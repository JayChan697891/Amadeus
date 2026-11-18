"""Trusted host composition of proposal, independent verification and handoff.

Each mutation retains the existing component's exact consent and durable fence.
run_once never resumes a partially executed producer/staging/verification attempt.
Only an already verified producer can resume its saved receiver handoff. Unknown
external execution still needs inspection through the existing owner APIs.
"""

from __future__ import annotations

import asyncio
import copy
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

from agentsync.adapters.approved_launch import digest
from agentsync.controlled_relay import (
    CodexProposalInput,
    ControlledRelay,
    RelayActor,
    RelayReviewer,
)
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import (
    HandoffReceiver,
    HandoffWorkspace,
    ProposalHandoff,
    ProposalHandoffOutcome,
    ProposalHandoffRequest,
)
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile
from agentsync.verification.owner_flow import OwnerCandidateFlow

ExactDecision = Callable[[dict[str, Any]], Awaitable[str | None]]
ReceiverBuilder = Callable[[HandoffReceiver, HandoffWorkspace], RelayActor]


@dataclass(frozen=True, slots=True)
class VerifiedProposalOutcome:
    state: Literal[
        "staging_denied",
        "execution_denied",
        "verification_not_passed",
        "completion_denied",
        "handoff",
    ]
    job_id: str | None = None
    execution_id: str | None = None
    handoff: ProposalHandoffOutcome | None = None
    execution_assessment: str | None = None
    verification: Literal["unverified"] = field(default="unverified", init=False)


def _boundary() -> NoReturn:
    raise AgentSyncError(
        "verified_flow_boundary", "The verified proposal flow is out of scope.", 409
    )


def _blocked_receiver(_receiver: HandoffReceiver, _workspace: HandoffWorkspace) -> RelayActor:
    # A concurrent text review must not start a receiver before Docker verification.
    raise AgentSyncError("verification_required", "Independent verification is required.", 409)


class VerifiedProposalFlow:
    """Owner-only host API; callbacks must independently approve the exact plans.

    Callbacks return the displayed staging plan SHA, job metadata SHA and completion
    decision SHA respectively. None, False or a different value never grants consent.
    The completion callback is a host decision, not a model verdict. The existing
    completion service independently requires a passed actual verifier result, current
    candidate pins and a distinct reviewer. This class never applies candidate code.
    """

    def __init__(self, core: Core, scratch: Path, receipts: Path) -> None:
        self._core = core
        self._relay = ControlledRelay(core, scratch, receipts)
        self._handoff = ProposalHandoff(core, scratch, receipts)

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise AgentSyncError("relay_execution_limit", "The verified flow budget expired.", 409)
        return remaining

    async def run_once(
        self,
        producer: RelayActor,
        proposal: CodexProposalInput,
        request: ProposalHandoffRequest,
        *,
        admin_token: str,
        stager: RelayReviewer,
        reviewer: RelayReviewer,
        profile: DockerProfile,
        approve_staging: ExactDecision,
        approve_execution: ExactDecision,
        approve_completion: ExactDecision,
        build_receiver: ReceiverBuilder,
        budget: float = 600,
    ) -> VerifiedProposalOutcome:
        if (
            type(producer) is not RelayActor
            or type(proposal) is not CodexProposalInput
            or type(request) is not ProposalHandoffRequest
            or type(stager) is not RelayReviewer
            or type(reviewer) is not RelayReviewer
            or type(profile) is not DockerProfile
            or proposal.submit_for_review is not True
            or proposal.task_id != request.source_task_id
            or len(
                {
                    producer.profile.project_id,
                    request.receiver.project_id,
                    stager.project_id,
                    reviewer.project_id,
                }
            )
            != 1
            or not all(
                callable(fn)
                for fn in (approve_staging, approve_execution, approve_completion, build_receiver)
            )
            or type(budget) not in (int, float)
            or not math.isfinite(budget)
            or not 0 < budget <= 900
        ):
            _boundary()
        deadline = asyncio.get_running_loop().time() + budget
        async with asyncio.timeout_at(deadline):
            return await self._run_once(
                producer,
                proposal,
                request,
                admin_token,
                stager,
                reviewer,
                profile,
                approve_staging,
                approve_execution,
                approve_completion,
                build_receiver,
                deadline,
            )

    async def _run_once(
        self,
        producer: RelayActor,
        proposal: CodexProposalInput,
        request: ProposalHandoffRequest,
        admin_token: str,
        stager: RelayReviewer,
        reviewer: RelayReviewer,
        profile: DockerProfile,
        approve_staging: ExactDecision,
        approve_execution: ExactDecision,
        approve_completion: ExactDecision,
        build_receiver: ReceiverBuilder,
        deadline: float,
    ) -> VerifiedProposalOutcome:
        owner = {"project_id": producer.profile.project_id, "admin_token": admin_token}
        stored = await self._relay.run_codex_proposal_once(
            producer, proposal, admin_token=admin_token, _execution_deadline=deadline
        )
        if stored.state != "proposal_stored":
            _boundary()
        saved = await self._handoff.run(
            request,
            admin_token=admin_token,
            build_receiver=_blocked_receiver,
            source_outcome=stored,
            wait_seconds=0,
            budget=self._remaining(deadline),
        )
        if saved.state != "waiting_for_review":
            _boundary()
        staging_auth = {
            "admin_token": admin_token,
            "staging_session_id": stager.session_id,
            "staging_session_token": stager.session_token,
        }
        preview = self._relay.preview_codex_proposal_staging(
            producer, proposal.task_id, **staging_auth
        )
        staging_sha = preview["plan_sha256"]
        # The callback receives a copy; it cannot replace the plan used below.
        staging_decision = await approve_staging(copy.deepcopy(preview))
        self._remaining(deadline)
        if staging_decision != staging_sha:
            return VerifiedProposalOutcome("staging_denied")
        staged = self._relay.stage_codex_proposal_once(
            producer,
            proposal.task_id,
            **staging_auth,
            expected_plan_sha256=staging_sha,
        )
        self._remaining(deadline)
        job = CandidateVerificationJobs(self._core).enqueue(
            **owner,
            candidate_id=staged["candidate_id"],
            expected_candidate_sha=staged["candidate_sha"],
            profile=profile,
            request_id="verified-flow-job-" + digest([request.request_id, proposal.task_id]),
        )
        execution_decision = await approve_execution(copy.deepcopy(job))
        self._remaining(deadline)
        if execution_decision != job["metadata_sha256"]:
            return VerifiedProposalOutcome("execution_denied", job["id"])
        flow = OwnerCandidateFlow(self._core)
        # Synchronous Docker work has its own bounded execution/cleanup policy.
        # Do not detach it to a thread whose completion would become unobservable.
        execution = flow.start_once(
            project_id=producer.profile.project_id,
            admin_token=admin_token,
            job_id=job["id"],
            expected_job_version=job["version"],
            expected_metadata_sha256=job["metadata_sha256"],
            profile=profile,
        )
        execution_id = execution["execution_id"]
        self._remaining(deadline)
        if execution["execution_assessment"] != "passed":
            return VerifiedProposalOutcome(
                "verification_not_passed",
                job["id"],
                execution_id,
                execution_assessment=execution["execution_assessment"],
            )
        submitted = self._relay.observe_codex_proposal_review(producer, proposal.task_id)
        if submitted.state != "submitted_for_review" or submitted.review_task_version is None:
            _boundary()
        decision = {
            "task_id": proposal.task_id,
            "expected_version": submitted.review_task_version,
            "job_id": job["id"],
            "execution_id": execution_id,
            "expected_execution_revision": execution["execution"]["revision"],
            "execution": execution,
            "reviewer_session_id": reviewer.session_id,
        }
        completion_sha = digest(decision)
        completion_decision = await approve_completion(
            {**copy.deepcopy(decision), "decision_sha256": completion_sha}
        )
        self._remaining(deadline)
        if completion_decision != completion_sha:
            return VerifiedProposalOutcome(
                "completion_denied",
                job["id"],
                execution_id,
                execution_assessment="passed",
            )
        flow.complete_once(
            project_id=producer.profile.project_id,
            admin_token=admin_token,
            session_id=reviewer.session_id,
            session_token=reviewer.session_token,
            task_id=proposal.task_id,
            expected_version=submitted.review_task_version,
            job_id=job["id"],
            execution_id=execution_id,
            expected_execution_revision=execution["execution"]["revision"],
            profile=profile,
            request_id="verified-flow-complete-" + digest([request.request_id, proposal.task_id]),
        )
        handoff = await self.resume_receiver(
            request,
            admin_token=admin_token,
            build_receiver=build_receiver,
            budget=self._remaining(deadline),
        )
        return VerifiedProposalOutcome("handoff", job["id"], execution_id, handoff, "passed")

    async def resume_receiver(
        self,
        request: ProposalHandoffRequest,
        *,
        admin_token: str,
        build_receiver: ReceiverBuilder,
        budget: float = 180,
    ) -> ProposalHandoffOutcome:
        """Resume only the receiver of a currently verified saved source.

        This does not rerun producer, staging, candidate execution or acceptance.
        Their interrupted/unknown attempts remain fenced by their existing services.
        """
        if (
            type(request) is not ProposalHandoffRequest
            or type(budget) not in (int, float)
            or not math.isfinite(budget)
            or not 0 < budget <= 900
        ):
            _boundary()
        deadline = asyncio.get_running_loop().time() + budget
        state = self._core.execute("get_project_state", request.receiver.authentication())
        source = next((t for t in state["tasks"] if t["id"] == request.source_task_id), None)
        if (
            source is None
            or source["status"] != "completed"
            or source["task_verification"] != "verified"
        ):
            raise AgentSyncError(
                "verification_required", "The source lacks current independent verification.", 409
            )
        return await self._handoff.run(
            request,
            admin_token=admin_token,
            build_receiver=build_receiver,
            wait_seconds=0,
            budget=self._remaining(deadline),
        )

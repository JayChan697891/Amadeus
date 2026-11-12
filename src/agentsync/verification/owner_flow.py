"""Explicit owner-side verification of one previously pinned candidate job.

Queue creation remains an independent, request-bound operation. Starting a job
uses separate durable claim, intent and execution transactions. A later failure
can leave earlier stages committed. Inspect the job, claim, intent and execution
through their existing authenticated services after interruption. This flow
never borrows a previous claim, retries execution or performs recovery for the
owner. Verified completion is a separate call with an independent reviewer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.verification.candidate_claims import OwnerCandidateClaims
from agentsync.verification.candidate_executor import OwnerCandidateExecutor
from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents
from agentsync.verification.candidate_jobs import (
    CandidateVerificationJobs,
    _error,
    _Lookup,
    _trusted_profile,
)
from agentsync.verification.docker import DockerProfile
from agentsync.verification.task_completion import OwnerVerifiedTaskCompletion

if TYPE_CHECKING:
    from agentsync.core.service import Core


class _Start(_Lookup):
    expected_job_version: int = Field(ge=1, le=2**63 - 3)
    expected_metadata_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
    lease_seconds: int = Field(ge=1, le=3600)


class OwnerCandidateFlow:
    """Compose the existing owner ledgers without adding an acceptance policy."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._jobs = CandidateVerificationJobs(core)
        self._claims = OwnerCandidateClaims(core)
        self._intents = OwnerCandidateExecutionIntents(core)
        self._executor = OwnerCandidateExecutor(core)
        self._completion = OwnerVerifiedTaskCompletion(core)

    def start_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_job_version: int,
        expected_metadata_sha256: str,
        profile: DockerProfile,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        """Start the queued job pinned by an enqueue receipt or authenticated read.

        The metadata digest covers the candidate, both task revisions, the
        exported input and the trusted verifier policy. Supply the job version
        and digest reviewed for this attempt. The returned executor observation
        does not complete a task, even if the verifier passes.
        """
        self._core._validated_payload(
            _Start,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_job_version": expected_job_version,
                "expected_metadata_sha256": expected_metadata_sha256,
                "lease_seconds": lease_seconds,
            },
        )
        job = self._jobs.get(project_id=project_id, admin_token=admin_token, job_id=job_id)
        if (
            job["version"] != expected_job_version
            or job["metadata_sha256"] != expected_metadata_sha256
        ):
            _error("version_conflict", "Candidate job does not match the reviewed queue pin.")
        if job["status"] != "queued":
            _error("invalid_state", "Starting candidate verification requires a queued job.")
        policy = _trusted_profile(profile)
        if policy != {
            "kind": job["profile_kind"],
            "sha256": job["profile_sha256"],
            "image_id": job["image_id"],
        }:
            _error("profile_mismatch", "Trusted profile differs from the queued candidate policy.")
        if lease_seconds <= profile.timeout_seconds + 60:
            _error(
                "reservation_expired", "Insufficient reservation time for execution and cleanup."
            )

        claimed = self._claims.claim_once(
            project_id=project_id,
            admin_token=admin_token,
            job_id=job_id,
            expected_version=expected_job_version,
            profile=profile,
            lease_seconds=lease_seconds,
        )
        claimed_job = claimed["job"]
        reservation = claimed["reservation"]
        if (
            claimed_job["id"] != job_id
            or claimed_job["metadata_sha256"] != expected_metadata_sha256
        ):
            _error("version_conflict", "Candidate pin changed during reservation.")
        prepared = self._intents.prepare_once(
            project_id=project_id,
            admin_token=admin_token,
            job_id=job_id,
            expected_version=claimed_job["version"],
            profile=profile,
        )
        intent = prepared["intent"]
        if (
            intent["job_id"] != job_id
            or intent["claim_id"] != reservation["id"]
            or intent["claim_proof_sha256"] != reservation["proof_sha256"]
            or intent["metadata_sha256"] != expected_metadata_sha256
        ):
            _error("version_conflict", "Candidate intent does not match this reservation.")
        return self._executor.execute_once(
            project_id=project_id,
            admin_token=admin_token,
            job_id=job_id,
            intent_id=intent["id"],
            expected_job_version=claimed_job["version"],
            expected_intent_revision=intent["revision"],
            profile=profile,
        )

    def complete_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        session_id: str,
        session_token: str,
        task_id: str,
        expected_version: int,
        job_id: str,
        execution_id: str,
        expected_execution_revision: int,
        request_id: str,
        profile: DockerProfile,
    ) -> dict[str, Any]:
        """Record explicit independent acceptance through the existing proof gate."""
        return self._completion.complete_once(
            project_id=project_id,
            admin_token=admin_token,
            session_id=session_id,
            session_token=session_token,
            task_id=task_id,
            expected_version=expected_version,
            job_id=job_id,
            execution_id=execution_id,
            expected_execution_revision=expected_execution_revision,
            request_id=request_id,
            profile=profile,
        )

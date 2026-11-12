"""Owner-side admission for a pinned client plan in an isolated host workspace.

The authority callback belongs to trusted host code. It must independently
establish cost and isolation and present the exact plan for human approval.
This module cannot establish those conditions from flags or client output.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from agentsync.adapters import claude_invocation, codex_invocation, cursor_invocation
from agentsync.adapters.base import AdapterTask, _identifier
from agentsync.adapters.host_receipts import _ReceiptDirectory
from agentsync.adapters.launch_context import LaunchContext
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError

ClientKind = Literal["codex", "claude", "cursor"]
HostProfile = (
    codex_invocation.CodexHostProfile
    | claude_invocation.ClaudeHostProfile
    | cursor_invocation.CursorHostProfile
)
Invocation = (
    codex_invocation.CodexInvocation
    | claude_invocation.ClaudeInvocation
    | cursor_invocation.CursorInvocation
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True).encode("ascii")).hexdigest()


def _launch_key(task: AdapterTask) -> str:
    return digest([task.project_id, task.session_id, task.task_id, task.request_id])


def client_kind(profile: HostProfile) -> ClientKind:
    if type(profile) is codex_invocation.CodexHostProfile:
        return "codex"
    if type(profile) is claude_invocation.ClaudeHostProfile:
        return "claude"
    if type(profile) is cursor_invocation.CursorHostProfile:
        return "cursor"
    raise AgentSyncError("validation_error", "An exact supported host profile is required.")


@dataclass(frozen=True, slots=True)
class LaunchReview:
    client: ClientKind
    plan_sha256: str
    plan: Invocation = field(repr=False)
    task: AdapterTask = field(repr=False)


@dataclass(frozen=True, slots=True)
class LaunchConsent:
    approval_id: str = field(repr=False)
    plan_sha256: str
    expires_at: float
    confirmed_cost: bool
    confirmed_isolation: bool


@dataclass(frozen=True, slots=True)
class LaunchAdmissionObservation:
    state: Literal["not_recorded", "request_reserved", "both_reservations_recorded", "unknown"]
    plan_sha256: str | None = None
    execution_verified: Literal[False] = field(default=False, init=False)


LaunchAuthority = Callable[[LaunchReview], Awaitable[LaunchConsent | None]]


def _check_execution_deadline(deadline: float | None) -> None:
    if deadline is not None and asyncio.get_running_loop().time() >= deadline:
        raise AgentSyncError("relay_execution_limit", "The controlled relay execution budget expired.", 409)


def prepare_launch_review(
    profile: HostProfile, task: AdapterTask, *, environment: dict[str, str]
) -> LaunchReview:
    """Prepare the exact host plan without invoking a client or requesting consent."""
    client = client_kind(profile)
    if isinstance(profile, codex_invocation.CodexHostProfile):
        plan: Invocation = codex_invocation.prepare_invocation(profile, task, environment=environment)
    elif isinstance(profile, claude_invocation.ClaudeHostProfile):
        plan = claude_invocation.prepare_invocation(profile, task, environment=environment)
    else:
        plan = cursor_invocation.prepare_invocation(profile, task, environment=environment)
    return LaunchReview(
        client,
        digest([
            client, task.project_id, task.session_id, task.task_id, task.request_id,
            task.timeout_seconds, task.instruction, plan.argv, str(plan.cwd), plan.stdin_text,
            sorted(plan.child_env().items()), plan.timeout_seconds, plan.output_limit,
            plan.expected_cli_version, plan.binary_sha256,
        ]),
        plan,
        task,
    )


def _consent_is_current(consent: LaunchConsent | None, review: LaunchReview) -> bool:
    now = time.time()
    return (
        type(consent) is LaunchConsent
        and type(consent.plan_sha256) is str
        and consent.plan_sha256 == review.plan_sha256
        and type(consent.expires_at) in (int, float)
        and now < consent.expires_at <= now + 300
        and consent.confirmed_cost is True
        and consent.confirmed_isolation is True
    )


def _valid_digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _observe_admission(
    store: _ReceiptDirectory, request_key: str, client: str,
) -> LaunchAdmissionObservation:
    if not _valid_digest(request_key):
        return LaunchAdmissionObservation("unknown")
    launch = store.read(f"launch-{request_key}.json")
    if launch is None:
        return LaunchAdmissionObservation("not_recorded")
    plan = launch.get("plan_sha256")
    consent_key = launch.get("consent_sha256")
    if (
        type(plan) is not str or not _valid_digest(plan)
        or launch.get("client") != client or launch.get("request_sha256") != request_key
        or not _valid_digest(consent_key)
    ):
        return LaunchAdmissionObservation("unknown")
    consent = store.read(f"consent-{consent_key}.json")
    if consent is None:
        return LaunchAdmissionObservation("request_reserved", plan)
    if consent != launch:
        return LaunchAdmissionObservation("unknown")
    return LaunchAdmissionObservation("both_reservations_recorded", plan)


class ApprovedLaunchFactory:
    """Use one exact prepared invocation and consume a host grant before capture.

    The trusted receipt directory must remain private and retained across restarts.
    A recorded request or approval can never launch again through that directory.
    Partial writes and uncertain starts are deliberately not reclaimed. The two
    exclusive receipts can consume a grant without starting a process.
    """

    def __init__(
        self,
        profile: HostProfile,
        *,
        environment: dict[str, str],
        receipts: Path,
        authority: LaunchAuthority,
        revalidate: Callable[[AdapterTask], None],
        _receipt_store: _ReceiptDirectory | None = None,
        _execution_deadline: float | None = None,
    ) -> None:
        self.client = client_kind(profile)
        if type(environment) is not dict or not callable(authority) or not callable(revalidate):
            raise AgentSyncError("validation_error", "Invalid host launch authority configuration.")
        if not isinstance(receipts, Path) or not receipts.is_absolute() or not receipts.is_dir():
            raise AgentSyncError("validation_error", "An existing private receipt directory is required.")
        self._profile = replace(profile)
        self._environment = dict(environment)
        root = receipts.resolve(strict=True)
        if _receipt_store is not None and (type(_receipt_store) is not _ReceiptDirectory or _receipt_store.root != root):
            raise AgentSyncError("validation_error", "The shared private receipt directory must match.")
        self._receipt_store = _receipt_store if _receipt_store is not None else _ReceiptDirectory(root)
        self._receipt_store.check()
        self._authority = authority
        self._revalidate = revalidate
        if _execution_deadline is not None and (
            type(_execution_deadline) is not float or not math.isfinite(_execution_deadline)
        ):
            raise AgentSyncError("validation_error", "Invalid host execution deadline.")
        self._execution_deadline = _execution_deadline

    def _prepare(self, task: AdapterTask) -> Invocation:
        return self._review(task).plan

    def _review(self, task: AdapterTask) -> LaunchReview:
        return prepare_launch_review(self._profile, task, environment=self._environment)

    async def __call__(self, task: AdapterTask, context: LaunchContext) -> CapturedProcess:
        if type(context) is not LaunchContext:
            raise AgentSyncError("validation_error", "Adapter-issued launch context required.")
        _check_execution_deadline(self._execution_deadline)
        context.check(task)
        review = await context.wait_before_start(task, lambda: asyncio.to_thread(self._review, task))
        plan = review.plan
        child_env = plan.child_env()
        consent = await context.wait_before_start(task, lambda: self._authority(review))
        if consent is None or not _consent_is_current(consent, review):
            raise AgentSyncError("launch_not_authorized", "The exact client launch is not authorized.", 403)
        _identifier(consent.approval_id)
        # Hash the binary and resolve the configured paths again after approval.
        fresh = await context.wait_before_start(task, lambda: asyncio.to_thread(self._prepare, task))
        if fresh != plan:
            raise AgentSyncError("launch_plan_changed", "The approved client plan changed.", 409)
        if not _consent_is_current(consent, review):
            raise AgentSyncError("launch_not_authorized", "The client launch consent expired.", 403)
        request_key = _launch_key(task)
        consent_key = digest(consent.approval_id)
        receipt: dict[str, object] = {
            "plan_sha256": review.plan_sha256, "client": self.client,
            "request_sha256": request_key, "consent_sha256": consent_key,
        }
        self._receipt_store.write(f"launch-{request_key}.json", receipt)
        self._receipt_store.write(f"consent-{consent_key}.json", receipt)
        self._revalidate(task)
        self._receipt_store.check()
        if not _consent_is_current(consent, review):
            raise AgentSyncError("launch_not_authorized", "The client launch consent expired.", 403)
        _check_execution_deadline(self._execution_deadline)
        return await context.start(
            task, plan.argv, cwd=plan.cwd, stdin_text=plan.stdin_text,
            timeout_seconds=plan.timeout_seconds, output_limit=plan.output_limit, env=child_env,
        )

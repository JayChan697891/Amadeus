"""Host-only two-client relay for an isolated, explicitly approved pilot.

The host supplies prepared Core tasks, isolated managed worktrees and fixed
synthetic inputs. Each start needs a separate approval for its exact plan.
The final task is submitted for independent review through the existing Core.
Receipts never include credentials, process output, client IDs or private paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

from agentsync.adapters._host_process import _HostRun
from agentsync.adapters.approved_launch import (
    ApprovedLaunchFactory,
    HostProfile,
    LaunchAdmissionObservation,
    LaunchAuthority,
    LaunchReview,
    _check_execution_deadline,
    _launch_key,
    _observe_admission,
    client_kind,
    digest,
    prepare_launch_review,
)
from agentsync.adapters.base import AdapterTask, _bounded_text, _identifier
from agentsync.adapters.claude import ClaudeAdapter, ClaudeResult
from agentsync.adapters.codex import CodexAdapter, CodexResult
from agentsync.adapters.cursor import CursorAdapter, CursorResult
from agentsync.adapters.host_receipts import _ReceiptDirectory
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError

_ActorAdapter = CodexAdapter | ClaudeAdapter | CursorAdapter
_REVIEW_MARKER = "Two controlled client replies matched the pilot input. Independent review pending."
_CLIENT_VERSION = r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}"


def _reject() -> NoReturn:
    raise AgentSyncError("relay_boundary", "The controlled relay no longer matches its scope.", 409)


@dataclass(frozen=True, slots=True)
class RelayActor:
    agent_id: str
    session_token: str = field(repr=False)
    profile: HostProfile = field(repr=False)
    worktree_id: str
    expected_head: str
    environment: dict[str, str] = field(repr=False)
    authority: LaunchAuthority = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.agent_id, self.session_token, self.worktree_id):
            _identifier(value)
        client_kind(self.profile)
        if (
            type(self.expected_head) is not str
            or len(self.expected_head) not in (40, 64)
            or any(character not in "0123456789abcdef" for character in self.expected_head)
            or type(self.environment) is not dict
            or not callable(self.authority)
        ):
            _reject()


@dataclass(frozen=True, slots=True)
class RelayInput:
    task_id: str
    expected_version: int
    context_id: str
    context_version: int
    context_sha256: str
    first_instruction: str = field(repr=False)
    second_instruction: str = field(repr=False)
    first_reply: str = field(repr=False)
    second_reply: str = field(repr=False)
    timeout_seconds: int = 90

    def __post_init__(self) -> None:
        _identifier(self.task_id)
        _identifier(self.context_id)
        for version in (self.expected_version, self.context_version):
            if type(version) is not int or not 1 <= version < 2**63 - 10:
                _reject()
        _bounded_text(self.context_sha256, 64)
        if len(self.context_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.context_sha256):
            _reject()
        for value in (self.first_instruction, self.second_instruction, self.first_reply, self.second_reply):
            _bounded_text(value, 1500)
            if not value.strip():
                _reject()
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 180:
            _reject()


@dataclass(frozen=True, slots=True)
class RelayOutcome:
    state: Literal["not_started", "incomplete", "conflict", "ready_for_review"]
    verification: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class RelayAttemptObservation:
    leg: Literal["first", "second"]
    state: Literal["not_dispatched", "outcome_unknown", "terminal_recorded"]
    client: str | None = None
    status: str | None = None
    exit_code: int | None = None
    timed_out: bool | None = None
    parent_ended: bool | None = None
    run_sha256: str | None = None
    session_sha256: str | None = None
    error_code: str | None = None
    admission: LaunchAdmissionObservation | None = None
    adapter_elapsed_ms: int | None = None
    reported_input_tokens: int | None = None
    reported_output_tokens: int | None = None
    agent_sha256: str | None = None
    declared_client_version: str | None = None
    protocol_session_sha256: str | None = None
    billing_verified: Literal[False] = field(default=False, init=False)
    cost_usd: None = field(default=None, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)


def _matched_text(value: Any, pattern: str) -> str | None:
    return value if type(value) is str and re.fullmatch(pattern, value) is not None else None


def _receipt_bool(value: Any) -> bool | None:
    return value if type(value) is bool else None


def _receipt_uint(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value < 2**63 else None


def _terminal_metrics(
    run: _HostRun, result: CodexResult | ClaudeResult | CursorResult | None = None,
) -> dict[str, object]:
    """Record elapsed time and sanitized observations from the matching adapter result."""
    metrics: dict[str, object] = {}
    if run.finished_at is not None:
        elapsed_ms = (run.finished_at - run.started_at) * 1000
        if math.isfinite(elapsed_ms) and 0 <= elapsed_ms < 2**63:
            metrics["adapter_elapsed_ms"] = int(elapsed_ms)
    if result is not None and result.run == run:
        session = (
            result.client_thread_id if isinstance(result, CodexResult) else result.client_session_id
        )
        if type(session) is str and session:
            metrics["protocol_session_sha256"] = digest(session)
        if isinstance(result, (CodexResult, ClaudeResult)) and result.usage is not None:
            metrics["reported_input_tokens"] = _receipt_uint(result.usage.input_tokens)
            metrics["reported_output_tokens"] = _receipt_uint(result.usage.output_tokens)
    return metrics


@dataclass(frozen=True, slots=True)
class RelayReviewer:
    project_id: str
    session_id: str
    session_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.project_id, self.session_id, self.session_token):
            _identifier(value)


class ControlledRelay:
    """Run at most one two-stage pilot for a project task in the receipt directory.

    Keep the private receipt directory and the entire separate Core data
    directory in place across restart. Incomplete
    runs cannot be retried here. Expired Core task leases remain recoverable via
    Core, which does not prove any prior client or descendant stopped.
    """

    def __init__(self, core: Core, scratch: Path, receipts: Path) -> None:
        if (
            type(core) is not Core
            or not isinstance(scratch, Path)
            or not isinstance(receipts, Path)
            or not scratch.is_absolute()
            or not receipts.is_absolute()
        ):
            _reject()
        self._core = core
        self._scratch = scratch.resolve(strict=True)
        self._receipts = receipts.resolve(strict=True)
        core_data = core.data_dir.resolve(strict=True)
        if (
            not self._scratch.is_dir()
            or not self._receipts.is_dir()
            or self._receipts == self._scratch
            or not self._receipts.is_relative_to(self._scratch)
            or not core_data.is_relative_to(self._scratch)
            or core_data.is_relative_to(self._receipts)
        ):
            _reject()
        self._receipt_store = _ReceiptDirectory(self._receipts)
        self._receipt_anchors = _ReceiptDirectory(core_data)

    def _check_receipt_anchor(self, project_id: str, *, bind: bool = False) -> None:
        """The separate Core data directory retains the selected receipt root across restart."""
        name = f"controlled-relay-{digest(project_id)}.json"
        expected: dict[str, object] = {
            "schema_version": 1, "receipt_root_sha256": self._receipt_store.location_pin(),
        }
        current = self._receipt_anchors.read(name, durable=bind)
        if current is None and bind:
            try:
                self._receipt_anchors.write(name, expected)
            except AgentSyncError as error:
                if error.code != "attempt_already_reserved":
                    raise
            current = self._receipt_anchors.read(name, durable=True)
        if (current is not None or bind) and (
            not current or type(current.get("schema_version")) is not int or current != expected
        ):
            raise AgentSyncError("relay_boundary", "The project receipt directory does not match its saved identity.", 409)

    def _call(self, actor: RelayActor, operation: str, **payload: Any) -> dict[str, Any]:
        return self._core.execute(operation, {
            **payload,
            "project_id": actor.profile.project_id,
            "session_id": actor.profile.session_id,
            "session_token": actor.session_token,
        })

    def _project_state(self, actor: RelayActor, *, min_session_seconds: float = 0) -> dict[str, Any]:
        return self._session_project_state(
            actor.profile.project_id, actor.profile.session_id, actor.session_token,
            expected_agent_id=actor.agent_id, min_session_seconds=min_session_seconds,
        )

    def _session_project_state(
        self, project_id: str, session_id: str, session_token: str, *,
        expected_agent_id: str | None = None, min_session_seconds: float = 0,
    ) -> dict[str, Any]:
        state = self._core.execute("get_project_state", {
            "project_id": project_id, "session_id": session_id, "session_token": session_token,
        })
        project_root = Path(state["project"]["root_path"]).resolve(strict=True)
        deadline = time.time() + min_session_seconds
        if not project_root.is_relative_to(self._scratch) or not any(
            session["id"] == session_id
            and (expected_agent_id is None or session["agent_id"] == expected_agent_id)
            and session["expires_at"] > deadline
            for session in state["sessions"]
        ):
            _reject()
        return state

    def _state(
        self, actor: RelayActor, task_id: str, *, min_session_seconds: float = 0
    ) -> dict[str, Any]:
        state = self._project_state(actor, min_session_seconds=min_session_seconds)
        for task in state["tasks"]:
            if task["id"] == task_id:
                return task
        raise AgentSyncError("relay_boundary", "The controlled relay task is unavailable.", 409)

    def _workspace(self, actor: RelayActor, task_id: str) -> dict[str, Any]:
        view = self._call(
            actor, "inspect_owned_worktree", worktree_id=actor.worktree_id, task_id=task_id,
        )
        root = Path(view["path"]).resolve(strict=True)
        if (
            view["task_id"] != task_id
            or view["head_sha"] != actor.expected_head
            or view["dirty"] is not False
            or actor.profile.root != root
            or root == self._scratch
            or not root.is_relative_to(self._scratch)
            or self._receipts.is_relative_to(root)
            or self._core.data_dir.resolve().is_relative_to(root)
        ):
            _reject()
        return view

    def _check_worktree_owner(self, actor: RelayActor, task_id: str) -> None:
        self._call(
            actor, "inspect_owned_worktree", worktree_id=actor.worktree_id,
            task_id=task_id, metadata_only=True,
        )

    @staticmethod
    def _receipt_name(key: str, stage: str) -> str:
        return f"relay-{key}-{stage}.json"

    def _record(self, key: str, stage: str, **detail: object) -> None:
        self._receipt_store.write(self._receipt_name(key, stage), {"stage": stage, "time": time.time(), **detail})

    def _key(self, actor: RelayActor, task_id: str) -> str:
        return self._task_receipt_key(actor.profile.project_id, task_id)

    @staticmethod
    def _task_receipt_key(project_id: str, task_id: str) -> str:
        return digest([project_id, task_id])

    def _read_receipt(self, key: str, stage: str) -> dict[str, Any] | None:
        receipt = self._receipt_store.read(self._receipt_name(key, stage))
        if receipt is None:
            return None
        return receipt if receipt.get("stage") == stage else {}

    def observe(self, actor: RelayActor, task_id: str) -> RelayOutcome:
        """Authenticate before observing a receipt, including after host restart."""
        task = self._state(actor, task_id)
        self._check_receipt_anchor(actor.profile.project_id)
        key = self._key(actor, task_id)
        ready = self._review_submission(key)
        if ready is not None:
            if self._matches_submission(task, ready) and task["status"] == "review":
                return RelayOutcome("ready_for_review")
            return RelayOutcome("incomplete")
        conflict = self._read_receipt(key, "conflict")
        if conflict is not None:
            return RelayOutcome("conflict" if conflict else "incomplete")
        if self._read_receipt(key, "incomplete") is not None:
            return RelayOutcome("incomplete")
        return RelayOutcome("not_started")

    def _review_submission(self, key: str) -> dict[str, Any] | None:
        ready = self._read_receipt(key, "ready_for_review")
        if ready is not None:
            return ready
        intent = self._read_receipt(key, "review-intent")
        if intent is None:
            return None
        admission = self._read_receipt(key, "incomplete")
        if (
            not admission or not intent or "wave_sha256" not in intent
            or admission.get("wave_sha256") != intent["wave_sha256"]
            or _matched_text(intent.get("owner_session_sha256"), r"[0-9a-f]{64}") is None
            or any(
                self._inspect_attempt(key, leg).status != "expected_reply" for leg in ("first", "second")
            )
        ):
            return {}
        return intent

    @staticmethod
    def _matches_submission(
        task: dict[str, Any], receipt: dict[str, Any], *, version_advance: int = 0,
    ) -> bool:
        version = receipt.get("task_version")
        owner_pin = receipt.get("owner_session_sha256")
        owner = task["owner_session_id"]
        return (
            type(version) is int and task["version"] == version + version_advance
            and task["result"] == _REVIEW_MARKER
            and (owner_pin is None or (type(owner) is str and digest(owner) == owner_pin))
        )

    def _wave_terminal_state(
        self, actor: RelayActor, task_id: str, wave_key: str,
    ) -> Literal["ready_for_review", "conflict"] | None:
        """Bind historical submission or conflict to the same durable wave."""
        task = self._state(actor, task_id)
        return self._wave_terminal_from_task(actor.profile.project_id, task, wave_key)

    def _wave_terminal_from_task(
        self, project_id: str, task: dict[str, Any], wave_key: str,
    ) -> Literal["ready_for_review", "conflict"] | None:
        if task["project_id"] != project_id:
            _reject()
        self._check_receipt_anchor(project_id)
        task_id = task["id"]
        key = self._task_receipt_key(project_id, task_id)
        admission = self._read_receipt(key, "incomplete")
        if not admission or admission.get("wave_sha256") != wave_key:
            return None
        ready = self._review_submission(key)
        conflict = self._read_receipt(key, "conflict")
        if ready is None and conflict and conflict.get("wave_sha256") == wave_key:
            return "conflict"
        if not ready or conflict is not None or ready.get("wave_sha256") != wave_key:
            return None
        version = ready.get("task_version")
        if type(version) is not int or task["result"] != _REVIEW_MARKER:
            return None
        if task["status"] == "review" and self._matches_submission(task, ready):
            return "ready_for_review"
        if task["status"] not in ("completed", "pending") or task["version"] != version + 1:
            return None
        accepted = task["status"] == "completed"
        if accepted and not self._matches_submission(task, ready, version_advance=1):
            return None
        if not accepted and task["owner_session_id"] is not None:
            return None
        review = task["latest_review"]
        sender = _matched_text(ready.get("sender_sha256"), r"[0-9a-f]{64}")
        recipient = _matched_text(ready.get("recipient_sha256"), r"[0-9a-f]{64}")
        if (
            type(review) is not dict or review.get("accept") is not accepted
            or review.get("version") != version + 1 or review.get("task_id") != task_id
            or review.get("project_id") != project_id
            or type(review.get("reviewer_agent_id")) is not str
            or sender is None or recipient is None or sender == recipient
            or digest(review["reviewer_agent_id"]) in (sender, recipient)
        ):
            return None
        # This describes the historical submission, not current task status or proof of verification.
        return "ready_for_review"

    def inspect_attempts(
        self, actor: RelayActor, task_id: str, *, admin_token: str
    ) -> tuple[RelayAttemptObservation, RelayAttemptObservation]:
        """Read sanitized same-project observations without reconnecting to any process."""
        if type(actor) is not RelayActor:
            _reject()
        _identifier(task_id)
        self._authorize_owner(actor, admin_token)
        self._state(actor, task_id)
        return self._project_attempts(actor.profile.project_id, task_id)

    def owner_inspect_attempts(
        self, project_id: str, task_id: str, *, admin_token: str,
    ) -> tuple[RelayAttemptObservation, RelayAttemptObservation]:
        """Read historical attempt receipts with project-owner authority after sessions expire."""
        _identifier(project_id)
        _identifier(task_id)
        self._authorize_project_owner(project_id, admin_token)
        return self._project_attempts(project_id, task_id)

    def _project_attempts(
        self, project_id: str, task_id: str,
    ) -> tuple[RelayAttemptObservation, RelayAttemptObservation]:
        self._check_receipt_anchor(project_id)
        key = self._task_receipt_key(project_id, task_id)
        return self._inspect_attempt(key, "first"), self._inspect_attempt(key, "second")

    def _authorize_owner(self, actor: RelayActor, admin_token: str) -> None:
        self._authorize_project_owner(actor.profile.project_id, admin_token)

    def _authorize_project_owner(self, project_id: str, admin_token: str) -> None:
        self._core.execute_owner(
            "list_members",
            {"project_id": project_id, "admin_token": admin_token, "limit": 1},
        )

    def _owner_worker_ids(
        self, project_id: str, agent_ids: set[str], admin_token: str,
    ) -> set[str]:
        response = self._core.execute_owner("list_selected_members", {
            "project_id": project_id, "admin_token": admin_token, "agent_ids": sorted(agent_ids),
        })
        return {member["agent_id"] for member in response["members"] if "worker" in member["roles"]}

    def _require_relay_workers(self, first: RelayActor, second: RelayActor, admin_token: str) -> None:
        if type(first) is not RelayActor or type(second) is not RelayActor:
            _reject()
        project_id = first.profile.project_id
        if second.profile.project_id != project_id or first.agent_id == second.agent_id:
            _reject()
        needed = {first.agent_id, second.agent_id}
        if self._owner_worker_ids(project_id, needed, admin_token) != needed:
            raise AgentSyncError("forbidden", "Both relay participants must hold the worker role.", 403)

    def _inspect_attempt(
        self, key: str, leg: Literal["first", "second"]
    ) -> RelayAttemptObservation:
        dispatch = self._read_receipt(key, leg + "-dispatched")
        observed = self._read_receipt(key, leg + "-observed")
        stopped = self._read_receipt(key, leg + "-stopped")
        if dispatch is None and observed is None and stopped is None:
            return RelayAttemptObservation(leg, "not_dispatched")
        client = _matched_text((dispatch or {}).get("client"), r"codex|claude|cursor")
        request = _matched_text((dispatch or {}).get("launch_request_sha256"), r"[0-9a-f]{64}")
        agent = _matched_text((dispatch or {}).get("agent_sha256"), r"[0-9a-f]{64}")
        version = _matched_text((dispatch or {}).get("declared_client_version"), _CLIENT_VERSION)
        admission = (
            _observe_admission(self._receipt_store, request, client)
            if request is not None and client is not None else None
        )
        if client is None or (observed is None) == (stopped is None):
            return RelayAttemptObservation(
                leg, "outcome_unknown", client, admission=admission,
                agent_sha256=agent, declared_client_version=version,
            )
        terminal = observed if observed is not None else stopped
        assert terminal is not None
        status = _matched_text(
            terminal.get("status"),
            r"expected_reply" if observed is not None else r"failed|unknown|succeeded|reply_mismatch",
        )
        exit_code = terminal.get("exit_code")
        parent_ended = _receipt_bool(terminal.get("parent_ended"))
        if status is None or (
            status == "expected_reply"
            and (type(exit_code) is not int or exit_code != 0 or parent_ended is not True)
        ):
            return RelayAttemptObservation(
                leg, "outcome_unknown", client, admission=admission,
                agent_sha256=agent, declared_client_version=version,
            )
        return RelayAttemptObservation(
            leg, "terminal_recorded", client, status,
            exit_code=exit_code if type(exit_code) is int and -(2**63) <= exit_code < 2**63 else None,
            timed_out=_receipt_bool(terminal.get("timed_out")),
            parent_ended=parent_ended,
            run_sha256=_matched_text(terminal.get("run_sha256"), r"[0-9a-f]{64}"),
            session_sha256=_matched_text(terminal.get("session_sha256"), r"[0-9a-f]{64}"),
            error_code=_matched_text(terminal.get("error_code"), r"[a-z_]{1,64}"),
            admission=admission,
            adapter_elapsed_ms=_receipt_uint(terminal.get("adapter_elapsed_ms")),
            reported_input_tokens=_receipt_uint(terminal.get("reported_input_tokens")) if client != "cursor" else None,
            reported_output_tokens=_receipt_uint(terminal.get("reported_output_tokens")) if client != "cursor" else None,
            agent_sha256=agent,
            declared_client_version=version,
            protocol_session_sha256=_matched_text(terminal.get("protocol_session_sha256"), r"[0-9a-f]{64}"),
        )

    def review_once(
        self, reviewer: RelayReviewer, task_id: str, *, accept: bool, evidence: str
    ) -> dict[str, Any]:
        """Record a human-directed Core review from a third enrolled identity."""
        if type(reviewer) is not RelayReviewer or type(accept) is not bool:
            _reject()
        _identifier(task_id)
        _bounded_text(evidence, 4000)
        if not evidence.strip():
            _reject()
        auth = {
            "project_id": reviewer.project_id, "session_id": reviewer.session_id,
            "session_token": reviewer.session_token,
        }
        project = self._core.execute("get_project_state", auth)
        self._check_receipt_anchor(reviewer.project_id)
        key = digest([reviewer.project_id, task_id])
        ready = self._review_submission(key)
        if not ready:
            _reject()
        actor = next(
            (row["agent_id"] for row in project["sessions"] if row["id"] == reviewer.session_id),
            None,
        )
        sender = _matched_text(ready.get("sender_sha256"), r"[0-9a-f]{64}")
        recipient = _matched_text(ready.get("recipient_sha256"), r"[0-9a-f]{64}")
        if actor is None or sender is None or recipient is None or sender == recipient or digest(actor) in (sender, recipient):
            _reject()
        version = ready.get("task_version")
        if type(version) is not int or not any(
            row["id"] == task_id and row["status"] == "review" and self._matches_submission(row, ready)
            for row in project["tasks"]
        ):
            _reject()
        return self._core.execute("review_task", {
            **auth, "task_id": task_id, "expected_version": version, "accept": accept,
            "evidence": evidence, "request_id": f"relay:{key}:independent-review",
        })

    def _claim(self, actor: RelayActor, task_id: str, version: int, request: str) -> dict[str, Any]:
        lease = self._call(actor, "claim_task", task_id=task_id, expected_version=version, request_id=request)
        state = self._state(actor, task_id)
        if state["status"] != "claimed" or state["version"] != lease["version"]:
            _reject()
        if state["owner_session_id"] != actor.profile.session_id:
            _reject()
        return lease

    async def _attempt(
        self,
        actor: RelayActor,
        spec: RelayInput,
        claim: dict[str, Any],
        key: str,
        stage: str,
        task: AdapterTask,
        expected_reply: str,
        execution_deadline: float | None,
    ) -> dict[str, Any]:
        _check_execution_deadline(execution_deadline)
        prefix = f"relay:{key}:{stage}"
        lease_token = claim["lease_token"]
        active = self._call(
            actor, "update_task", task_id=spec.task_id, lease_token=lease_token,
            expected_version=claim["version"], status="running", request_id=prefix + ":running",
        )

        def renew(_: AdapterTask) -> None:
            nonlocal active
            _check_execution_deadline(execution_deadline)
            self._workspace(actor, spec.task_id)
            active = self._call(
                actor, "renew_lease", task_id=spec.task_id, lease_token=lease_token,
                expected_version=active["version"], request_id=prefix + ":capture",
            )
            current = self._state(actor, spec.task_id, min_session_seconds=spec.timeout_seconds + 2)
            if (
                current["status"] != "running"
                or current["version"] != active["version"]
                or current["owner_session_id"] != actor.profile.session_id
                or current["lease_expires_at"] <= time.time() + spec.timeout_seconds + 2
            ):
                _reject()
            _check_execution_deadline(execution_deadline)

        factory = ApprovedLaunchFactory(
            actor.profile, environment=actor.environment, receipts=self._receipts,
            authority=actor.authority, revalidate=renew, _receipt_store=self._receipt_store,
            _execution_deadline=execution_deadline,
        )
        adapter: _ActorAdapter
        namespace = (task.project_id, task.session_id)
        if factory.client == "codex":
            adapter = CodexAdapter(*namespace, contextual_factory=factory)
        elif factory.client == "claude":
            adapter = ClaudeAdapter(*namespace, contextual_factory=factory)
        else:
            adapter = CursorAdapter(*namespace, contextual_factory=factory)
        self._record(
            key, stage + "-dispatched", client=factory.client, launch_request_sha256=_launch_key(task),
            agent_sha256=digest(actor.agent_id),
            declared_client_version=_matched_text(actor.profile.expected_cli_version, _CLIENT_VERSION),
        )
        run = await adapter.start_task(task)
        try:
            run = await adapter.wait_terminal(run.run_id, timeout_seconds=spec.timeout_seconds + 2)
            if run.status != "succeeded" or run.exit_code != 0 or not run.parent_ended:
                self._record(
                    key, stage + "-stopped", status=run.status, timed_out=run.timed_out,
                    exit_code=run.exit_code, parent_ended=run.parent_ended,
                    run_sha256=digest(run.run_id), session_sha256=digest(run.session_id),
                    error_code=_matched_text(run.error_code, r"[a-z_]{1,64}"),
                    **_terminal_metrics(run),
                )
                _check_execution_deadline(execution_deadline)
                _reject()
            result = await adapter.get_result(run.run_id)
        except (TimeoutError, asyncio.CancelledError):
            with suppress(AgentSyncError, TimeoutError):
                async with asyncio.timeout(2):
                    await adapter.cancel_task(run.run_id)
            raise
        matches = (
            result.agent_messages == (expected_reply,) if isinstance(result, CodexResult)
            else result.result_text == expected_reply
        )
        if result.run != run or not matches:
            self._record(
                key, stage + "-stopped", status="reply_mismatch", exit_code=run.exit_code,
                timed_out=run.timed_out, parent_ended=run.parent_ended,
                run_sha256=digest(run.run_id), session_sha256=digest(run.session_id),
                error_code="reply_mismatch",
                **_terminal_metrics(run, result),
            )
            _reject()
        self._record(
            key, stage + "-observed", status="expected_reply", run_sha256=digest(run.run_id),
            session_sha256=digest(run.session_id), exit_code=run.exit_code,
            parent_ended=run.parent_ended, timed_out=run.timed_out,
            **_terminal_metrics(run, result),
        )
        return {**active, "lease_token": lease_token}

    def _pinned_inputs(
        self, first: RelayActor, second: RelayActor, spec: RelayInput,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], tuple[AdapterTask, AdapterTask]]:
        if type(first) is not RelayActor or type(second) is not RelayActor or type(spec) is not RelayInput:
            _reject()
        if (
            first.profile.project_id != second.profile.project_id
            or first.profile.session_id == second.profile.session_id
            or first.agent_id == second.agent_id
            or first.worktree_id == second.worktree_id
            or first.profile.root.is_relative_to(second.profile.root)
            or second.profile.root.is_relative_to(first.profile.root)
        ):
            _reject()
        task = self._state(first, spec.task_id)
        self._state(second, spec.task_id)
        if task["status"] != "pending" or task["version"] != spec.expected_version:
            _reject()
        left = self._workspace(first, spec.task_id)
        right = self._workspace(second, spec.task_id)
        if left["snapshot_id"] != right["snapshot_id"]:
            _reject()
        reference = {"context_id": spec.context_id, "version": spec.context_version}
        revision = self._call(first, "get_context", **reference)
        content = revision["content"]
        _bounded_text(content, 1000)
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != spec.context_sha256:
            _reject()
        key = self._key(first, spec.task_id)
        first_task = AdapterTask(
            first.profile.project_id, first.profile.session_id, spec.task_id,
            f"relay:{key}:first:launch", spec.first_instruction, spec.timeout_seconds,
        )
        second_task = AdapterTask(
            second.profile.project_id, second.profile.session_id, spec.task_id,
            f"relay:{key}:second:launch",
            f"{spec.second_instruction}\n\nApproved shared context:\n{content}", spec.timeout_seconds,
        )
        return task, reference, revision, (first_task, second_task)

    def preview_launches(
        self, first: RelayActor, second: RelayActor, spec: RelayInput, *, admin_token: str,
    ) -> tuple[LaunchReview, LaunchReview]:
        """Prepare host-private plans; conflict checks and exact consent still gate execution."""
        if type(first) is not RelayActor:
            _reject()
        self._require_relay_workers(first, second, admin_token)
        self._check_receipt_anchor(first.profile.project_id)
        _, _, _, (first_task, second_task) = self._pinned_inputs(first, second, spec)
        return (
            prepare_launch_review(first.profile, first_task, environment=first.environment),
            prepare_launch_review(second.profile, second_task, environment=second.environment),
        )

    async def run_once(
        self, first: RelayActor, second: RelayActor, spec: RelayInput, *, admin_token: str,
        _wave_key: str | None = None, _execution_deadline: float | None = None,
    ) -> RelayOutcome:
        if type(first) is not RelayActor:
            _reject()
        if _wave_key is not None and (
            type(_wave_key) is not str or len(_wave_key) != 64
            or any(c not in "0123456789abcdef" for c in _wave_key)
        ):
            _reject()
        self._require_relay_workers(first, second, admin_token)
        task, reference, revision, (first_task, second_task) = self._pinned_inputs(first, second, spec)
        _check_execution_deadline(_execution_deadline)
        self._check_receipt_anchor(first.profile.project_id, bind=True)
        key = self._key(first, spec.task_id)
        self._record(key, "incomplete", context_version=spec.context_version, wave_sha256=_wave_key)
        comparison = self._call(
            first, "compare_worktrees", left_id=first.worktree_id, right_id=second.worktree_id,
            expected_left_head=first.expected_head, expected_right_head=second.expected_head,
        )
        if comparison["mergeable"] is not True:
            self._record(
                key, "conflict", conflict_count=len(comparison["conflict_paths"]), wave_sha256=_wave_key
            )
            return RelayOutcome("conflict")
        _check_execution_deadline(_execution_deadline)
        a = await self._attempt(
            first, spec, self._claim(first, spec.task_id, task["version"], f"relay:{key}:claim-a"),
            key, "first", first_task, spec.first_reply, _execution_deadline,
        )
        self._workspace(first, spec.task_id)
        _check_execution_deadline(_execution_deadline)
        package = self._call(
            first, "submit_handoff", task_id=spec.task_id, lease_token=a["lease_token"],
            expected_version=a["version"], target_agent_id=second.agent_id,
            package={"summary": "Controlled pilot context", "context_refs": [reference]},
            request_id=f"relay:{key}:handoff",
        )
        received = self._call(second, "get_handoff", handoff_id=package["id"])
        if received != package or received["contexts"] != [revision]:
            _reject()
        _check_execution_deadline(_execution_deadline)
        accepted = self._call(
            second, "resolve_handoff", handoff_id=package["id"], expected_version=package["task_version"],
            accept=True, request_id=f"relay:{key}:accept",
        )
        current = self._state(second, spec.task_id)
        if (
            current["status"] != "pending"
            or current["version"] != accepted["task_version"]
            or current["assigned_agent_id"] != second.agent_id
        ):
            _reject()
        self._record(key, "handoff", context_version=spec.context_version, task_version=current["version"])
        _check_execution_deadline(_execution_deadline)
        b = await self._attempt(
            second, spec, self._claim(second, spec.task_id, current["version"], f"relay:{key}:claim-b"),
            key, "second", second_task, spec.second_reply, _execution_deadline,
        )
        self._workspace(first, spec.task_id)
        self._workspace(second, spec.task_id)
        _check_execution_deadline(_execution_deadline)
        submission = {
            "task_version": b["version"] + 1,
            "sender_sha256": digest(first.agent_id), "recipient_sha256": digest(second.agent_id),
            "owner_session_sha256": digest(second.profile.session_id), "wave_sha256": _wave_key,
        }
        self._record(key, "review-intent", **submission)
        _check_execution_deadline(_execution_deadline)
        reviewed = self._call(
            second, "update_task", task_id=spec.task_id, lease_token=b["lease_token"],
            expected_version=b["version"], status="review", result=_REVIEW_MARKER,
            request_id=f"relay:{key}:review",
        )
        if reviewed["version"] != submission["task_version"]:
            _reject()
        self._record(key, "ready_for_review", **submission)
        return RelayOutcome("ready_for_review")

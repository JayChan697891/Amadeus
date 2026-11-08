"""Host-only two-client relay for an isolated, explicitly approved pilot.

The host supplies prepared Core tasks, isolated managed worktrees and fixed
synthetic inputs. Each start needs a separate approval for its exact plan.
The final task is submitted for independent review through the existing Core.
Receipts never include credentials, process output, client IDs or private paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import stat
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

from agentsync.adapters.approved_launch import (
    ApprovedLaunchFactory,
    HostProfile,
    LaunchAuthority,
    _exclusive_receipt,
    client_kind,
    digest,
)
from agentsync.adapters.base import AdapterTask, _bounded_text, _identifier
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.codex import CodexAdapter, CodexResult
from agentsync.adapters.cursor import CursorAdapter
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError

_ActorAdapter = CodexAdapter | ClaudeAdapter | CursorAdapter
_REVIEW_MARKER = "Two controlled client replies matched the pilot input. Independent review pending."


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
class RelayReviewer:
    project_id: str
    session_id: str
    session_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.project_id, self.session_id, self.session_token):
            _identifier(value)


class ControlledRelay:
    """Run at most one two-stage pilot for a project task in the receipt directory.

    Keep the private receipts and the Core database across restart. Incomplete
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
        if (
            not self._scratch.is_dir()
            or not self._receipts.is_dir()
            or self._receipts == self._scratch
            or not self._receipts.is_relative_to(self._scratch)
            or not core.data_dir.resolve().is_relative_to(self._scratch)
        ):
            _reject()

    def _call(self, actor: RelayActor, operation: str, **payload: Any) -> dict[str, Any]:
        return self._core.execute(operation, {
            **payload,
            "project_id": actor.profile.project_id,
            "session_id": actor.profile.session_id,
            "session_token": actor.session_token,
        })

    def _project_state(self, actor: RelayActor, *, min_session_seconds: float = 0) -> dict[str, Any]:
        state = self._call(actor, "get_project_state")
        project_root = Path(state["project"]["root_path"]).resolve(strict=True)
        deadline = time.time() + min_session_seconds
        if not project_root.is_relative_to(self._scratch) or not any(
            session["id"] == actor.profile.session_id and session["agent_id"] == actor.agent_id
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
        view = self._call(actor, "inspect_worktree", worktree_id=actor.worktree_id)
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

    def _receipt(self, key: str, stage: str) -> Path:
        return self._receipts / f"relay-{key}-{stage}.json"

    def _record(self, key: str, stage: str, **detail: object) -> None:
        _exclusive_receipt(self._receipt(key, stage), {"stage": stage, "time": time.time(), **detail})

    def _key(self, actor: RelayActor, task_id: str) -> str:
        return digest([actor.profile.project_id, task_id])

    def _read_receipt(self, key: str, stage: str) -> dict[str, Any] | None:
        path = self._receipt(key, stage)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= 4096:
            return {}
        try:
            with path.open("rb") as file:
                raw = file.read(4097)
            if len(raw) > 4096:
                return {}
            receipt = json.loads(raw)
        except (OSError, ValueError, RecursionError):
            return {}
        return receipt if type(receipt) is dict and receipt.get("stage") == stage else {}

    def observe(self, actor: RelayActor, task_id: str) -> RelayOutcome:
        """Authenticate before observing a receipt, including after host restart."""
        task = self._state(actor, task_id)
        key = self._key(actor, task_id)
        ready = self._read_receipt(key, "ready_for_review")
        if ready is not None:
            if ready.get("task_version") == task["version"] and task["status"] == "review":
                return RelayOutcome("ready_for_review")
            return RelayOutcome("incomplete")
        conflict = self._read_receipt(key, "conflict")
        if conflict is not None:
            return RelayOutcome("conflict" if conflict else "incomplete")
        if self._read_receipt(key, "incomplete") is not None:
            return RelayOutcome("incomplete")
        return RelayOutcome("not_started")

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
        key = digest([reviewer.project_id, task_id])
        ready = self._read_receipt(key, "ready_for_review")
        if not ready:
            _reject()
        actor = next(
            (row["agent_id"] for row in project["sessions"] if row["id"] == reviewer.session_id),
            None,
        )
        if actor is None or digest(actor) in (ready.get("sender_sha256"), ready.get("recipient_sha256")):
            _reject()
        version = ready.get("task_version")
        if type(version) is not int or not any(
            row["id"] == task_id and row["status"] == "review" and row["version"] == version
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
        instruction: str,
        expected_reply: str,
    ) -> dict[str, Any]:
        prefix = f"relay:{key}:{stage}"
        lease_token = claim["lease_token"]
        active = self._call(
            actor, "update_task", task_id=spec.task_id, lease_token=lease_token,
            expected_version=claim["version"], status="running", request_id=prefix + ":running",
        )

        def renew(_: AdapterTask) -> None:
            nonlocal active
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

        factory = ApprovedLaunchFactory(
            actor.profile, environment=actor.environment, receipts=self._receipts,
            authority=actor.authority, revalidate=renew,
        )
        adapter: _ActorAdapter
        namespace = (actor.profile.project_id, actor.profile.session_id)
        if factory.client == "codex":
            adapter = CodexAdapter(*namespace, contextual_factory=factory)
        elif factory.client == "claude":
            adapter = ClaudeAdapter(*namespace, contextual_factory=factory)
        else:
            adapter = CursorAdapter(*namespace, contextual_factory=factory)
        task = AdapterTask(*namespace, spec.task_id, prefix + ":launch", instruction, spec.timeout_seconds)
        self._record(key, stage + "-dispatched", client=factory.client)
        run = await adapter.start_task(task)
        try:
            async with asyncio.timeout(spec.timeout_seconds + 2):
                while run.status in ("starting", "running"):
                    await asyncio.sleep(0.05)
                    run = await adapter.get_status(run.run_id)
                if run.status != "succeeded" or run.exit_code != 0 or not run.parent_ended:
                    self._record(
                        key, stage + "-stopped", status=run.status, timed_out=run.timed_out,
                        exit_code=run.exit_code, parent_ended=run.parent_ended,
                    )
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
            self._record(key, stage + "-stopped", status="reply_mismatch", exit_code=run.exit_code)
            _reject()
        self._record(
            key, stage + "-observed", status="expected_reply", run_sha256=digest(run.run_id),
            exit_code=run.exit_code, parent_ended=run.parent_ended,
        )
        return {**active, "lease_token": lease_token}

    async def run_once(self, first: RelayActor, second: RelayActor, spec: RelayInput) -> RelayOutcome:
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
        self._record(key, "incomplete", context_version=spec.context_version)
        comparison = self._call(
            first, "compare_worktrees", left_id=first.worktree_id, right_id=second.worktree_id,
            expected_left_head=first.expected_head, expected_right_head=second.expected_head,
        )
        if comparison["mergeable"] is not True:
            self._record(key, "conflict", conflict_count=len(comparison["conflict_paths"]))
            return RelayOutcome("conflict")
        a = await self._attempt(
            first, spec, self._claim(first, spec.task_id, task["version"], f"relay:{key}:claim-a"),
            key, "first", spec.first_instruction, spec.first_reply,
        )
        self._workspace(first, spec.task_id)
        package = self._call(
            first, "submit_handoff", task_id=spec.task_id, lease_token=a["lease_token"],
            expected_version=a["version"], target_agent_id=second.agent_id,
            package={"summary": "Controlled pilot context", "context_refs": [reference]},
            request_id=f"relay:{key}:handoff",
        )
        received = self._call(second, "get_handoff", handoff_id=package["id"])
        if received != package or received["contexts"] != [revision]:
            _reject()
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
        b = await self._attempt(
            second, spec, self._claim(second, spec.task_id, current["version"], f"relay:{key}:claim-b"),
            key, "second", f"{spec.second_instruction}\n\nApproved shared context:\n{content}", spec.second_reply,
        )
        self._workspace(first, spec.task_id)
        self._workspace(second, spec.task_id)
        reviewed = self._call(
            second, "update_task", task_id=spec.task_id, lease_token=b["lease_token"],
            expected_version=b["version"], status="review", result=_REVIEW_MARKER,
            request_id=f"relay:{key}:review",
        )
        self._record(
            key, "ready_for_review", task_version=reviewed["version"],
            sender_sha256=digest(first.agent_id), recipient_sha256=digest(second.agent_id),
        )
        return RelayOutcome("ready_for_review")

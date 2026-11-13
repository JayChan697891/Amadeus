"""Trusted host composition for one dependent proposal, never automatic acceptance.

Keep the existing Core and relay receipt directory together across restarts.
Only the invocation that exclusively writes dispatch intent may start a wave.
An intent with no observable wave is uncertain and is never retried here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, NoReturn

from agentsync.adapters.approved_launch import client_kind, digest
from agentsync.adapters.base import _bounded_text, _identifier
from agentsync.adapters.host_receipts import _ReceiptDirectory
from agentsync.controlled_relay import (
    CodexProposalInput,
    CodexProposalOutcome,
    ControlledRelay,
    ProposalContextPin,
    RelayActor,
)
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposals import proposal_paths
from agentsync.relay_queue import CodexProposalQueueItem, RelayQueue, RelayQueueOutcome


def _reject() -> NoReturn:
    raise AgentSyncError("handoff_boundary", "The host handoff no longer matches its scope.", 409)


def _seconds(value: float, maximum: float, *, zero: bool = False) -> None:
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
        or (not zero and value == 0)
        or value > maximum
    ):
        _reject()


@dataclass(frozen=True, slots=True)
class HandoffReceiver:
    project_id: str
    agent_id: str
    session_id: str
    session_token: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.project_id, self.agent_id, self.session_id, self.session_token):
            _identifier(value)

    def authentication(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "session_id": self.session_id,
            "session_token": self.session_token,
        }


@dataclass(frozen=True, slots=True)
class ProposalHandoffRequest:
    source_task_id: str
    receiver: HandoffReceiver = field(repr=False)
    request_id: str
    instruction: str = field(repr=False)
    allowed_paths: tuple[str, ...] = ("review.md",)
    execution_seconds: int = 90
    title: str = "Review the preceding proposal"

    def __post_init__(self) -> None:
        _identifier(self.source_task_id)
        _identifier(self.request_id)
        if type(self.receiver) is not HandoffReceiver:
            _reject()
        _bounded_text(self.instruction, 1500)
        _bounded_text(self.title, 200)
        if not self.instruction.strip() or not self.title.strip():
            _reject()
        if type(self.allowed_paths) is not tuple:
            _reject()
        object.__setattr__(self, "allowed_paths", proposal_paths(list(self.allowed_paths)))
        if type(self.execution_seconds) is not int or not 1 <= self.execution_seconds <= 180:
            _reject()


@dataclass(frozen=True, slots=True)
class HandoffWorkspace:
    task_id: str
    task_version: int
    worktree_id: str
    head_sha: str
    path: Path = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProposalHandoffOutcome:
    state: Literal["waiting_for_review", "not_ready", "resolved", "incomplete", "unknown"]
    pin: ProposalContextPin
    task_id: str | None = None
    worktree_id: str | None = None
    wave: RelayQueueOutcome | None = None
    verification: Literal["unverified"] = field(default="unverified", init=False)


class ProposalHandoff:
    """One host-authorized source-to-receiver operation with bounded waiting.

    The caller supplies credentials in memory and an exact-plan authority through
    the receiver factory. This class never creates accounts, approves results or
    executes candidate code. Receipt loss/corruption is not automatic recovery.
    """

    def __init__(self, core: Core, scratch: Path, receipts: Path) -> None:
        self._core = core
        self._relay = ControlledRelay(core, scratch, receipts)
        self._queue = RelayQueue(self._relay)
        self._receipts = _ReceiptDirectory(receipts)

    def _call(self, receiver: HandoffReceiver, operation: str, **payload: Any) -> dict[str, Any]:
        return self._core.execute(operation, {**payload, **receiver.authentication()})

    def _state(self, receiver: HandoffReceiver) -> dict[str, Any]:
        state = self._call(receiver, "get_project_state")
        if not any(
            s["id"] == receiver.session_id and s["agent_id"] == receiver.agent_id
            for s in state["sessions"]
        ):
            _reject()
        return state

    @staticmethod
    def _check(deadline: float) -> None:
        if asyncio.get_running_loop().time() >= deadline:
            raise AgentSyncError(
                "relay_execution_limit", "The handoff execution budget expired.", 409
            )

    def _save(self, name: str, value: dict[str, Any]) -> None:
        try:
            self._receipts.write(name, value)
        except AgentSyncError as error:
            if error.code != "attempt_already_reserved":
                raise
        if self._receipts.read(name, durable=True) != value:
            _reject()

    def _source(
        self,
        request: ProposalHandoffRequest,
        name: str,
        outcome: CodexProposalOutcome | None,
        actor: RelayActor | None,
    ) -> dict[str, Any]:
        saved = self._receipts.read(name, durable=True)
        if saved is None:
            if outcome is None:
                if actor is None or actor.profile.project_id != request.receiver.project_id:
                    _reject()
                outcome = self._relay.observe_codex_proposal(actor, request.source_task_id)
            if type(outcome) is not CodexProposalOutcome or outcome.state != "proposal_stored":
                _reject()
            if (
                outcome.context_id is None
                or outcome.context_version is None
                or outcome.content_sha256 is None
            ):
                _reject()
            pin = ProposalContextPin(
                request.source_task_id,
                outcome.context_id,
                outcome.context_version,
                outcome.content_sha256,
            )
            context = self._call(
                request.receiver,
                "get_context",
                context_id=pin.context_id,
                version=pin.context_version,
            )
            content = context["content"]
            if (
                context["project_id"] != request.receiver.project_id
                or context["kind"] != "note"
                or context["source"] != "amadeus:task-proposal"
                or hashlib.sha256(content.encode("utf-8")).hexdigest() != pin.content_sha256
                or context["author_agent_id"] == request.receiver.agent_id
            ):
                _reject()
            try:
                body = json.loads(content)
                if body["task_id"] != request.source_task_id:
                    _reject()
                tree = self._call(
                    request.receiver, "inspect_worktree", worktree_id=body["worktree_id"]
                )
            except (ValueError, KeyError, TypeError):
                _reject()
            if tree["task_id"] != request.source_task_id:
                _reject()
            saved = {
                "pin": asdict(pin),
                "producer_agent_id": context["author_agent_id"],
                "snapshot_id": tree["snapshot_id"],
            }
            self._save(name, saved)
        if not saved or set(saved) != {"pin", "producer_agent_id", "snapshot_id"}:
            _reject()
        try:
            pin = ProposalContextPin(**saved["pin"])
            _identifier(saved["producer_agent_id"])
            _identifier(saved["snapshot_id"])
        except (TypeError, KeyError):
            _reject()
        if (
            pin.producer_task_id != request.source_task_id
            or saved["producer_agent_id"] == request.receiver.agent_id
        ):
            _reject()
        if outcome is not None and (
            type(outcome) is not CodexProposalOutcome
            or outcome.state != "proposal_stored"
            or (outcome.context_id, outcome.context_version, outcome.content_sha256)
            != (pin.context_id, pin.context_version, pin.content_sha256)
        ):
            _reject()
        return saved

    async def run(
        self,
        request: ProposalHandoffRequest,
        *,
        admin_token: str,
        build_receiver: Callable[[HandoffReceiver, HandoffWorkspace], RelayActor],
        source_outcome: CodexProposalOutcome | None = None,
        source_actor: RelayActor | None = None,
        wait_seconds: float = 60,
        poll_seconds: float = 1,
        budget: float = 180,
    ) -> ProposalHandoffOutcome:
        """Resume preparation or observe an existing dispatch; never retry a launch.

        Timeout/cancellation propagates and leaves all saved intent/queue fences intact.
        It does not establish that an external client or its descendants have stopped.
        """
        if type(request) is not ProposalHandoffRequest or not callable(build_receiver):
            _reject()
        if source_actor is not None and type(source_actor) is not RelayActor:
            _reject()
        if source_outcome is not None and source_actor is not None:
            _reject()
        _seconds(wait_seconds, 900, zero=True)
        _seconds(poll_seconds, 30)
        _seconds(budget, 900)
        deadline = asyncio.get_running_loop().time() + budget
        async with asyncio.timeout_at(deadline):
            return await self._run(
                request,
                admin_token,
                build_receiver,
                source_outcome,
                source_actor,
                wait_seconds,
                poll_seconds,
                deadline,
            )

    async def _run(
        self,
        request: ProposalHandoffRequest,
        admin_token: str,
        build_receiver: Callable[[HandoffReceiver, HandoffWorkspace], RelayActor],
        source_outcome: CodexProposalOutcome | None,
        source_actor: RelayActor | None,
        wait_seconds: float,
        poll_seconds: float,
        deadline: float,
    ) -> ProposalHandoffOutcome:
        receiver = request.receiver
        self._state(receiver)
        attempts = self._relay.owner_inspect_attempts(
            receiver.project_id, request.source_task_id, admin_token=admin_token
        )
        if (
            attempts[0].state != "terminal_recorded"
            or attempts[0].status != "proposal_received"
            or attempts[0].parent_ended is not True
        ):
            _reject()
        key = digest(["proposal-handoff-v1", receiver.project_id, request.request_id])
        prefix = "handoff-" + key
        config = {
            "schema": 1,
            "source_task_id": request.source_task_id,
            "receiver_agent_id": receiver.agent_id,
            "receiver_session_id": receiver.session_id,
            "instruction_sha256": digest(request.instruction),
            "title_sha256": digest(request.title),
            "allowed_paths_sha256": digest(request.allowed_paths),
            "execution_seconds": request.execution_seconds,
        }
        self._check(deadline)
        self._save(prefix + "-config.json", config)
        source = self._source(request, prefix + "-source.json", source_outcome, source_actor)
        pin = ProposalContextPin(**source["pin"])
        intent_name = prefix + "-dispatch.json"
        existing_intent = self._receipts.read(intent_name, durable=True)
        if existing_intent is None:
            loop = asyncio.get_running_loop()
            wait_until, heartbeat_at = loop.time() + wait_seconds, float("-inf")
            while True:
                self._check(deadline)
                state = self._state(receiver)
                task = next((t for t in state["tasks"] if t["id"] == request.source_task_id), None)
                if task is None:
                    _reject()
                review = task["latest_review"]
                if task["status"] == "completed":
                    if (
                        not review
                        or review["accept"] is not True
                        or review["version"] != task["version"]
                        or review["reviewer_agent_id"] == source["producer_agent_id"]
                    ):
                        _reject()
                    break
                if loop.time() >= wait_until:
                    return ProposalHandoffOutcome("waiting_for_review", pin)
                if loop.time() - heartbeat_at >= 30:
                    self._call(receiver, "heartbeat")
                    heartbeat_at = loop.time()
                await asyncio.sleep(min(poll_seconds, max(0, wait_until - loop.time())))
        elif not existing_intent:
            _reject()
        self._check(deadline)
        task_name, tree_name = prefix + "-task.json", prefix + "-tree.json"
        stored_task, stored_tree = (
            self._receipts.read(task_name, durable=True),
            self._receipts.read(tree_name, durable=True),
        )
        if existing_intent is not None and (not stored_task or not stored_tree):
            _reject()
        if stored_task is None:
            created = self._call(
                receiver,
                "create_task",
                title=request.title,
                dependencies=[request.source_task_id],
                description="Host proposal handoff " + key,
                request_id=prefix + "-task",
            )
            stored_task = {"task_id": created["id"], "version": created["version"]}
            self._save(task_name, stored_task)
        if not stored_task or set(stored_task) != {"task_id", "version"}:
            _reject()
        self._check(deadline)
        if stored_tree is None:
            created_tree = self._call(
                receiver,
                "create_worktree",
                task_id=stored_task["task_id"],
                snapshot_id=source["snapshot_id"],
                request_id=prefix + "-tree",
            )
            stored_tree = {
                "worktree_id": created_tree["worktree_id"],
                "head_sha": created_tree["head_sha"],
            }
            self._save(tree_name, stored_tree)
        if not stored_tree or set(stored_tree) != {"worktree_id", "head_sha"}:
            _reject()
        tree = self._call(
            receiver,
            "inspect_owned_worktree",
            task_id=stored_task["task_id"],
            worktree_id=stored_tree["worktree_id"],
        )
        if (
            tree["head_sha"] != stored_tree["head_sha"]
            or tree["snapshot_id"] != source["snapshot_id"]
            or tree["dirty"]
        ):
            _reject()
        workspace = HandoffWorkspace(
            stored_task["task_id"],
            stored_task["version"],
            tree["worktree_id"],
            tree["head_sha"],
            Path(tree["path"]),
        )
        actor = build_receiver(receiver, workspace)
        if type(actor) is not RelayActor or client_kind(actor.profile) != "codex":
            _reject()
        if (
            actor.agent_id,
            actor.profile.project_id,
            actor.profile.session_id,
            actor.session_token,
            actor.worktree_id,
            actor.expected_head,
            actor.profile.root,
        ) != (
            receiver.agent_id,
            receiver.project_id,
            receiver.session_id,
            receiver.session_token,
            workspace.worktree_id,
            workspace.head_sha,
            workspace.path,
        ):
            _reject()
        wave_request = prefix + "-wave"
        intent: dict[str, object] = {
            "task_id": workspace.task_id,
            "worktree_id": workspace.worktree_id,
            "source_sha256": digest(source),
        }

        def observe() -> ProposalHandoffOutcome:
            wave = self._queue.observe(actor, wave_request)
            if wave.state == "incomplete":
                wave = self._queue.reconcile_completed(actor, wave_request, admin_token=admin_token)
            state: Literal["resolved", "incomplete", "unknown"] = (
                "resolved"
                if wave.state == "resolved"
                else "incomplete"
                if wave.state == "incomplete"
                else "unknown"
            )
            return ProposalHandoffOutcome(
                state, pin, workspace.task_id, workspace.worktree_id, wave
            )

        if existing_intent is not None:
            if existing_intent != intent:
                _reject()
            return observe()
        spec = CodexProposalInput(
            workspace.task_id,
            workspace.task_version,
            request.instruction,
            request.allowed_paths,
            request.execution_seconds,
            True,
            pin,
        )
        item = CodexProposalQueueItem(actor, spec)
        self._check(deadline)
        self._call(receiver, "heartbeat")
        preview = self._queue.preview((item,), admin_token=admin_token, parallel_limit=1)
        if preview.state != "selected":
            return ProposalHandoffOutcome(
                "not_ready", pin, workspace.task_id, workspace.worktree_id
            )
        self._check(deadline)
        await asyncio.sleep(0)
        try:
            self._receipts.write(intent_name, intent)
        except AgentSyncError as error:
            if error.code != "attempt_already_reserved":
                raise
            if self._receipts.read(intent_name, durable=True) != intent:
                _reject()
            return observe()
        if self._receipts.read(intent_name, durable=True) != intent:
            _reject()
        self._check(deadline)
        await self._queue.run_ready_once(
            (item,),
            request_id=wave_request,
            admin_token=admin_token,
            parallel_limit=1,
            expected_selection_sha256=preview.selection_sha256,
            _execution_deadline=deadline,
        )
        return observe()

"""One bounded wave of owner-prepared relays on an isolated Core project.

Only the supplied tasks can be selected. Every leg still uses the exact-plan
authority in ControlledRelay. Use the same private receipt directory across
waves and restarts. A crash, cancellation or uncertain result fences subsequent
waves until an operator reconciles the isolated workspace outside this runner.
"""

from __future__ import annotations

import asyncio
import hmac
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, NoReturn

from agentsync.adapters.approved_launch import digest
from agentsync.adapters.base import _identifier
from agentsync.controlled_relay import ControlledRelay, RelayActor, RelayInput
from agentsync.errors import AgentSyncError
from agentsync.relay_wave_journal import RelayWaveJournal
from agentsync.scheduling import plan_tasks

BatchState = Literal["not_started", "no_ready_tasks", "resolved", "incomplete"]
TaskState = Literal["ready_for_review", "conflict", "incomplete"]


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid controlled relay wave input.")


@dataclass(frozen=True, slots=True)
class RelayQueueItem:
    first: RelayActor = field(repr=False)
    second: RelayActor = field(repr=False)
    task: RelayInput
    first_capabilities: tuple[str, ...] = ()
    second_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.first) is not RelayActor
            or type(self.second) is not RelayActor
            or type(self.task) is not RelayInput
            or self.first.profile.project_id != self.second.profile.project_id
            or self.first.agent_id == self.second.agent_id
            or self.first.profile.session_id == self.second.profile.session_id
            or self.first.worktree_id == self.second.worktree_id
        ):
            _invalid()
        for required in (self.first_capabilities, self.second_capabilities):
            if type(required) is not tuple or len(required) > 16:
                _invalid()
            for value in required:
                _identifier(value)
            if len(set(required)) != len(required):
                _invalid()
        roots = (self.first.profile.root, self.second.profile.root)
        if roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):
            _invalid()


@dataclass(frozen=True, slots=True)
class RelayQueueResult:
    """Historical per-wave result; a submitted task may have been reviewed since."""

    task_id: str
    state: TaskState


@dataclass(frozen=True, slots=True)
class RelayQueueOutcome:
    state: BatchState
    tasks: tuple[RelayQueueResult, ...] = ()
    verification: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class PendingRelayWave:
    wave_id: str
    receipt_state: Literal["admitted", "incomplete"]
    outcome: RelayQueueOutcome


@dataclass(frozen=True, slots=True)
class RelayPreviewTask:
    task_id: str
    expected_version: int
    first_agent_id: str
    second_agent_id: str


@dataclass(frozen=True, slots=True)
class RelayQueuePreview:
    state: Literal["selected", "no_ready_tasks", "fenced"]
    tasks: tuple[RelayPreviewTask, ...] = ()
    selection_sha256: str | None = None
    verification: Literal["unverified"] = field(default="unverified", init=False)


def _selected_tasks(selected: Any) -> tuple[str, ...]:
    if (
        type(selected) is not list or not 1 <= len(selected) <= 4
        or any(type(task_id) is not str for task_id in selected)
        or len(set(selected)) != len(selected)
    ):
        return ()
    return tuple(selected)


def _roots(item: RelayQueueItem) -> tuple[Path, Path]:
    return item.first.profile.root, item.second.profile.root


def _selection_pin(selected: tuple[RelayQueueItem, ...]) -> str:
    """Bind the displayed selection, independently of each launch approval."""
    return digest([
        "relay-queue-selection-v1",
        [
            [
                item.task.task_id, item.task.expected_version, item.task.context_id,
                item.task.context_version, item.task.context_sha256, item.task.timeout_seconds,
                [
                    [actor.profile.project_id, actor.profile.session_id, actor.agent_id,
                     actor.worktree_id, actor.expected_head]
                    for actor in (item.first, item.second)
                ],
                item.first_capabilities, item.second_capabilities,
            ]
            for item in selected
        ],
    ])


class RelayQueue:
    """Select ready tasks by Core priority, with one task per participant.

    Capacity is local to this runner. The observed Core ownership count is a
    scheduling input, not a lock on unrelated clients. The host must coordinate
    any use of the underlying relay outside this queue. This API never reviews
    a task or turns a model response into an execution approval.
    """

    def __init__(self, relay: ControlledRelay) -> None:
        if type(relay) is not ControlledRelay:
            _invalid()
        self._relay = relay
        self._journal = RelayWaveJournal(relay._receipts)

    @staticmethod
    def _key(actor: RelayActor, request_id: str) -> str:
        if type(actor) is not RelayActor:
            _invalid()
        _identifier(request_id)
        return digest(["relay-queue-v1", actor.profile.project_id, request_id])

    @staticmethod
    def _validate_items(
        items: tuple[RelayQueueItem, ...], parallel_limit: int
    ) -> tuple[RelayQueueItem, ...]:
        if (
            type(items) is not tuple
            or not 1 <= len(items) <= 16
            or any(type(item) is not RelayQueueItem for item in items)
            or type(parallel_limit) is not int
            or not 1 <= parallel_limit <= 4
        ):
            _invalid()
        items = tuple(replace(item) for item in items)
        project_id = items[0].first.profile.project_id
        if (
            len({item.task.task_id for item in items}) != len(items)
            or any(item.first.profile.project_id != project_id for item in items)
        ):
            _invalid()
        return items

    def _legacy_fence(self, project_id: str) -> bool:
        legacy = digest(["relay-queue-active-v1", project_id])
        return self._relay._read_receipt(legacy, "wave-lock") is not None

    def _fenced(self, project_id: str, project_key: str) -> bool:
        return self._legacy_fence(project_id) or self._journal.pending(project_key) is not None

    def _check_selected(self, selected: tuple[RelayQueueItem, ...]) -> None:
        for item in selected:
            self._relay._state(item.second, item.task.task_id)
            if self._relay.observe(item.first, item.task.task_id).state != "not_started":
                raise AgentSyncError(
                    "attempt_already_reserved", "A selected task already has a relay receipt.", 409
                )

    def preview(
        self, items: tuple[RelayQueueItem, ...], *, admin_token: str, parallel_limit: int = 1
    ) -> RelayQueuePreview:
        """Preview the scheduler's current selection without reserving work or invoking a client."""
        items = self._validate_items(items, parallel_limit)
        actor = items[0].first
        project_key, snapshot = self._owner_project(actor, admin_token)
        if self._fenced(actor.profile.project_id, project_key):
            return RelayQueuePreview("fenced")
        selected = self._select(items, snapshot, parallel_limit)
        self._check_selected(selected)
        if not selected:
            return RelayQueuePreview("no_ready_tasks")
        tasks = tuple(
            RelayPreviewTask(
                item.task.task_id, item.task.expected_version, item.first.agent_id, item.second.agent_id
            )
            for item in selected
        )
        return RelayQueuePreview("selected", tasks, _selection_pin(selected))

    def observe(self, actor: RelayActor, request_id: str) -> RelayQueueOutcome:
        """Read the saved wave outcome after reauthenticating in Core."""
        key = self._key(actor, request_id)
        self._relay._project_state(actor)
        project_key = digest(actor.profile.project_id)
        saved = self._journal.get(project_key, key)
        if saved is not None:
            status, selected, rows = saved
            outcome = self._outcome(selected, rows)
            if status == "admitted" or status != outcome.state:
                return RelayQueueOutcome("incomplete")
            return outcome
        initial = self._relay._read_receipt(key, "wave-admitted")
        final = self._relay._read_receipt(key, "wave-observed")
        if initial is None and final is None:
            return RelayQueueOutcome("not_started")
        if not initial or not final:
            return RelayQueueOutcome("incomplete")
        return self._outcome(initial.get("task_ids"), final.get("tasks"))

    def reconcile_completed(
        self, actor: RelayActor, request_id: str, *, admin_token: str
    ) -> RelayQueueOutcome:
        """Recover only a wave whose same-wave terminal receipts all survived.

        This never restarts a client or frees a fence based on a missing receipt.
        A submission must match its recorded Core version or the exact next
        version with an accepted review from a third identity.
        """
        key = self._key(actor, request_id)
        project_key, _ = self._owner_project(actor, admin_token)
        saved = self._journal.get(project_key, key)
        if saved is None or saved[0] != "admitted":
            return self.observe(actor, request_id)
        return self._reconcile_admitted(actor, project_key, key, saved[1])

    def observe_pending(self, actor: RelayActor, *, admin_token: str) -> PendingRelayWave | None:
        """Discover the current project fence when the original request ID was lost."""
        project_key, _ = self._owner_project(actor, admin_token)
        saved = self._journal.pending(project_key)
        if saved is None:
            if self._legacy_fence(actor.profile.project_id):
                raise AgentSyncError(
                    "wave_incomplete", "A legacy relay wave still holds the fence.", 409
                )
            return None
        key, state, selected, rows = saved
        if state == "admitted":
            tasks = tuple(
                RelayQueueResult(task_id, "incomplete") for task_id in _selected_tasks(selected)
            )
            return PendingRelayWave(key, "admitted", RelayQueueOutcome("incomplete", tasks))
        outcome = self._outcome(selected, rows)
        if outcome.state != "incomplete":
            outcome = RelayQueueOutcome("incomplete")
        return PendingRelayWave(key, "incomplete", outcome)

    def reconcile_pending(
        self, actor: RelayActor, *, admin_token: str, expected_wave_id: str
    ) -> RelayQueueOutcome:
        """Reconcile only the exact observed wave, never a newer project fence."""
        if type(expected_wave_id) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_wave_id):
            _invalid()
        project_key, _ = self._owner_project(actor, admin_token)
        saved = self._journal.get(project_key, expected_wave_id)
        if saved is None:
            raise AgentSyncError("not_found", "The relay wave was not found.", 404)
        state, selected, rows = saved
        if state == "admitted":
            return self._reconcile_admitted(actor, project_key, expected_wave_id, selected)
        outcome = self._outcome(selected, rows)
        return outcome if outcome.state == state else RelayQueueOutcome("incomplete")

    def _owner_project(self, actor: RelayActor, admin_token: str) -> tuple[str, dict[str, Any]]:
        if type(actor) is not RelayActor:
            _invalid()
        self._relay._authorize_owner(actor, admin_token)
        snapshot = self._relay._project_state(actor)
        project_id = actor.profile.project_id
        return digest(project_id), snapshot

    def _reconcile_admitted(
        self, actor: RelayActor, project_key: str, key: str, selected: Any
    ) -> RelayQueueOutcome:
        task_ids = _selected_tasks(selected)
        if not task_ids:
            return RelayQueueOutcome("incomplete")
        results: list[dict[str, str]] = []
        for task_id in task_ids:
            state = self._relay._wave_terminal_state(actor, task_id, key)
            if state is None:
                return RelayQueueOutcome("incomplete")
            results.append({"task_id": task_id, "state": state})
        self._journal.record(project_key, key, incomplete=False, results=results)
        return self._outcome(list(task_ids), results)

    @staticmethod
    def _outcome(selected: Any, rows: Any) -> RelayQueueOutcome:
        if type(selected) is not list or type(rows) is not list or not 1 <= len(rows) <= 4:
            return RelayQueueOutcome("incomplete")
        results = []
        for row in rows:
            if type(row) is not dict or set(row) != {"task_id", "state"}:
                return RelayQueueOutcome("incomplete")
            state = row["state"]
            if type(row["task_id"]) is not str or type(state) is not str or state not in (
                "ready_for_review", "conflict", "incomplete"
            ):
                return RelayQueueOutcome("incomplete")
            results.append(RelayQueueResult(row["task_id"], state))
        if [result.task_id for result in results] != selected:
            return RelayQueueOutcome("incomplete")
        incomplete = any(result.state == "incomplete" for result in results)
        return RelayQueueOutcome("incomplete" if incomplete else "resolved", tuple(results))

    def _select(
        self, items: tuple[RelayQueueItem, ...], snapshot: dict[str, Any], limit: int
    ) -> tuple[RelayQueueItem, ...]:
        project_id = snapshot["project"]["id"]
        now = time.time()
        sessions = {row["id"]: row for row in snapshot["sessions"]}
        capabilities = {row["id"]: set(row["capabilities"]) for row in snapshot["agents"]}
        tasks = {row["id"]: row for row in snapshot["tasks"]}
        active = [row for row in tasks.values() if row["status"] in ("claimed", "running", "blocked")]
        busy = {sessions[row["owner_session_id"]]["agent_id"] for row in active}
        budget = max(0, limit - len(active))
        if not budget:
            return ()
        ready: dict[str, dict[str, int]] = {}
        eligible = []
        for item in items:
            actors = (item.first, item.second)
            if any(
                actor.agent_id in busy
                or not (session := sessions.get(actor.profile.session_id))
                or session["agent_id"] != actor.agent_id
                or session["online"] is not True
                or session["expires_at"] <= now + item.task.timeout_seconds + 2
                for actor in actors
            ):
                continue
            if not set(item.first_capabilities) <= capabilities[item.first.agent_id]:
                continue
            if not set(item.second_capabilities) <= capabilities[item.second.agent_id]:
                continue
            if item.first.agent_id not in ready:
                scoped = tuple(
                    candidate.task.task_id for candidate in items
                    if candidate.first.agent_id == item.first.agent_id
                    and candidate.task.task_id in tasks
                )
                plan = plan_tasks(
                    {"tasks": snapshot["tasks"]}, project_id=project_id,
                    agent_id=item.first.agent_id, now=now, limit=100,
                    candidate_task_ids=scoped,
                )
                ready[item.first.agent_id] = {
                    candidate.task_id: candidate.expected_version for candidate in plan.candidates
                }
            if ready[item.first.agent_id].get(item.task.task_id) == item.task.expected_version:
                eligible.append(item)
        eligible.sort(key=lambda item: (
            -tasks[item.task.task_id]["priority"],
            tasks[item.task.task_id]["created_at"],
            item.task.task_id,
        ))
        selected: list[RelayQueueItem] = []
        roots: list[Path] = []
        for item in eligible:
            if len(selected) >= budget:
                break
            participants = {item.first.agent_id, item.second.agent_id}
            if participants & busy or any(
                root.is_relative_to(previous) or previous.is_relative_to(root)
                for root in _roots(item)
                for previous in roots
            ):
                continue
            selected.append(item)
            busy.update(participants)
            roots.extend(_roots(item))
        return tuple(selected)

    async def run_ready_once(
        self, items: tuple[RelayQueueItem, ...], *, request_id: str, admin_token: str,
        parallel_limit: int = 1, expected_selection_sha256: str | None = None,
    ) -> RelayQueueOutcome:
        """Run at most one wave, optionally bound to a previously previewed selection."""
        items = self._validate_items(items, parallel_limit)
        if expected_selection_sha256 is not None and (
            type(expected_selection_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_selection_sha256) is None
        ):
            _invalid()
        actor = items[0].first
        project_id = actor.profile.project_id
        key = self._key(actor, request_id)
        project_key, snapshot = self._owner_project(actor, admin_token)
        if (
            self._journal.get(project_key, key) is not None
            or self._relay._read_receipt(key, "wave-admitted") is not None
        ):
            raise AgentSyncError("attempt_already_reserved", "This relay wave already has a receipt.", 409)
        if self._fenced(project_id, project_key):
            raise AgentSyncError("wave_incomplete", "An earlier relay wave still holds the project fence.", 409)
        selected = self._select(items, snapshot, parallel_limit)
        if expected_selection_sha256 is not None and (
            not selected or not hmac.compare_digest(expected_selection_sha256, _selection_pin(selected))
        ):
            raise AgentSyncError("selection_changed", "The previewed relay selection changed.", 409)
        if not selected:
            return RelayQueueOutcome("no_ready_tasks")
        self._check_selected(selected)
        self._journal.admit(project_key, key, tuple(item.task.task_id for item in selected))

        async def run(item: RelayQueueItem) -> RelayQueueResult:
            try:
                outcome = await self._relay.run_once(
                    item.first, item.second, item.task, admin_token=admin_token, _wave_key=key,
                )
            except Exception:
                return RelayQueueResult(item.task.task_id, "incomplete")
            if outcome.state == "ready_for_review":
                return RelayQueueResult(item.task.task_id, "ready_for_review")
            if outcome.state == "conflict":
                return RelayQueueResult(item.task.task_id, "conflict")
            return RelayQueueResult(item.task.task_id, "incomplete")

        results = tuple(await asyncio.gather(*(run(item) for item in selected)))
        incomplete = any(result.state == "incomplete" for result in results)
        self._journal.record(
            project_key,
            key,
            incomplete=incomplete,
            results=[{"task_id": row.task_id, "state": row.state} for row in results],
        )
        return RelayQueueOutcome("incomplete" if incomplete else "resolved", results)

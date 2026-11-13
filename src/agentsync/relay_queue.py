"""One bounded wave of owner-prepared relays on an isolated Core project.

Only the supplied tasks can be selected. Every leg still uses the exact-plan
authority in ControlledRelay. Use the same private receipt directory across
waves and restarts. A crash, cancellation or uncertain result fences subsequent
waves until an operator reconciles the isolated workspace outside this runner.
"""

from __future__ import annotations

import asyncio
import hmac
import math
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import Any, Literal, NoReturn, cast

from agentsync.adapters.approved_launch import (
    ClientKind,
    _check_execution_deadline,
    client_kind,
    digest,
    prepare_launch_review,
)
from agentsync.adapters.base import _identifier
from agentsync.controlled_relay import (
    CodexProposalInput,
    ControlledRelay,
    ProposalReviewInput,
    RelayActor,
    RelayInput,
)
from agentsync.errors import AgentSyncError
from agentsync.relay_wave_journal import JournalState, RelayWaveJournal
from agentsync.scheduling import plan_tasks

BatchState = Literal["not_started", "no_ready_tasks", "resolved", "incomplete"]
TaskState = Literal["ready_for_review", "conflict", "incomplete"]
_TerminalReader = Callable[[str, str], Literal["ready_for_review", "conflict"] | None]
_FAILURE_CODES = frozenset(
    {
        "attempt_already_reserved",
        "forbidden",
        "idempotency_conflict",
        "lease_expired",
        "not_found",
        "receipt_unavailable",
        "relay_boundary",
        "relay_operation_failed",
        "relay_outcome_unknown",
        "relay_execution_limit",
        "session_expired",
        "storage_error",
        "unauthorized",
        "version_conflict",
        "workspace_boundary",
    }
)


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid controlled relay wave input.")


def _validate_capabilities(required: tuple[str, ...]) -> None:
    if type(required) is not tuple or len(required) > 16:
        _invalid()
    for value in required:
        _identifier(value)
    if len(set(required)) != len(required):
        _invalid()


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
        _validate_capabilities(self.first_capabilities)
        _validate_capabilities(self.second_capabilities)
        roots = (self.first.profile.root, self.second.profile.root)
        if roots[0].is_relative_to(roots[1]) or roots[1].is_relative_to(roots[0]):
            _invalid()


@dataclass(frozen=True, slots=True)
class CodexProposalQueueItem:
    """One prepared read-only Codex launch with explicit submission for Core review."""

    first: RelayActor = field(repr=False)
    task: CodexProposalInput
    first_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.first) is not RelayActor
            or type(self.task) is not CodexProposalInput
            or client_kind(self.first.profile) != "codex"
            or self.task.submit_for_review is not True
        ):
            _invalid()
        _validate_capabilities(self.first_capabilities)


@dataclass(frozen=True, slots=True)
class ProposalReviewQueueItem:
    """One prepared reviewer for a dependent verified-source task."""

    first: RelayActor = field(repr=False)
    task: ProposalReviewInput
    first_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.first) is not RelayActor or type(self.task) is not ProposalReviewInput:
            _invalid()
        _validate_capabilities(self.first_capabilities)


_QueueItem = RelayQueueItem | CodexProposalQueueItem | ProposalReviewQueueItem


def _participants(item: _QueueItem) -> tuple[tuple[RelayActor, tuple[str, ...]], ...]:
    first = (item.first, item.first_capabilities)
    if isinstance(item, RelayQueueItem):
        return first, (item.second, item.second_capabilities)
    return (first,)


@dataclass(frozen=True, slots=True)
class RelayQueueResult:
    """Historical per-wave result; a submitted task may have been reviewed since."""

    task_id: str
    state: TaskState
    failure_code: str | None = None

    def _receipt_row(self) -> dict[str, str]:
        row = {"task_id": self.task_id, "state": self.state}
        if self.failure_code is not None:
            row["failure_code"] = self.failure_code
        return row


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
class RelayWaveHistoryEntry:
    wave_id: str
    journal_state: JournalState
    outcome: RelayQueueOutcome


@dataclass(frozen=True, slots=True)
class RelayWaveHistoryPage:
    waves: tuple[RelayWaveHistoryEntry, ...]
    next_before: str | None = None


@dataclass(frozen=True, slots=True)
class RelayPreviewTask:
    task_id: str
    expected_version: int
    first_agent_id: str
    second_agent_id: str
    first_client: ClientKind
    second_client: ClientKind


@dataclass(frozen=True, slots=True)
class CodexProposalPreviewTask:
    task_id: str
    expected_version: int
    agent_id: str
    client: Literal["codex"] = field(default="codex", init=False)


@dataclass(frozen=True, slots=True)
class ProposalReviewPreviewTask:
    task_id: str
    expected_version: int
    agent_id: str
    client: ClientKind


@dataclass(frozen=True, slots=True)
class RelayQueuePreview:
    state: Literal["selected", "no_ready_tasks", "fenced"]
    tasks: tuple[RelayPreviewTask | CodexProposalPreviewTask | ProposalReviewPreviewTask, ...] = ()
    selection_sha256: str | None = None
    verification: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class RelaySequenceOutcome:
    reason: Literal["no_ready_tasks", "wave_limit", "time_limit", "execution_limit", "incomplete"]
    waves: tuple[RelayQueueOutcome, ...]
    verification: Literal["unverified"] = field(default="unverified", init=False)


def _selected_tasks(selected: Any) -> tuple[str, ...]:
    if (
        type(selected) is not list
        or not 1 <= len(selected) <= 4
        or any(type(task_id) is not str for task_id in selected)
        or len(set(selected)) != len(selected)
    ):
        return ()
    return tuple(selected)


def _selection_pin(selected: tuple[_QueueItem, ...]) -> str:
    """Bind the displayed selection, independently of each launch approval."""
    rows: list[list[object]] = []
    for item in selected:
        actors = [
            [
                actor.profile.project_id,
                actor.profile.session_id,
                actor.agent_id,
                actor.worktree_id,
                actor.expected_head,
                client_kind(actor.profile),
                actor.profile.expected_cli_version,
                actor.profile.expected_binary_sha256,
            ]
            for actor, _ in _participants(item)
        ]
        if isinstance(item, RelayQueueItem):
            rows.append(
                [
                    item.task.task_id,
                    item.task.expected_version,
                    item.task.context_id,
                    item.task.context_version,
                    item.task.context_sha256,
                    item.task.timeout_seconds,
                    actors,
                    item.first_capabilities,
                    item.second_capabilities,
                ]
            )
        else:
            rows.append(
                [
                    "proposal-review"
                    if isinstance(item, ProposalReviewQueueItem)
                    else "codex-proposal",
                    item.task.task_id,
                    item.task.expected_version,
                    digest(item.task.instruction),
                    item.task.allowed_paths,
                    item.task.timeout_seconds,
                    item.task.submit_for_review,
                    actors,
                    item.first_capabilities,
                    *([asdict(item.task.input_context)] if item.task.input_context else []),
                ]
            )
    return digest(["relay-queue-selection-v1", rows])


class RelayQueue:
    """Select ready tasks by Core priority, with one task per participant.

    A task may offer up to four prepared alternatives with identical inputs and role
    requirements. Equal-priority alternatives are considered in supplied order.
    Capacity is local to this runner. The observed Core ownership count is a
    scheduling input, not a lock on unrelated clients. The host must coordinate
    any use of the underlying relay outside this queue. This API never reviews
    a task or turns a model response into an execution approval.
    """

    def __init__(self, relay: ControlledRelay) -> None:
        if type(relay) is not ControlledRelay:
            _invalid()
        self._relay = relay
        relay._receipt_store.check()
        self._journal = RelayWaveJournal(relay._receipts)
        relay._receipt_store.check()

    @staticmethod
    def _key(actor: RelayActor, request_id: str) -> str:
        if type(actor) is not RelayActor:
            _invalid()
        _identifier(request_id)
        return digest(["relay-queue-v1", actor.profile.project_id, request_id])

    @staticmethod
    def _validate_items(
        items: tuple[_QueueItem, ...], parallel_limit: int
    ) -> tuple[_QueueItem, ...]:
        if (
            type(items) is not tuple
            or not 1 <= len(items) <= 16
            or any(
                type(item) not in (RelayQueueItem, CodexProposalQueueItem, ProposalReviewQueueItem)
                for item in items
            )
            or type(parallel_limit) is not int
            or not 1 <= parallel_limit <= 4
        ):
            _invalid()
        items = tuple(replace(item) for item in items)
        project_id = items[0].first.profile.project_id
        specifications: dict[str, _QueueItem] = {}
        alternatives: dict[str, set[tuple[str, ...]]] = {}
        for item in items:
            if item.first.profile.project_id != project_id:
                _invalid()
            task_id = item.task.task_id
            first_option = specifications.setdefault(task_id, item)
            options = alternatives.setdefault(task_id, set())
            participants = _participants(item)
            agent_ids = tuple(actor.agent_id for actor, _ in participants)
            if (
                type(item) is not type(first_option)
                or item.task != first_option.task
                or tuple(caps for _, caps in participants)
                != tuple(caps for _, caps in _participants(first_option))
                or agent_ids in options
                or len(options) >= 4
            ):
                _invalid()
            options.add(agent_ids)
        return items

    def _legacy_fence(self, project_id: str) -> bool:
        legacy = digest(["relay-queue-active-v1", project_id])
        return self._relay._read_receipt(legacy, "wave-lock") is not None

    def _fenced(self, project_id: str, project_key: str) -> bool:
        return self._legacy_fence(project_id) or self._journal.pending(project_key) is not None

    def _check_journal_anchor(self, project_key: str, *, bind: bool = False) -> None:
        anchors = self._relay._receipt_anchors
        name = f"controlled-relay-wave-{project_key}.json"
        saved = anchors.read(name, durable=bind)
        if saved is None and not bind:
            return
        identity = self._journal.location_identity(initialize=saved is None)
        expected: dict[str, object] = {
            "schema_version": 1,
            "journal_sha256": digest([self._relay._receipt_store.location_pin(), *identity]),
        }
        if saved is None:
            try:
                anchors.write(name, expected)
            except AgentSyncError as error:
                if error.code != "attempt_already_reserved":
                    raise
            saved = anchors.read(name, durable=True)
        if not saved or type(saved.get("schema_version")) is not int or saved != expected:
            raise AgentSyncError(
                "wave_journal_unavailable",
                "The wave journal does not match its saved identity.",
                409,
            )

    def _check_selected(self, selected: tuple[_QueueItem, ...]) -> None:
        for item in selected:
            if isinstance(item, RelayQueueItem):
                self._relay._state(item.second, item.task.task_id)
            for actor, _ in _participants(item):
                self._relay._check_worktree_owner(actor, item.task.task_id)
            if self._relay.observe(item.first, item.task.task_id).state != "not_started":
                raise AgentSyncError(
                    "attempt_already_reserved", "A selected task already has a relay receipt.", 409
                )

    def _check_review_input(
        self, item: ProposalReviewQueueItem, admin_token: str, wave_key: str
    ) -> None:
        task = self._relay._single_codex_task(item.first, item.task, admin_token, wave_key=wave_key)
        prepare_launch_review(item.first.profile, task, environment=item.first.environment)

    def preview(
        self, items: tuple[_QueueItem, ...], *, admin_token: str, parallel_limit: int = 1
    ) -> RelayQueuePreview:
        """Preview the scheduler's current selection without reserving work or invoking a client."""
        items = self._validate_items(items, parallel_limit)
        actor = items[0].first
        project_key, snapshot, workers = self._owner_candidate_snapshot(items, admin_token)
        if self._fenced(actor.profile.project_id, project_key):
            return RelayQueuePreview("fenced")
        selected = self._select(items, snapshot, workers, parallel_limit)
        self._check_selected(selected)
        if not selected:
            return RelayQueuePreview("no_ready_tasks")
        tasks = tuple(
            RelayPreviewTask(
                item.task.task_id,
                item.task.expected_version,
                item.first.agent_id,
                item.second.agent_id,
                client_kind(item.first.profile),
                client_kind(item.second.profile),
            )
            if isinstance(item, RelayQueueItem)
            else ProposalReviewPreviewTask(
                item.task.task_id,
                item.task.expected_version,
                item.first.agent_id,
                client_kind(item.first.profile),
            )
            if isinstance(item, ProposalReviewQueueItem)
            else CodexProposalPreviewTask(
                item.task.task_id, item.task.expected_version, item.first.agent_id
            )
            for item in selected
        )
        return RelayQueuePreview("selected", tasks, _selection_pin(selected))

    def observe(self, actor: RelayActor, request_id: str) -> RelayQueueOutcome:
        """Read the saved wave outcome after reauthenticating in Core."""
        key = self._key(actor, request_id)
        self._relay._project_state(actor)
        self._relay._check_receipt_anchor(actor.profile.project_id)
        project_key = digest(actor.profile.project_id)
        self._check_journal_anchor(project_key)
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
        version with an accepted or rejected review from a third identity.
        """
        key = self._key(actor, request_id)
        project_key, _ = self._owner_project(actor, admin_token)
        saved = self._journal.get(project_key, key)
        if saved is None or saved[0] not in ("admitted", "incomplete"):
            return self.observe(actor, request_id)
        return self._reconcile_open(
            project_key,
            key,
            saved,
            partial(self._relay._wave_terminal_state, actor),
        )

    def observe_pending(self, actor: RelayActor, *, admin_token: str) -> PendingRelayWave | None:
        """Discover the current project fence when the original request ID was lost."""
        project_key, _ = self._owner_project(actor, admin_token)
        return self._observe_pending(actor.profile.project_id, project_key)

    def owner_observe_pending(
        self, project_id: str, *, admin_token: str
    ) -> PendingRelayWave | None:
        """Inspect a project fence when agent sessions have expired or are unavailable."""
        project_key = self._owner_journal_key(project_id, admin_token)
        return self._observe_pending(project_id, project_key)

    def _observe_pending(self, project_id: str, project_key: str) -> PendingRelayWave | None:
        saved = self._journal.pending(project_key)
        if saved is None:
            if self._legacy_fence(project_id):
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

    def history(
        self,
        actor: RelayActor,
        *,
        admin_token: str,
        limit: int = 16,
        before: str | None = None,
    ) -> RelayWaveHistoryPage:
        """Read this project's journal, newest first, without knowing original request IDs."""
        self._validate_history_page(limit, before)
        project_key, _ = self._owner_project(actor, admin_token)
        return self._history(project_key, limit=limit, before=before)

    def owner_history(
        self,
        project_id: str,
        *,
        admin_token: str,
        limit: int = 16,
        before: str | None = None,
    ) -> RelayWaveHistoryPage:
        """Read the project's journal without a live agent session or client profile."""
        self._validate_history_page(limit, before)
        project_key = self._owner_journal_key(project_id, admin_token)
        return self._history(project_key, limit=limit, before=before)

    @staticmethod
    def _validate_history_page(limit: int, before: str | None) -> None:
        if (
            type(limit) is not int
            or not 1 <= limit <= 32
            or (
                before is not None
                and (type(before) is not str or re.fullmatch(r"[0-9a-f]{64}", before) is None)
            )
        ):
            _invalid()

    def _history(self, project_key: str, *, limit: int, before: str | None) -> RelayWaveHistoryPage:
        rows, next_before = self._journal.history(project_key, limit=limit, before=before)
        entries = []
        for key, state, selected, results in rows:
            outcome = self._outcome(selected, results)
            if state == "admitted":
                outcome = RelayQueueOutcome(
                    "incomplete",
                    tuple(
                        RelayQueueResult(task_id, "incomplete")
                        for task_id in _selected_tasks(selected)
                    ),
                )
            elif outcome.state != state:
                outcome = RelayQueueOutcome("incomplete")
            entries.append(RelayWaveHistoryEntry(key, state, outcome))
        return RelayWaveHistoryPage(tuple(entries), next_before)

    def reconcile_pending(
        self, actor: RelayActor, *, admin_token: str, expected_wave_id: str
    ) -> RelayQueueOutcome:
        """Reconcile only the exact observed wave, never a newer project fence."""
        if type(expected_wave_id) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_wave_id):
            _invalid()
        project_key, _ = self._owner_project(actor, admin_token)
        return self._reconcile_pending_wave(
            project_key,
            expected_wave_id,
            partial(self._relay._wave_terminal_state, actor),
        )

    def reconcile_pending_from_session(
        self,
        project_id: str,
        *,
        session_id: str,
        session_token: str,
        admin_token: str,
        expected_wave_id: str,
    ) -> RelayQueueOutcome:
        """Reconcile saved receipts with an enrolled session and owner authorization."""
        if type(expected_wave_id) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_wave_id):
            _invalid()
        for value in (project_id, session_id, session_token):
            _identifier(value)
        self._relay._authorize_project_owner(project_id, admin_token)
        snapshot = self._relay._session_project_state(project_id, session_id, session_token)
        project_key = self._checked_journal_key(project_id)
        tasks = {task["id"]: task for task in snapshot["tasks"]}

        def context(context_id: str, version: int) -> dict[str, Any]:
            return self._relay._core.execute(
                "get_context",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "session_token": session_token,
                    "context_id": context_id,
                    "version": version,
                },
            )

        def terminal(task_id: str, wave_id: str) -> Literal["ready_for_review", "conflict"] | None:
            task = tasks.get(task_id)
            return (
                None
                if task is None
                else self._relay._wave_terminal_from_task(project_id, task, wave_id, context)
            )

        return self._reconcile_pending_wave(project_key, expected_wave_id, terminal)

    def _reconcile_pending_wave(
        self,
        project_key: str,
        expected_wave_id: str,
        read_terminal: _TerminalReader,
    ) -> RelayQueueOutcome:
        saved = self._journal.get(project_key, expected_wave_id)
        if saved is None:
            raise AgentSyncError("not_found", "The relay wave was not found.", 404)
        state, selected, rows = saved
        if state in ("admitted", "incomplete"):
            return self._reconcile_open(project_key, expected_wave_id, saved, read_terminal)
        outcome = self._outcome(selected, rows)
        return outcome if outcome.state == state else RelayQueueOutcome("incomplete")

    def _owner_project(self, actor: RelayActor, admin_token: str) -> tuple[str, dict[str, Any]]:
        if type(actor) is not RelayActor:
            _invalid()
        self._relay._authorize_owner(actor, admin_token)
        snapshot = self._relay._project_state(actor)
        return self._checked_journal_key(actor.profile.project_id), snapshot

    def _owner_journal_key(self, project_id: str, admin_token: str) -> str:
        _identifier(project_id)
        self._relay._authorize_project_owner(project_id, admin_token)
        return self._checked_journal_key(project_id)

    def _checked_journal_key(self, project_id: str) -> str:
        self._relay._check_receipt_anchor(project_id)
        project_key = digest(project_id)
        self._check_journal_anchor(project_key)
        return project_key

    def _owner_candidate_snapshot(
        self,
        items: tuple[_QueueItem, ...],
        admin_token: str,
    ) -> tuple[str, dict[str, Any], set[str]]:
        first = items[0].first
        project = first.profile.project_id
        actors = {actor.agent_id for item in items for actor, _ in _participants(item)}
        workers = self._relay._owner_worker_ids(project, actors, admin_token)
        self._relay._check_receipt_anchor(project)
        project_key = digest(project)
        seen: set[str] = set()
        for item in items:
            for actor, _ in _participants(item):
                if workers and actor.agent_id not in workers:
                    continue
                session_id = actor.profile.session_id
                if session_id in seen:
                    continue
                seen.add(session_id)
                try:
                    snapshot = self._relay._project_state(actor)
                except AgentSyncError as error:
                    if error.code != "session_expired":
                        raise
                else:
                    self._check_journal_anchor(project_key)
                    return project_key, snapshot, workers
        raise AgentSyncError("session_expired", "No prepared relay session remains valid.", 401)

    def _reconcile_open(
        self,
        project_key: str,
        key: str,
        saved: tuple[str, Any, Any],
        read_terminal: _TerminalReader,
    ) -> RelayQueueOutcome:
        _, selected, rows = saved
        task_ids = _selected_tasks(selected)
        prior = self._outcome(selected, rows)
        if prior.state != "incomplete":
            return RelayQueueOutcome("incomplete")
        if not task_ids:
            return prior
        results: list[dict[str, str]] = []
        for task_id in task_ids:
            state = read_terminal(task_id, key)
            if state is None:
                return prior
            results.append({"task_id": task_id, "state": state})
        self._journal.record(project_key, key, incomplete=False, results=results, reconciled=True)
        return self._outcome(list(task_ids), results)

    @staticmethod
    def _outcome(selected: Any, rows: Any) -> RelayQueueOutcome:
        if type(selected) is not list or type(rows) is not list or not 1 <= len(rows) <= 4:
            return RelayQueueOutcome("incomplete")
        results = []
        for row in rows:
            if type(row) is not dict or set(row) not in (
                {"task_id", "state"},
                {"task_id", "state", "failure_code"},
            ):
                return RelayQueueOutcome("incomplete")
            state = row["state"]
            if (
                type(row["task_id"]) is not str
                or type(state) is not str
                or state not in ("ready_for_review", "conflict", "incomplete")
            ):
                return RelayQueueOutcome("incomplete")
            failure = row.get("failure_code")
            if "failure_code" in row and (
                state != "incomplete" or type(failure) is not str or failure not in _FAILURE_CODES
            ):
                return RelayQueueOutcome("incomplete")
            results.append(RelayQueueResult(row["task_id"], cast(TaskState, state), failure))
        if [result.task_id for result in results] != selected:
            return RelayQueueOutcome("incomplete")
        incomplete = any(result.state == "incomplete" for result in results)
        return RelayQueueOutcome("incomplete" if incomplete else "resolved", tuple(results))

    def _select(
        self,
        items: tuple[_QueueItem, ...],
        snapshot: dict[str, Any],
        workers: set[str],
        limit: int,
    ) -> tuple[_QueueItem, ...]:
        project_id = snapshot["project"]["id"]
        now = time.time()
        sessions = {row["id"]: row for row in snapshot["sessions"]}
        capabilities = {row["id"]: set(row["capabilities"]) for row in snapshot["agents"]}
        tasks = {row["id"]: row for row in snapshot["tasks"]}
        active = [
            row for row in tasks.values() if row["status"] in ("claimed", "running", "blocked")
        ]
        busy = {sessions[row["owner_session_id"]]["agent_id"] for row in active}
        budget = max(0, limit - len(active))
        if not budget:
            return ()
        ready: dict[str, dict[str, int]] = {}
        eligible = []
        for item in items:
            if any(
                actor.agent_id not in workers
                or actor.agent_id in busy
                or not (session := sessions.get(actor.profile.session_id))
                or session["agent_id"] != actor.agent_id
                or session["online"] is not True
                or session["expires_at"] <= now + item.task.timeout_seconds + 2
                or not set(required) <= capabilities[actor.agent_id]
                for actor, required in _participants(item)
            ):
                continue
            if item.first.agent_id not in ready:
                scoped = tuple(
                    dict.fromkeys(
                        candidate.task.task_id
                        for candidate in items
                        if candidate.first.agent_id == item.first.agent_id
                        and candidate.task.task_id in tasks
                    )
                )
                plan = plan_tasks(
                    {"tasks": snapshot["tasks"]},
                    project_id=project_id,
                    agent_id=item.first.agent_id,
                    now=now,
                    limit=100,
                    candidate_task_ids=scoped,
                )
                ready[item.first.agent_id] = {
                    candidate.task_id: candidate.expected_version for candidate in plan.candidates
                }
            if ready[item.first.agent_id].get(item.task.task_id) == item.task.expected_version:
                eligible.append(item)
        eligible.sort(
            key=lambda item: (
                -tasks[item.task.task_id]["priority"],
                tasks[item.task.task_id]["created_at"],
                item.task.task_id,
            )
        )
        grouped: dict[str, list[_QueueItem]] = {}
        for item in eligible:
            grouped.setdefault(item.task.task_id, []).append(item)
        groups = tuple(grouped.values())

        def select_options(
            start: int,
            slots: int,
            occupied: set[str],
            roots: tuple[Path, ...],
        ) -> tuple[tuple[int, ...], tuple[_QueueItem, ...]]:
            if not slots:
                return (), ()
            for index in range(start, len(groups)):
                best_rank: tuple[int, ...] | None = None
                best: tuple[tuple[int, ...], tuple[_QueueItem, ...]] = ((), ())
                for item in groups[index]:
                    actors = _participants(item)
                    participants = {actor.agent_id for actor, _ in actors}
                    item_roots = tuple(actor.profile.root for actor, _ in actors)
                    if participants & occupied or any(
                        root.is_relative_to(previous) or previous.is_relative_to(root)
                        for root in item_roots
                        for previous in roots
                    ):
                        continue
                    tail_ranks, tail = select_options(
                        index + 1, slots - 1, occupied | participants, roots + item_roots
                    )
                    ranks = (index, *tail_ranks)
                    # Keep task priority first, then prefer filling earlier remaining slots.
                    padded = ranks + (len(groups),) * (slots - len(ranks))
                    if best_rank is None or padded < best_rank:
                        best_rank, best = padded, (ranks, (item, *tail))
                if best_rank is not None:
                    return best
            return (), ()

        return select_options(0, budget, busy, ())[1]

    async def run_ready_once(
        self,
        items: tuple[_QueueItem, ...],
        *,
        request_id: str,
        admin_token: str,
        parallel_limit: int = 1,
        expected_selection_sha256: str | None = None,
        _execution_deadline: float | None = None,
    ) -> RelayQueueOutcome:
        """Run at most one wave, optionally bound to a previously previewed selection."""
        _check_execution_deadline(_execution_deadline)
        items = self._validate_items(items, parallel_limit)
        if expected_selection_sha256 is not None and (
            type(expected_selection_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_selection_sha256) is None
        ):
            _invalid()
        actor = items[0].first
        project_id = actor.profile.project_id
        key = self._key(actor, request_id)
        project_key, snapshot, workers = self._owner_candidate_snapshot(items, admin_token)
        if (
            self._journal.get(project_key, key) is not None
            or self._relay._read_receipt(key, "wave-admitted") is not None
        ):
            raise AgentSyncError(
                "attempt_already_reserved", "This relay wave already has a receipt.", 409
            )
        if self._fenced(project_id, project_key):
            raise AgentSyncError(
                "wave_incomplete", "An earlier relay wave still holds the project fence.", 409
            )
        selected = self._select(items, snapshot, workers, parallel_limit)
        if expected_selection_sha256 is not None and (
            not selected
            or not hmac.compare_digest(expected_selection_sha256, _selection_pin(selected))
        ):
            raise AgentSyncError("selection_changed", "The previewed relay selection changed.", 409)
        if not selected:
            return RelayQueueOutcome("no_ready_tasks")
        self._check_selected(selected)
        required_workers = {
            participant.agent_id for item in selected for participant, _ in _participants(item)
        }
        if (
            self._relay._owner_worker_ids(project_id, required_workers, admin_token)
            != required_workers
        ):
            raise AgentSyncError(
                "forbidden", "A selected relay participant lost the worker role.", 403
            )
        # Reject invalid pinned inputs before reserving the wave. The launch path
        # prepares the task again after admission and keeps its failure fence.
        for item in selected:
            if not isinstance(item, RelayQueueItem) and item.task.input_context is not None:
                _check_execution_deadline(_execution_deadline)
                if isinstance(item, ProposalReviewQueueItem):
                    self._check_review_input(item, admin_token, key)
                else:
                    self._relay._single_codex_task(item.first, item.task, admin_token, wave_key=key)
        self._relay._check_receipt_anchor(project_id, bind=True)
        self._check_journal_anchor(project_key, bind=True)
        _check_execution_deadline(_execution_deadline)
        self._journal.admit(project_key, key, tuple(item.task.task_id for item in selected))

        async def run(item: _QueueItem) -> RelayQueueResult:
            task_id = item.task.task_id
            state: TaskState | Literal["not_started"] | None
            try:
                if isinstance(item, ProposalReviewQueueItem):
                    await self._relay.run_proposal_review_once(
                        item.first,
                        item.task,
                        admin_token=admin_token,
                        _wave_key=key,
                        _execution_deadline=_execution_deadline,
                    )
                    state = self._relay._wave_terminal_state(item.first, task_id, key)
                elif isinstance(item, CodexProposalQueueItem):
                    await self._relay.run_codex_proposal_once(
                        item.first,
                        item.task,
                        admin_token=admin_token,
                        _wave_key=key,
                        _execution_deadline=_execution_deadline,
                    )
                    state = self._relay._wave_terminal_state(item.first, task_id, key)
                else:
                    outcome = await self._relay.run_once(
                        item.first,
                        item.second,
                        item.task,
                        admin_token=admin_token,
                        _wave_key=key,
                        _execution_deadline=_execution_deadline,
                    )
                    state = outcome.state
            except AgentSyncError as error:
                failure = (
                    error.code
                    if type(error.code) is str and error.code in _FAILURE_CODES
                    else "relay_operation_failed"
                )
                return RelayQueueResult(task_id, "incomplete", failure)
            except Exception:
                return RelayQueueResult(task_id, "incomplete", "relay_outcome_unknown")
            if state in ("ready_for_review", "conflict"):
                return RelayQueueResult(task_id, state)
            return RelayQueueResult(task_id, "incomplete", "relay_outcome_unknown")

        results = tuple(await asyncio.gather(*(run(item) for item in selected)))
        incomplete = any(result.state == "incomplete" for result in results)
        self._journal.record(
            project_key,
            key,
            incomplete=incomplete,
            results=[row._receipt_row() for row in results],
        )
        return RelayQueueOutcome("incomplete" if incomplete else "resolved", results)

    async def drain_ready(
        self,
        items: tuple[_QueueItem, ...],
        *,
        request_id: str,
        admin_token: str,
        parallel_limit: int = 1,
        max_waves: int = 2,
        start_window_seconds: float = 120,
        execution_budget_seconds: float | None = None,
    ) -> RelaySequenceOutcome:
        """Continue prepared tasks only; every launch still requires exact fresh consent.

        The start window controls admission. An optional execution budget also
        limits awaited execution and prevents further launches when it expires.
        Cancellation does not prove child cleanup. Inspect the saved wave before
        taking any further action.
        """
        items = self._validate_items(items, parallel_limit)
        _identifier(request_id)
        if (
            type(max_waves) is not int
            or not 1 <= max_waves <= 4
            or type(start_window_seconds) not in (int, float)
            or not 0 < start_window_seconds <= 900
            or not math.isfinite(start_window_seconds)
            or (
                execution_budget_seconds is not None
                and (
                    type(execution_budget_seconds) not in (int, float)
                    or not 0 < execution_budget_seconds <= 900
                )
            )
        ):
            _invalid()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + start_window_seconds
        execution_deadline = (
            None if execution_budget_seconds is None else loop.time() + execution_budget_seconds
        )
        project = items[0].first.profile.project_id
        outcomes: list[RelayQueueOutcome] = []
        remaining = items
        for index in range(max_waves):
            if execution_deadline is not None and loop.time() >= execution_deadline:
                return RelaySequenceOutcome("execution_limit", tuple(outcomes))
            if loop.time() >= deadline:
                return RelaySequenceOutcome("time_limit", tuple(outcomes))
            wave_request = digest(["relay-queue-sequence-v1", project, request_id, index])
            timer = asyncio.timeout_at(execution_deadline)
            try:
                async with timer:
                    wave = await self.run_ready_once(
                        remaining,
                        request_id=wave_request,
                        admin_token=admin_token,
                        parallel_limit=parallel_limit,
                        _execution_deadline=execution_deadline,
                    )
            except TimeoutError:
                if not timer.expired():
                    raise
                return RelaySequenceOutcome("execution_limit", tuple(outcomes))
            except AgentSyncError as error:
                if error.code != "relay_execution_limit":
                    raise
                return RelaySequenceOutcome("execution_limit", tuple(outcomes))
            if wave.state == "no_ready_tasks":
                return RelaySequenceOutcome("no_ready_tasks", tuple(outcomes))
            outcomes.append(wave)
            if any(row.failure_code == "relay_execution_limit" for row in wave.tasks):
                return RelaySequenceOutcome("execution_limit", tuple(outcomes))
            if wave.state != "resolved":
                return RelaySequenceOutcome("incomplete", tuple(outcomes))
            attempted = {row.task_id for row in wave.tasks}
            remaining = tuple(item for item in remaining if item.task.task_id not in attempted)
            if not remaining:
                return RelaySequenceOutcome("no_ready_tasks", tuple(outcomes))
        return RelaySequenceOutcome("wave_limit", tuple(outcomes))

"""Owned bounded Mock workflows, not a production scheduler or real-client relay.

Only a fresh temporary child of an explicit existing scratch parent is used.
The owned fixture performs authenticated Core lifecycle operations and peer
reviews, but all work/results/evidence are simulation_only/unverified. No caller
Core, adapters, credentials, instructions or callbacks are accepted. There
is no restart recovery, external execution, lease renewal or production authority.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Literal

from agentsync.adapters import AdapterTask
from agentsync.core.service import Core
from agentsync.dispatch_planning import plan_dispatches
from agentsync.mock_run_manager import MockRunManager, MockWorker

_MARKER = "simulation_only/unverified"


def _valid_label(value: str) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is not None


@dataclass(frozen=True, slots=True)
class MockWorkflowTask:
    """Simulation metadata only; labels are 1..64 ASCII identifier characters."""

    label: str
    priority: int
    capability: Literal["build", "test"]
    dependencies: tuple[str, ...] = ()
    fail_first_attempt: bool = False

    def __post_init__(self) -> None:
        if (
            not _valid_label(self.label)
            or type(self.priority) is not int
            or not -(2**63) <= self.priority < 2**63
            or type(self.capability) is not str
            or self.capability not in ("build", "test")
            or type(self.dependencies) is not tuple
            or len(self.dependencies) > 15
            or any(not _valid_label(label) for label in self.dependencies)
            or len(set(self.dependencies)) != len(self.dependencies)
            or self.label in self.dependencies
            or type(self.fail_first_attempt) is not bool
        ):
            raise ValueError("Invalid mock workflow task.")


_SCENARIO = (
    MockWorkflowTask("root-build", 40, "build", fail_first_attempt=True),
    MockWorkflowTask("root-test", 30, "test"),
    MockWorkflowTask("join", 20, "build", ("root-build", "root-test")),
    MockWorkflowTask("final", 10, "test", ("join",)),
)


def _copy_tasks(tasks: tuple[MockWorkflowTask, ...]) -> tuple[MockWorkflowTask, ...]:
    if (
        type(tasks) is not tuple
        or not 1 <= len(tasks) <= 16
        or any(type(task) is not MockWorkflowTask for task in tasks)
    ):
        raise ValueError("Invalid mock workflow tasks.")
    try:
        copies = tuple(replace(task) for task in tasks)
    except (AttributeError, TypeError):
        raise ValueError("Invalid mock workflow task.") from None
    remaining = {task.label: task for task in copies}
    if len(remaining) != len(copies) or any(
        dependency not in remaining for task in copies for dependency in task.dependencies
    ):
        raise ValueError("Invalid mock workflow dependencies or duplicate labels.")
    ordered: list[MockWorkflowTask] = []
    while remaining:
        ready = sorted(
            label
            for label, task in remaining.items()
            if all(dependency not in remaining for dependency in task.dependencies)
        )
        if not ready:
            raise ValueError("Mock workflow dependencies contain a cycle.")
        ordered.extend(remaining.pop(label) for label in ready)
    return tuple(ordered)


@dataclass
class _Owned:
    worker: int
    row: dict[str, Any] = field(repr=False)
    lease: str = field(repr=False)


async def run_mock_workflow_demo(
    scratch_parent: Path,
    *,
    max_attempts_per_task: int = 2,
    attempt_budget: int = 6,
    max_elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the original four-task simulation, including its first build failure."""
    return await run_mock_workflow(
        scratch_parent,
        tasks=_SCENARIO,
        max_attempts_per_task=max_attempts_per_task,
        attempt_budget=attempt_budget,
        max_elapsed_seconds=max_elapsed_seconds,
    )


async def run_mock_workflow(
    scratch_parent: Path,
    *,
    tasks: tuple[MockWorkflowTask, ...],
    max_attempts_per_task: int = 2,
    attempt_budget: int = 6,
    max_elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Run 1..16 typed simulation tasks in a disposable owned child, then remove it.

    The parent must already be an absolute directory. Strict integer bounds are
    1..3 attempts per task and 1..16 starts overall (default 6). Task values are
    copied and validated as an acyclic graph before filesystem I/O. Unordered
    inputs use deterministic topological creation order. Existing parent databases
    are never opened. Only logical labels and simulation observations are returned.
    Core errors propagate; owned active Mock runs are cancelled on unexpected exit.
    Optional elapsed budget is a finite number in (0, 60], including owned Core
    setup. It stops admission and cancels active simulations after expiry is
    observed; it cannot preempt a synchronous operation or an awaited Mock call.
    """
    if (
        not isinstance(scratch_parent, Path)
        or not scratch_parent.is_absolute()
        or type(max_attempts_per_task) is not int
        or not 1 <= max_attempts_per_task <= 3
        or type(attempt_budget) is not int
        or not 1 <= attempt_budget <= 16
        or (
            max_elapsed_seconds is not None
            and (
                type(max_elapsed_seconds) not in (int, float)
                or not 0 < max_elapsed_seconds <= 60
                or not math.isfinite(max_elapsed_seconds)
            )
        )
    ):
        raise ValueError("Invalid mock workflow scratch parent or bounds.")
    scenario = _copy_tasks(tasks)
    try:
        scratch_parent = scratch_parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Mock workflow scratch parent must be an existing directory.") from None
    if not scratch_parent.is_dir():
        raise ValueError("Mock workflow scratch parent must be an existing directory.")
    deadline = None if max_elapsed_seconds is None else monotonic() + max_elapsed_seconds
    with TemporaryDirectory(prefix="agentsync-mock-workflow-", dir=scratch_parent) as child:
        return await _run(Path(child), scenario, max_attempts_per_task, attempt_budget, deadline)


async def _run(
    directory: Path,
    scenario: tuple[MockWorkflowTask, ...],
    max_attempts: int,
    budget: int,
    deadline: float | None,
) -> dict[str, Any]:
    root = directory / "project"
    root.mkdir()
    core = Core(directory / "state")
    project = core.execute("create_project", {"name": _MARKER, "root_path": str(root)})
    project_id = project["project_id"]
    actors = []
    for label in ("build", "test"):
        actor = core.execute("register_agent", {**project, "name": label, "capabilities": [label]})
        core.execute_owner(
            "set_agent_roles",
            {
                **project,
                "agent_id": actor["agent_id"],
                "roles": ["worker", "reviewer"],
                "expected_version": 1,
                "request_id": "grant-" + label,
            },
        )
        actors.append(actor)
    credentials = [
        {
            "project_id": project_id,
            "session_id": actor["session_id"],
            "session_token": actor["session_token"],
        }
        for actor in actors
    ]

    def call(worker: int, operation: str, **payload: Any) -> dict[str, Any]:
        return core.execute(operation, {**credentials[worker], **payload})

    tasks: dict[str, dict[str, Any]] = {}
    requirements: dict[str, tuple[str, ...]] = {}
    for definition in scenario:
        label = definition.label
        tasks[label] = call(
            0,
            "create_task",
            title=label,
            description=_MARKER,
            priority=definition.priority,
            dependencies=[tasks[parent]["id"] for parent in definition.dependencies],
            request_id="create-" + label,
        )
        requirements[tasks[label]["id"]] = (definition.capability,)
    fail_first = {definition.label for definition in scenario if definition.fail_first_attempt}
    labels = {row["id"]: label for label, row in tasks.items()}
    worker_indices = {actor["agent_id"]: index for index, actor in enumerate(actors)}
    worker_labels = ("build", "test")
    manager = MockRunManager(
        project_id,
        tuple(MockWorker(actor["agent_id"], actor["session_id"]) for actor in actors),
        global_limit=2,
        per_agent_limit=1,
        max_runs=16,
        clock=lambda: 100.0,
    )
    attempts = dict.fromkeys(tasks, 0)
    owned: dict[str, _Owned] = {}
    active: dict[str, tuple[str, int]] = {}
    retries: list[str] = []
    trace: list[dict[str, Any]] = []
    reviews = []
    peak = 0
    stop_reason = None

    def expired() -> bool:
        nonlocal stop_reason
        if deadline is not None and monotonic() >= deadline:
            stop_reason = "time_budget_exhausted"
            return True
        return False

    async def cancel_active() -> None:
        for run_id in list(active):
            if (await manager.get_status(run_id)).run.status == "running":
                await manager.cancel_task(run_id)
            del active[run_id]

    def transition(label: str, status: str) -> dict[str, Any]:
        entry = owned[label]
        entry.row = call(
            entry.worker,
            "update_task",
            task_id=entry.row["id"],
            expected_version=entry.row["version"],
            lease_token=entry.lease,
            status=status,
            result=_MARKER,
            request_id=f"{label}-{status}",
        )
        return entry.row

    try:
        while stop_reason is None:
            if expired():
                break
            remaining = budget - sum(attempts.values())
            state = call(0, "get_project_state")
            if all(row["status"] == "completed" for row in state["tasks"]):
                break
            if remaining == 0:
                stop_reason = "attempt_budget_exhausted"
                break
            batch: list[tuple[str, int, int | None]] = [
                (label, owned[label].worker, None) for label in retries[:remaining]
            ]
            retries = retries[len(batch) :]
            fresh_budget = remaining - len(batch)
            if fresh_budget:
                plan = plan_dispatches(
                    state,
                    project_id=project_id,
                    worker_agent_ids=tuple(actor["agent_id"] for actor in actors),
                    now=time.time(),
                    global_limit=2,
                    per_agent_limit=1,
                    limit=min(fresh_budget, 2),
                    required_capabilities=requirements,
                )
                batch.extend(
                    (labels[item.task_id], worker_indices[item.agent_id], item.expected_version)
                    for item in plan.dispatches
                )
            if not batch:
                raise RuntimeError("Owned mock workflow unexpectedly has no eligible work.")
            # All starts in this bounded batch precede every simulated finish.
            for label, worker, version in batch:
                if expired():
                    break
                if sum(attempts.values()) >= budget or attempts[label] >= max_attempts:
                    raise RuntimeError("Mock workflow attempt reservation was violated.")
                if version is not None:
                    claimed = call(
                        worker,
                        "claim_task",
                        task_id=tasks[label]["id"],
                        expected_version=version,
                        request_id="claim-" + label,
                    )
                    owned[label] = _Owned(worker, claimed, claimed["lease_token"])
                    transition(label, "running")
                if expired():
                    break
                attempts[label] += 1
                started = await manager.start_task(
                    actors[worker]["agent_id"],
                    AdapterTask(
                        project_id,
                        actors[worker]["session_id"],
                        tasks[label]["id"],
                        f"{label}-attempt-{attempts[label]}",
                    ),
                )
                active[started.run.run_id] = (label, worker)
                peak = max(peak, len(active))
                trace.append(
                    {
                        "event": "started",
                        "task": label,
                        "worker": worker_labels[worker],
                        "attempt": attempts[label],
                        "active_simulations": len(active),
                    }
                )
                if expired():
                    break
            if stop_reason == "time_budget_exhausted":
                break
            for run_id, (label, worker) in list(active.items()):
                if expired():
                    break
                failed = label in fail_first and attempts[label] == 1
                ended = await manager.finish_mock_run(run_id, output=_MARKER, failed=failed)
                result = await manager.get_result(run_id)
                if result.result.run != ended.run or result.result.output != _MARKER:
                    raise RuntimeError("Mock workflow result correlation failed.")
                del active[run_id]
                trace.append(
                    {
                        "event": "finished",
                        "task": label,
                        "worker": worker_labels[worker],
                        "attempt": attempts[label],
                        "status": ended.run.status,
                        "active_simulations": len(active),
                    }
                )
                if expired():
                    break
                if failed:
                    if attempts[label] >= max_attempts:
                        stop_reason = "per_task_attempts_exhausted"
                    else:
                        retries.append(label)
                    continue
                submitted = transition(label, "review")
                peer = 1 - worker
                completed = call(
                    peer,
                    "review_task",
                    task_id=submitted["id"],
                    expected_version=submitted["version"],
                    accept=True,
                    evidence=_MARKER,
                    request_id="review-" + label,
                )
                if completed["latest_review"]["reviewer_agent_id"] != actors[peer]["agent_id"]:
                    raise RuntimeError("Mock workflow peer review correlation failed.")
                reviews.append(
                    {
                        "task": label,
                        "owner": worker_labels[worker],
                        "reviewer": worker_labels[peer],
                        "evidence": _MARKER,
                    }
                )
                trace.append({"event": "peer_reviewed", **reviews[-1]})
                del owned[label]
        # Cancellation must finish before constructing the public zero-active summary.
        await cancel_active()
        # Exhaustion releases every remaining owned Core lease, never descendants.
        for label in owned:
            transition(label, "failed")
            trace.append({"event": "stopped", "task": label, "reason": stop_reason})
        current = call(0, "list_tasks")
        persisted = Core(core.data_dir).execute("list_tasks", credentials[0])
        if persisted != current:
            raise RuntimeError("Mock workflow persistence check failed.")
        statuses = {
            label: next(row["status"] for row in persisted["tasks"] if row["id"] == task["id"])
            for label, task in tasks.items()
        }
        return {
            "ok": True,
            "data": {
                "scope": "simulation_only",
                "simulated": True,
                "execution_connected": False,
                "verification": "unverified",
                "core_authorization": "unverified",
                "formal_acceptance": False,
                "real_client_verified": False,
                "outcome": "simulated_completed" if stop_reason is None else "simulated_stopped",
                "stop_reason": stop_reason,
                "task_statuses": statuses,
                "attempt_counts": attempts,
                "attempts_used": sum(attempts.values()),
                "max_active_simulations": peak,
                "active_simulations": len(active),
                "peer_reviews": reviews,
                "trace": trace,
                "persistence_verified": True,
            },
        }
    finally:
        await cancel_active()

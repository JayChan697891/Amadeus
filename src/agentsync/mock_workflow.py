"""Owned four-task simulation demo, not a scheduler or real-client relay.

Only a fresh temporary child of an explicit existing scratch parent is used.
The fixed fixture performs authenticated Core lifecycle operations and peer
reviews, but all work/results/evidence are simulation_only/unverified. No caller
Core, tasks, adapters, credentials, instructions or callbacks are accepted. There
is no restart recovery, external execution, lease renewal or production authority.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from agentsync.adapters import AdapterTask
from agentsync.core.service import Core
from agentsync.dispatch_planning import plan_dispatches
from agentsync.mock_run_manager import MockRunManager, MockWorker

_MARKER = "simulation_only/unverified"
_SCENARIO = (
    ("root-build", 40, "build", ()),
    ("root-test", 30, "test", ()),
    ("join", 20, "build", ("root-build", "root-test")),
    ("final", 10, "test", ("join",)),
)


@dataclass
class _Owned:
    worker: int
    row: dict[str, Any] = field(repr=False)
    lease: str = field(repr=False)


async def run_mock_workflow_demo(
    scratch_parent: Path, *, max_attempts_per_task: int = 2, attempt_budget: int = 6
) -> dict[str, Any]:
    """Run a bounded fixed simulation in a disposable owned child, then remove it.

    The parent must already be an absolute directory. Strict integer bounds are
    1..3 attempts per task and 1..16 starts overall. Options are validated before
    filesystem I/O. Existing parent databases are never opened. Only logical
    fixture labels and simulation observations are returned, without credentials.
    Core errors propagate; owned active Mock runs are cancelled on unexpected exit.
    """
    if (
        not isinstance(scratch_parent, Path)
        or not scratch_parent.is_absolute()
        or type(max_attempts_per_task) is not int
        or not 1 <= max_attempts_per_task <= 3
        or type(attempt_budget) is not int
        or not 1 <= attempt_budget <= 16
    ):
        raise ValueError("Invalid mock workflow scratch parent or bounds.")
    try:
        scratch_parent = scratch_parent.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Mock workflow scratch parent must be an existing directory.") from None
    if not scratch_parent.is_dir():
        raise ValueError("Mock workflow scratch parent must be an existing directory.")
    with TemporaryDirectory(prefix="agentsync-mock-workflow-", dir=scratch_parent) as child:
        return await _run(Path(child), max_attempts_per_task, attempt_budget)


async def _run(directory: Path, max_attempts: int, budget: int) -> dict[str, Any]:
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
    for label, priority, capability, dependencies in _SCENARIO:
        tasks[label] = call(
            0,
            "create_task",
            title=label,
            description=_MARKER,
            priority=priority,
            dependencies=[tasks[parent]["id"] for parent in dependencies],
            request_id="create-" + label,
        )
        requirements[tasks[label]["id"]] = (capability,)
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
            for run_id, (label, worker) in list(active.items()):
                failed = label == "root-build" and attempts[label] == 1
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
        for run_id in active:
            if (await manager.get_status(run_id)).run.status == "running":
                await manager.cancel_task(run_id)

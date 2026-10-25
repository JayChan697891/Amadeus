"""Capacity suggestions from caller-authorized Core snapshots, never execution.

The worker allowlist confers no Core permission. Counts reflect task ownership,
not client processes. Limits constrain this plan only: independent concurrent
plans can compete for the same slots. Core must recheck each explicit claim;
it does not enforce these planning limits. Completeness/freshness is unverified.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from agentsync.errors import AgentSyncError
from agentsync.scheduling import plan_tasks


@dataclass(frozen=True, slots=True)
class DispatchRecommendation:
    task_id: str
    expected_version: int
    agent_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class AgentLoad:
    agent_id: str
    session_id: str | None
    active_count: int
    planned_count: int


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    project_id: str
    observed_at: float
    dispatches: tuple[DispatchRecommendation, ...]
    global_active_count: int
    worker_loads: tuple[AgentLoad, ...]
    global_limit: int
    per_agent_limit: int
    scope: Literal["planning_only"] = field(default="planning_only", init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    capability_matching: Literal["unverified"] = field(default="unverified", init=False)
    snapshot_freshness: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)
    load_scope: Literal["core_task_ownership_only"] = field(
        default="core_task_ownership_only", init=False
    )


def plan_dispatches(
    state: dict[str, Any],
    *,
    project_id: str,
    worker_agent_ids: tuple[str, ...],
    now: float,
    global_limit: int = 4,
    per_agent_limit: int = 1,
    limit: int = 10,
) -> DispatchPlan:
    try:
        return _plan_dispatches(
            state, project_id, worker_agent_ids, now, global_limit, per_agent_limit, limit
        )
    except (KeyError, TypeError, ValueError, OverflowError, UnicodeError):
        raise AgentSyncError("invalid_snapshot", "Invalid dispatch snapshot or options.") from None


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid snapshot")


def _identifier(value: Any) -> None:
    _require(type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= 200)
    _require(not any(ord(character) < 32 for character in value))


def _timestamp(value: Any) -> float:
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0)
    return float(value)


def _plan_dispatches(
    state: dict[str, Any],
    project_id: str,
    worker_agent_ids: tuple[str, ...],
    now: float,
    global_limit: int,
    per_agent_limit: int,
    limit: int,
) -> DispatchPlan:
    _identifier(project_id)
    now = _timestamp(now)
    for bound in (global_limit, per_agent_limit, limit):
        _require(type(bound) is int and 1 <= bound <= 100)
    _require(type(worker_agent_ids) is tuple and 1 <= len(worker_agent_ids) <= 32)
    for worker in worker_agent_ids:
        _identifier(worker)
    _require(len(set(worker_agent_ids)) == len(worker_agent_ids))
    _require(type(state) is dict and set(state) == {"project", "agents", "sessions", "tasks"})
    _require(type(state["project"]) is dict and state["project"]["id"] == project_id)
    _timestamp(state["project"]["created_at"])
    _require(type(state["agents"]) is list and len(state["agents"]) <= 8192)
    _require(type(state["sessions"]) is list and len(state["sessions"]) <= 8192)
    agent_ids = set()
    for row in state["agents"]:
        _require(type(row) is dict)
        _identifier(row["id"])
        _require(row["project_id"] == project_id and row["id"] not in agent_ids)
        _timestamp(row["created_at"])
        agent_ids.add(row["id"])
    _require(set(worker_agent_ids) <= agent_ids)
    workers = sorted(worker_agent_ids)
    session_map = {}
    for row in state["sessions"]:
        _require(type(row) is dict)
        _identifier(row["id"])
        _require(row["project_id"] == project_id and row["id"] not in session_map)
        _identifier(row["agent_id"])
        _require(row["agent_id"] in agent_ids and type(row["online"]) is bool)
        created, heartbeat, expires = (
            _timestamp(row[key]) for key in ("created_at", "heartbeat_at", "expires_at")
        )
        _require(created <= heartbeat < expires)
        session_map[row["id"]] = row
    # Validate every task even when no worker is online or all capacity is occupied.
    ready_by_worker = {
        worker: {
            item.task_id
            for item in plan_tasks(
                {"tasks": state["tasks"]},
                project_id=project_id,
                agent_id=worker,
                now=now,
                limit=100,
            ).candidates
        }
        for worker in workers
    }
    for row in state["tasks"]:
        owner = row["owner_session_id"]
        _require(owner is None or owner in session_map)
        if row["status"] in {"claimed", "running", "blocked"}:
            _require(owner is not None)
    selected: dict[str, str | None] = {}
    for worker in workers:
        online = [
            row
            for row in session_map.values()
            if row["agent_id"] == worker
            and row["created_at"] <= row["heartbeat_at"] <= now
            and now - row["heartbeat_at"] <= 120
            and row["expires_at"] > now
        ]
        online.sort(key=lambda row: (-row["heartbeat_at"], -row["created_at"], row["id"]))
        selected[worker] = online[0]["id"] if online else None
    active = {row["id"]: 0 for row in state["agents"]}
    global_active = 0
    for row in state["tasks"]:
        if row["status"] in {"claimed", "running", "blocked"}:
            active[session_map[row["owner_session_id"]]["agent_id"]] += 1
            global_active += 1
    planned = dict.fromkeys(workers, 0)
    dispatches: list[DispatchRecommendation] = []
    ordered = sorted(
        state["tasks"], key=lambda row: (-row["priority"], float(row["created_at"]), row["id"])
    )
    for row in ordered:
        if len(dispatches) >= min(limit, max(0, global_limit - global_active)):
            break
        available = [
            worker
            for worker in workers
            if selected[worker] is not None
            and row["id"] in ready_by_worker[worker]
            and active[worker] + planned[worker] < per_agent_limit
        ]
        if not available:
            continue
        worker = min(available, key=lambda agent: (active[agent] + planned[agent], agent))
        session_id = selected[worker]
        assert session_id is not None
        dispatches.append(DispatchRecommendation(row["id"], row["version"], worker, session_id))
        planned[worker] += 1
    return DispatchPlan(
        project_id,
        now,
        tuple(dispatches),
        global_active,
        tuple(
            AgentLoad(worker, selected[worker], active[worker], planned[worker])
            for worker in workers
        ),
        global_limit,
        per_agent_limit,
    )

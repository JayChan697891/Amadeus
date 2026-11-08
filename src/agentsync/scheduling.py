"""Read-only recommendations from a caller-authorized Core list_tasks snapshot.

This module never authenticates, claims, executes, or maintains task state. A plan
does not prove snapshot completeness or freshness; Core must recheck every claim.
Optional capability filtering compares caller requirements with self-reported
declarations only. Capability verification, retries and autonomous scheduling
remain unverified.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from agentsync.errors import AgentSyncError


@dataclass(frozen=True, slots=True)
class TaskRecommendation:
    task_id: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class SchedulingPlan:
    project_id: str
    agent_id: str
    observed_at: float
    candidates: tuple[TaskRecommendation, ...]
    capability_filter: Literal["not_requested", "caller_required_self_reported"] = field(
        default="not_requested", kw_only=True
    )
    scope: Literal["planning_only"] = field(default="planning_only", init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    snapshot_freshness: Literal["unverified"] = field(default="unverified", init=False)
    capability_matching: Literal["unverified"] = field(default="unverified", init=False)


def plan_tasks(
    snapshot: dict[str, Any],
    *,
    project_id: str,
    agent_id: str,
    now: float,
    limit: int = 10,
    required_capabilities: dict[str, tuple[str, ...]] | None = None,
    agent_capabilities: tuple[str, ...] = (),
    candidate_task_ids: tuple[str, ...] | None = None,
) -> SchedulingPlan:
    try:
        return _plan(
            snapshot, project_id, agent_id, now, limit, required_capabilities, agent_capabilities,
            candidate_task_ids,
        )
    except (KeyError, TypeError, ValueError, OverflowError, UnicodeError):
        raise AgentSyncError(
            "invalid_snapshot", "Invalid scheduling snapshot or options."
        ) from None


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid snapshot")


def _identifier(value: Any) -> None:
    _require(type(value) is str and bool(value.strip()) and len(value.encode("utf-8")) <= 200)
    _require(not any(ord(character) < 32 for character in value))


def _timestamp(value: Any) -> float:
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0)
    return float(value)


def _capability_tokens(value: Any) -> frozenset[str]:
    _require(type(value) is tuple and len(value) <= 128)
    for token in value:
        _identifier(token)
    _require(len(value) == len(set(value)))
    return frozenset(value)


def _capability_requirements(
    value: dict[str, tuple[str, ...]], task_ids: set[str]
) -> dict[str, frozenset[str]]:
    _require(type(value) is dict and len(value) <= 4096)
    for task_id in value:
        _identifier(task_id)
    _require(set(value) == task_ids)
    total = 0
    requirements = {}
    for task_id, tokens in value.items():
        requirements[task_id] = _capability_tokens(tokens)
        total += len(tokens)
        _require(total <= 16384)
    return requirements


def _plan(
    snapshot: dict[str, Any],
    project_id: str,
    agent_id: str,
    now: float,
    limit: int,
    required_capabilities: dict[str, tuple[str, ...]] | None,
    agent_capabilities: tuple[str, ...],
    candidate_task_ids: tuple[str, ...] | None,
) -> SchedulingPlan:
    _identifier(project_id)
    _identifier(agent_id)
    observed = _timestamp(now)
    _require(type(limit) is int and 1 <= limit <= 100)
    _require(type(snapshot) is dict and set(snapshot) == {"tasks"})
    source = snapshot["tasks"]
    _require(type(source) is list and len(source) <= 4096)
    rows: dict[str, dict[str, Any]] = {}
    edge_count = 0
    statuses = {
        "pending",
        "claimed",
        "running",
        "handoff",
        "review",
        "blocked",
        "failed",
        "cancelled",
        "completed",
    }
    for original in source:
        _require(type(original) is dict)
        row = dict(original)
        task_id = row["id"]
        _identifier(task_id)
        _require(task_id not in rows and row["project_id"] == project_id)
        _require(type(row["status"]) is str and row["status"] in statuses)
        _require(type(row["priority"]) is int and -(2**63) <= row["priority"] < 2**63)
        _require(type(row["version"]) is int and 1 <= row["version"] <= 2**63 - 2)
        row["created_at"] = _timestamp(row["created_at"])
        _timestamp(row["updated_at"])
        if row["owner_session_id"] is not None:
            _identifier(row["owner_session_id"])
        if row["lease_expires_at"] is not None:
            _timestamp(row["lease_expires_at"])
        assigned, expires = row["assigned_agent_id"], row["assignment_expires_at"]
        _require((assigned is None) == (expires is None))
        if assigned is not None:
            _identifier(assigned)
            _timestamp(expires)
        dependencies = row["dependencies"]
        _require(type(dependencies) is list and len(dependencies) <= 4096)
        for dependency in dependencies:
            _identifier(dependency)
        _require(len(dependencies) == len(set(dependencies)))
        row["dependencies"] = tuple(dependencies)
        edge_count += len(dependencies)
        _require(edge_count <= 65536)
        rows[task_id] = row

    requirements = None
    declared = frozenset[str]()
    if required_capabilities is not None:
        requirements = _capability_requirements(required_capabilities, set(rows))
        declared = _capability_tokens(agent_capabilities)
    allowed: set[str] | None = None
    if candidate_task_ids is not None:
        _require(type(candidate_task_ids) is tuple and len(candidate_task_ids) <= 4096)
        for task_id in candidate_task_ids:
            _identifier(task_id)
        allowed = set(candidate_task_ids)
        _require(len(allowed) == len(candidate_task_ids) and allowed <= rows.keys())

    # Iterative traversal keeps a valid deep dependency chain off the Python stack.
    children: dict[str, list[str]] = {task_id: [] for task_id in rows}
    incoming = dict.fromkeys(rows, 0)
    for task_id, row in rows.items():
        for dependency in row["dependencies"]:
            if dependency in rows:
                incoming[task_id] += 1
                children[dependency].append(task_id)
    ready = deque(task_id for task_id, degree in incoming.items() if degree == 0)
    visited = 0
    while ready:
        task_id = ready.popleft()
        visited += 1
        for child in children[task_id]:
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
    _require(visited == len(rows))
    candidates = []
    for row in rows.values():
        if allowed is not None and row["id"] not in allowed:
            continue
        if requirements is not None and not requirements[row["id"]] <= declared:
            continue
        if (
            row["status"] != "pending"
            or row["owner_session_id"] is not None
            or row["lease_expires_at"] is not None
        ):
            continue
        if any(
            dependency not in rows or rows[dependency]["status"] != "completed"
            for dependency in row["dependencies"]
        ):
            continue
        if (
            row["assigned_agent_id"] is not None
            and row["assignment_expires_at"] > observed
            and row["assigned_agent_id"] != agent_id
        ):
            continue
        candidates.append(row)
    candidates.sort(key=lambda row: (-row["priority"], row["created_at"], row["id"]))
    return SchedulingPlan(
        project_id,
        agent_id,
        observed,
        tuple(TaskRecommendation(row["id"], row["version"]) for row in candidates[:limit]),
        capability_filter="caller_required_self_reported"
        if requirements is not None
        else "not_requested",
    )

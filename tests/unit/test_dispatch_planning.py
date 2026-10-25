"""Read-only dispatch recommendations, not execution, authorization, or quota enforcement."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

import pytest

from agentsync.dispatch_planning import plan_dispatches
from agentsync.errors import AgentSyncError


def task(task_id="task", **changes):
    return {
        "id": task_id,
        "project_id": "project",
        "title": "Task",
        "description": "",
        "priority": 0,
        "status": "pending",
        "version": 1,
        "owner_session_id": None,
        "result": "",
        "dependencies": [],
        "created_at": 10.0,
        "updated_at": 10.0,
        "lease_expires_at": None,
        "assigned_agent_id": None,
        "assignment_expires_at": None,
        "latest_review": None,
        **changes,
    }


def session(agent="a", **changes):
    return {
        "id": f"session-{agent}",
        "project_id": "project",
        "agent_id": agent,
        "created_at": 1.0,
        "heartbeat_at": 99.0,
        "expires_at": 200.0,
        "online": True,
        **changes,
    }


def state(tasks=None, sessions=None):
    return {
        "project": {"id": "project", "name": "Project", "root_path": "/opaque", "created_at": 1.0},
        "agents": [
            {
                "id": agent,
                "project_id": "project",
                "name": agent,
                "capabilities": [],
                "created_at": 1.0,
            }
            for agent in ("a", "b")
        ],
        "sessions": sessions if sessions is not None else [session("a"), session("b")],
        "tasks": tasks if tasks is not None else [task()],
    }


def plan(snapshot, **options):
    values = {"project_id": "project", "worker_agent_ids": ("a", "b"), "now": 100.0, **options}
    return plan_dispatches(snapshot, **values)


def test_public_dispatch_tracer_returns_ids_without_tokens_or_authority():
    result = plan(state())
    item = result.dispatches[0]
    assert (item.task_id, item.expected_version, item.agent_id, item.session_id) == (
        "task",
        1,
        "a",
        "session-a",
    )
    assert result.scope == "planning_only" and result.execution_connected is False
    assert (
        result.capability_matching
        == result.snapshot_freshness
        == result.core_authorization
        == "unverified"
    )
    assert result.load_scope == "core_task_ownership_only"


def test_global_priority_order_and_least_load_balancing_are_deterministic():
    rows = [
        task("b", priority=1),
        task("a", priority=1),
        task("high", priority=2),
        task("old", priority=1, created_at=9.0),
    ]
    result = plan(state(rows), per_agent_limit=2)
    assert [(item.task_id, item.agent_id) for item in result.dispatches] == [
        ("high", "a"),
        ("old", "b"),
        ("a", "a"),
        ("b", "b"),
    ]
    reverse = state(list(reversed(rows)), list(reversed([session("a"), session("b")])))
    assert plan(reverse, worker_agent_ids=("b", "a"), per_agent_limit=2) == result


def test_existing_owned_task_load_selects_less_busy_agent():
    result = plan(
        state(
            [
                task(
                    "owned", status="running", owner_session_id="session-a", lease_expires_at=200.0
                ),
                task(),
            ]
        ),
        per_agent_limit=2,
    )
    assert result.global_active_count == 1
    assert result.dispatches[0].agent_id == "b"
    assert [
        (load.agent_id, load.active_count, load.planned_count) for load in result.worker_loads
    ] == [("a", 1, 0), ("b", 0, 1)]


def test_plan_limits_bound_one_batch_and_never_duplicate_a_task():
    snapshot = state([task(str(index)) for index in range(5)])
    result = plan(snapshot)
    assert len(result.dispatches) == len({item.task_id for item in result.dispatches}) == 2
    assert len(plan(snapshot, global_limit=1).dispatches) == 1
    assert len(plan(snapshot, limit=1).dispatches) == 1


def test_expired_lease_and_offline_owner_still_occupy_global_slot():
    snapshot = state(
        [
            task("owned", status="running", owner_session_id="session-a", lease_expires_at=50.0),
            task(),
        ],
        [session("a", heartbeat_at=20.0, expires_at=90.0), session("b")],
    )
    result = plan(snapshot, global_limit=1)
    assert result.global_active_count == 1 and result.dispatches == ()


def test_load_aggregates_all_sessions_but_dispatch_selects_one_fresh_session():
    snapshot = state(
        [
            task("one", status="claimed", owner_session_id="session-a", lease_expires_at=50.0),
            task("two", status="blocked", owner_session_id="new-a", lease_expires_at=200.0),
            task(),
        ],
        [
            session("a", heartbeat_at=20.0, expires_at=90.0),
            session("a", id="new-a", created_at=2.0),
        ],
    )
    result = plan(snapshot, worker_agent_ids=("a",), per_agent_limit=3)
    assert result.worker_loads[0].active_count == result.global_active_count == 2
    assert result.dispatches[0].session_id == "new-a"


def test_active_load_outside_allowlist_is_not_ignored():
    result = plan(
        state(
            [
                task(
                    "owned", status="claimed", owner_session_id="session-b", lease_expires_at=200.0
                ),
                task(),
            ]
        ),
        worker_agent_ids=("a",),
        global_limit=1,
    )
    assert result.global_active_count == 1 and result.dispatches == ()


def test_reserved_worker_at_capacity_does_not_fall_back_to_another_worker():
    result = plan(
        state(
            [
                task(
                    "owned", status="blocked", owner_session_id="session-b", lease_expires_at=200.0
                ),
                task("reserved", priority=10, assigned_agent_id="b", assignment_expires_at=150.0),
                task("free"),
            ]
        )
    )
    assert [(item.task_id, item.agent_id) for item in result.dispatches] == [("free", "a")]


@pytest.mark.parametrize(
    "heartbeat,expires,old_online,eligible",
    [
        (80.0, 300.0, True, True),
        (79.0, 300.0, True, False),
        (201.0, 300.0, True, False),
        (199.0, 200.0, True, False),
        (199.0, 300.0, False, True),
    ],
)
def test_online_is_recomputed_from_explicit_timestamps(heartbeat, expires, old_online, eligible):
    result = plan(
        state(
            sessions=[session("a", heartbeat_at=heartbeat, expires_at=expires, online=old_online)]
        ),
        worker_agent_ids=("a",),
        now=200.0,
    )
    assert bool(result.dispatches) is eligible


def test_one_session_is_chosen_by_heartbeat_created_and_id():
    sessions = [
        session("a", id="z", created_at=2.0),
        session("a", id="a", created_at=3.0),
        session("a", id="b", created_at=3.0),
    ]
    assert plan(state(sessions=sessions), worker_agent_ids=("a",)).dispatches[0].session_id == "a"
    sessions.append(session("a", id="fresh", created_at=1.0, heartbeat_at=100.0))
    assert (
        plan(state(sessions=list(reversed(sessions))), worker_agent_ids=("a",))
        .dispatches[0]
        .session_id
        == "fresh"
    )


def test_review_handoff_and_terminal_tasks_do_not_count_as_active_ownership():
    rows = [
        task("review", status="review", owner_session_id="session-a"),
        task("handoff", status="handoff"),
        task("completed", status="completed", owner_session_id="session-a"),
        task("free"),
    ]
    result = plan(state(rows))
    assert result.global_active_count == 0
    assert [item.task_id for item in result.dispatches] == ["free"]


@pytest.mark.parametrize(
    "damage",
    [
        "unknown_owner",
        "duplicate_session",
        "unknown_session_agent",
        "foreign_session",
        "foreign_agent",
        "project",
        "incomplete_task",
    ],
)
def test_invalid_snapshot_relations_have_static_errors(damage):
    snapshot = state()
    if damage == "unknown_owner":
        snapshot["tasks"] = [
            task(status="running", owner_session_id="missing", lease_expires_at=200.0)
        ]
    elif damage == "duplicate_session":
        snapshot["sessions"].append(session("a"))
    elif damage == "unknown_session_agent":
        snapshot["sessions"][0]["agent_id"] = "missing"
    elif damage == "foreign_session":
        snapshot["sessions"][0]["project_id"] = "other-project"
    elif damage == "foreign_agent":
        snapshot["agents"][0]["project_id"] = "other-project"
    elif damage == "project":
        snapshot["project"]["id"] = "other-project"
    else:
        del snapshot["tasks"][0]["priority"]
    with pytest.raises(AgentSyncError) as exc:
        plan(snapshot)
    assert exc.value.code == "invalid_snapshot" and "other-project" not in exc.value.message


def test_strict_options_and_session_numbers_reject_bool_and_nonfinite_values():
    for options in (
        {"global_limit": True},
        {"global_limit": 0},
        {"per_agent_limit": 101},
        {"limit": 1.0},
        {"now": float("nan")},
        {"worker_agent_ids": ()},
        {"worker_agent_ids": ("a", "a")},
        {"worker_agent_ids": ("unknown",)},
    ):
        with pytest.raises(AgentSyncError):
            plan(state(), **options)
    for field, value in (("heartbeat_at", True), ("expires_at", float("inf")), ("created_at", "1")):
        snapshot = state()
        snapshot["sessions"][0][field] = value
        with pytest.raises(AgentSyncError):
            plan(snapshot)


@pytest.mark.parametrize("unavailable", ["full", "offline"])
def test_full_or_offline_workers_do_not_skip_snapshot_validation(unavailable):
    snapshot = state(
        [
            task("owned", status="running", owner_session_id="session-a", lease_expires_at=200.0),
            task(),
        ]
    )
    if unavailable == "offline":
        for item in snapshot["sessions"]:
            item["heartbeat_at"] = 80.0
            item["expires_at"] = 90.0
    options = {"global_limit": 1} if unavailable == "full" else {"global_limit": 4}
    assert plan(snapshot, **options).dispatches == ()
    del snapshot["tasks"][1]["priority"]
    with pytest.raises(AgentSyncError):
        plan(snapshot, **options)


def test_bounded_workers_agents_sessions_and_tasks():
    snapshots = []
    snapshot = state()
    snapshot["sessions"] = [session("a", id=f"s-{index}") for index in range(8193)]
    snapshots.append(snapshot)
    snapshot = state()
    snapshot["agents"] = [{**snapshot["agents"][0], "id": f"a-{index}"} for index in range(8193)]
    snapshots.append(snapshot)
    snapshots.append(state([task(str(index)) for index in range(4097)]))
    for snapshot in snapshots:
        with pytest.raises(AgentSyncError):
            plan(snapshot)
    with pytest.raises(AgentSyncError):
        plan(state(), worker_agent_ids=tuple(f"worker-{index}" for index in range(33)))


def test_plan_is_immutable_and_does_not_change_or_retain_mutable_input():
    snapshot = state()
    before = deepcopy(snapshot)
    result = plan(snapshot)
    assert snapshot == before
    snapshot["tasks"][0]["version"] = 2
    assert result.dispatches[0].expected_version == 1
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.worker_loads[0].active_count = 999
    with pytest.raises((ValueError, TypeError)):
        replace(result, execution_connected=True)

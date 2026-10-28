"""Capacity recommendations over real temporary Core state, never automatic claims."""

import time
from collections import Counter

from test_scheduling_core_boundary import auth
from test_scheduling_core_boundary import world as world

from agentsync.dispatch_planning import plan_dispatches


def create(core, actor, title, priority=0):
    return core.execute(
        "create_task",
        {**auth(actor), "title": title, "priority": priority, "request_id": title},
    )


def claim(core, actor, task, request_id, lease_seconds=300):
    return core.execute(
        "claim_task",
        {
            **auth(actor),
            "task_id": task["id"],
            "expected_version": task["version"],
            "request_id": request_id,
            "lease_seconds": lease_seconds,
        },
    )


def test_real_task_load_limits_suggestions_without_mutating_core(world):
    core, actors = world
    first, second = actors
    active = create(core, second, "Already active", 100)
    claim(core, second, active, "claim-active")
    ready = [create(core, first, f"Ready {number}", number) for number in (30, 20, 10)]
    snapshot = core.execute("get_project_state", auth(first))
    task_before = snapshot["tasks"]
    result = plan_dispatches(
        snapshot,
        project_id=first["project_id"],
        worker_agent_ids=tuple(actor["agent_id"] for actor in actors),
        now=time.time(),
        global_limit=3,
        per_agent_limit=2,
    )
    assert result.global_active_count == 1
    assert [row.task_id for row in result.dispatches] == [ready[0]["id"], ready[1]["id"]]
    assert len({row.task_id for row in result.dispatches}) == 2
    assert result.scope == "planning_only" and result.execution_connected is False
    assert result.core_authorization == "unverified"
    assert core.execute("list_tasks", auth(first))["tasks"] == task_before
    by_session = {actor["session_id"]: actor for actor in actors}
    for row in result.dispatches:
        actor = by_session[row.session_id]
        assert actor["agent_id"] == row.agent_id
        core.execute(
            "claim_task",
            {
                **auth(actor),
                "task_id": row.task_id,
                "expected_version": row.expected_version,
                "request_id": "explicit-" + row.task_id,
            },
        )
    current = core.execute("list_tasks", auth(first))["tasks"]
    owners = Counter(row["owner_session_id"] for row in current if row["status"] == "claimed")
    assert sum(owners.values()) == 3 and max(owners.values()) <= 2


def test_expired_lease_keeps_slot_until_explicit_core_reclamation(world, monkeypatch):
    core, actors = world
    first, second = actors
    leased = create(core, second, "Lease to reclaim", 10)
    running = claim(core, second, leased, "claim-short", lease_seconds=1)
    create(core, first, "Waiting")
    snapshot = core.execute("get_project_state", auth(first))
    observed = running["lease_expires_at"] + 0.25
    arguments = {
        "project_id": first["project_id"],
        "worker_agent_ids": tuple(actor["agent_id"] for actor in actors),
        "now": observed,
        "global_limit": 1,
        "per_agent_limit": 1,
    }
    before = plan_dispatches(snapshot, **arguments)
    assert before.global_active_count == 1 and before.dispatches == ()
    assert core.execute("list_tasks", auth(first))["tasks"] == snapshot["tasks"]
    # Time is an external boundary; all state changes still use the public Core.
    with monkeypatch.context() as clock:
        clock.setattr("agentsync.core.service.time.time", lambda: observed)
        core.execute("reclaim_expired", auth(first))
        recovered = core.execute("get_project_state", auth(first))
        after = plan_dispatches(recovered, **arguments)
        assert after.global_active_count == 0
        assert len(after.dispatches) == 1 and after.dispatches[0].task_id == leased["id"]
        assert after.dispatches[0].expected_version == 3
        assert core.execute("list_tasks", auth(first))["tasks"] == recovered["tasks"]


def test_offline_handoff_recipient_is_not_replaced_by_another_available_worker(world, monkeypatch):
    core, (sender, recipient) = world
    reserved = create(core, sender, "Reserved", 100)
    ready = create(core, sender, "Unreserved", 1)
    owned = claim(core, sender, reserved, "claim-transfer")
    transfer = core.execute(
        "submit_handoff",
        {
            **auth(sender),
            "task_id": reserved["id"],
            "expected_version": owned["version"],
            "lease_token": owned["lease_token"],
            "target_agent_id": recipient["agent_id"],
            "package": {"summary": "Continue locally"},
            "request_id": "submit",
        },
    )
    accepted = core.execute(
        "resolve_handoff",
        {
            **auth(recipient),
            "handoff_id": transfer["id"],
            "expected_version": transfer["task_version"],
            "accept": True,
            "request_id": "accept",
        },
    )
    observed = time.time() + 121
    assert accepted["reservation_expires_at"] > observed
    with monkeypatch.context() as clock:
        clock.setattr("agentsync.core.service.time.time", lambda: observed)
        core.execute("heartbeat", auth(sender))
        snapshot = core.execute("get_project_state", auth(sender))
        result = plan_dispatches(
            snapshot,
            project_id=sender["project_id"],
            worker_agent_ids=(sender["agent_id"], recipient["agent_id"]),
            now=observed,
            global_limit=2,
            per_agent_limit=2,
        )
        assert [(row.task_id, row.agent_id) for row in result.dispatches] == [
            (ready["id"], sender["agent_id"])
        ]
        assert core.execute("list_tasks", auth(sender))["tasks"] == snapshot["tasks"]

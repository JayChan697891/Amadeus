"""Real local Core observations; a planning recommendation grants no claim."""

import time

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.scheduling import plan_tasks


@pytest.fixture
def world(tmp_path):
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "Planning", "root_path": str(tmp_path)})
    actors = []
    for name in ("First", "Second"):
        registered = core.execute("register_agent", {**project, "name": name})
        owner_grant(core, project, registered, roles=("worker",))
        actors.append(
            {
                "project_id": project["project_id"],
                "session_id": registered["session_id"],
                "session_token": registered["session_token"],
                "agent_id": registered["agent_id"],
            }
        )
    return core, actors


def auth(actor):
    return {key: value for key, value in actor.items() if key != "agent_id"}


def test_planning_uses_core_dependencies_and_priority_without_changing_tasks(world):
    core, (actor, _) = world
    parent = core.execute(
        "create_task", {**auth(actor), "title": "Parent", "priority": 2, "request_id": "parent"}
    )
    low = core.execute(
        "create_task", {**auth(actor), "title": "Low", "priority": 1, "request_id": "low"}
    )
    core.execute(
        "create_task",
        {
            **auth(actor),
            "title": "Dependent",
            "priority": 100,
            "dependencies": [parent["id"]],
            "request_id": "dependent",
        },
    )
    snapshot = core.execute("list_tasks", auth(actor))
    result = plan_tasks(
        snapshot, project_id=actor["project_id"], agent_id=actor["agent_id"], now=time.time()
    )
    assert [item.task_id for item in result.candidates] == [parent["id"], low["id"]]
    assert result.scope == "planning_only" and result.execution_connected is False
    assert core.execute("list_tasks", auth(actor)) == snapshot
    assert Core(core.data_dir).execute("list_tasks", auth(actor)) == snapshot


def test_core_rejects_stale_recommendation_after_another_worker_claims(world):
    core, (first, second) = world
    task = core.execute("create_task", {**auth(first), "title": "Race", "request_id": "create"})
    result = plan_tasks(
        core.execute("list_tasks", auth(first)),
        project_id=first["project_id"],
        agent_id=first["agent_id"],
        now=time.time(),
    )
    candidate = result.candidates[0]
    core.execute(
        "claim_task",
        {
            **auth(second),
            "task_id": task["id"],
            "expected_version": 1,
            "request_id": "second-claim",
        },
    )
    after_claim = core.execute("list_tasks", auth(first))
    with pytest.raises(AgentSyncError) as exc:
        core.execute(
            "claim_task",
            {
                **auth(first),
                "task_id": candidate.task_id,
                "expected_version": candidate.expected_version,
                "request_id": "stale-plan",
            },
        )
    assert exc.value.code == "version_conflict"
    assert core.execute("list_tasks", auth(first)) == after_claim
    assert after_claim["tasks"][0]["owner_session_id"] == second["session_id"]


def test_accepted_handoff_public_reservation_filters_plans_and_core_claims(tmp_path):
    core = Core(tmp_path / "handoff-state")
    project = core.execute(
        "create_project", {"name": "Planning handoff", "root_path": str(tmp_path)}
    )
    workers = []
    for name in ("Sender", "Recipient", "Other worker"):
        registered = core.execute("register_agent", {**project, "name": name})
        owner_grant(core, project, registered, roles=("worker",))
        workers.append(
            {
                "project_id": project["project_id"],
                "session_id": registered["session_id"],
                "session_token": registered["session_token"],
                "agent_id": registered["agent_id"],
            }
        )
    sender, recipient, other = workers
    task = core.execute(
        "create_task", {**auth(sender), "title": "Reserved handoff", "request_id": "create"}
    )
    lease = core.execute(
        "claim_task",
        {
            **auth(sender),
            "task_id": task["id"],
            "expected_version": task["version"],
            "request_id": "sender-claim",
        },
    )
    transfer = core.execute(
        "submit_handoff",
        {
            **auth(sender),
            "task_id": task["id"],
            "expected_version": lease["version"],
            "lease_token": lease["lease_token"],
            "target_agent_id": recipient["agent_id"],
            "package": {"summary": "Continue this local task"},
            "request_id": "submit",
        },
    )
    resolved = core.execute(
        "resolve_handoff",
        {
            **auth(recipient),
            "handoff_id": transfer["id"],
            "expected_version": transfer["task_version"],
            "accept": True,
            "request_id": "accept",
        },
    )
    assert resolved["status"] == "accepted"
    assert (
        core.execute("get_handoff", {**auth(recipient), "handoff_id": transfer["id"]}) == resolved
    )
    snapshot = core.execute("list_tasks", auth(recipient))
    public = snapshot["tasks"][0]
    now = time.time()
    assert public["status"] == "pending"
    assert public["assigned_agent_id"] == recipient["agent_id"]
    assert public["assignment_expires_at"] == resolved["reservation_expires_at"] > now
    recipient_plan = plan_tasks(
        snapshot, project_id=project["project_id"], agent_id=recipient["agent_id"], now=now
    )
    assert [
        (candidate.task_id, candidate.expected_version) for candidate in recipient_plan.candidates
    ] == [(task["id"], public["version"])]
    for unassigned in (sender, other):
        assert (
            plan_tasks(
                snapshot, project_id=project["project_id"], agent_id=unassigned["agent_id"], now=now
            ).candidates
            == ()
        )
    assert core.execute("list_tasks", auth(recipient)) == snapshot
    with pytest.raises(AgentSyncError) as exc:
        core.execute(
            "claim_task",
            {
                **auth(other),
                "task_id": public["id"],
                "expected_version": public["version"],
                "request_id": "other-claim",
            },
        )
    assert exc.value.code == "assignment_denied"
    assert core.execute("list_tasks", auth(recipient)) == snapshot
    candidate = recipient_plan.candidates[0]
    claimed = core.execute(
        "claim_task",
        {
            **auth(recipient),
            "task_id": candidate.task_id,
            "expected_version": candidate.expected_version,
            "request_id": "recipient-claim",
        },
    )
    assert claimed["status"] == "claimed" and claimed["owner_session_id"] == recipient["session_id"]


def test_in_flight_handoff_is_not_a_candidate_but_other_pending_work_is(world):
    core, (sender, recipient) = world
    transferring = core.execute(
        "create_task",
        {**auth(sender), "title": "Transfer in progress", "request_id": "transfer-task"},
    )
    ready = core.execute(
        "create_task", {**auth(sender), "title": "Other ready work", "request_id": "ready-task"}
    )
    lease = core.execute(
        "claim_task",
        {
            **auth(sender),
            "task_id": transferring["id"],
            "expected_version": transferring["version"],
            "request_id": "sender-claim",
        },
    )
    core.execute(
        "submit_handoff",
        {
            **auth(sender),
            "task_id": transferring["id"],
            "expected_version": lease["version"],
            "lease_token": lease["lease_token"],
            "target_agent_id": recipient["agent_id"],
            "package": {"summary": "Awaiting normal recipient decision"},
            "request_id": "submit",
        },
    )
    snapshot = core.execute("list_tasks", auth(recipient))
    assert (
        next(row for row in snapshot["tasks"] if row["id"] == transferring["id"])["status"]
        == "handoff"
    )
    result = plan_tasks(
        snapshot,
        project_id=recipient["project_id"],
        agent_id=recipient["agent_id"],
        now=time.time(),
    )
    assert [(candidate.task_id, candidate.expected_version) for candidate in result.candidates] == [
        (ready["id"], ready["version"])
    ]
    assert core.execute("list_tasks", auth(recipient)) == snapshot

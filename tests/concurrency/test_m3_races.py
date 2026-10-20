"""Competing M3 writes must have exactly one transactional winner."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def actors(core, tmp_path):
    project = core.execute("create_project", {"name": "races", "root_path": str(tmp_path)})
    result = []
    for name in ("sender", "receiver"):
        registered = core.execute("register_agent", {**project, "name": name})
        auth = {key: registered[key] for key in ("session_id", "session_token")}
        result.append((auth | {"project_id": project["project_id"]}, registered["agent_id"]))
    return result


def compete(core, operations):
    barrier = Barrier(len(operations))

    def execute(item):
        # Distinct Core instances/connections model independent callers of one DB.
        contender = Core(core.data_dir)
        barrier.wait(timeout=15)
        try:
            return contender.execute(*item)
        except AgentSyncError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        results = list(executor.map(execute, operations))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, AgentSyncError) for result in results) == len(operations) - 1
    return next(result for result in results if isinstance(result, dict))


def test_context_update_race_has_one_revision_and_replay_is_immutable(tmp_path):
    core = Core(tmp_path / "db")
    (a, _), (b, _) = actors(core, tmp_path)
    initial = core.execute(
        "publish_context",
        {**a, "kind": "note", "title": "Race", "content": "Original", "request_id": "initial"},
    )
    operations = [
        (
            "publish_context",
            {
                **auth,
                "kind": "decision",
                "title": "Race",
                "content": content,
                "context_id": initial["id"],
                "expected_version": 1,
                "request_id": "update",
            },
        )
        for auth, content in ((a, "Alpha"), (b, "Beta"))
    ]
    winner = compete(core, operations)
    assert winner["version"] == 2
    assert core.execute("get_context", {**a, "context_id": initial["id"], "version": 1}) == initial
    assert core.execute("get_context", {**a, "context_id": initial["id"]}) == winner
    with pytest.raises(AgentSyncError):
        core.execute("get_context", {**a, "context_id": initial["id"], "version": 3})
    winning_request = next(item for item in operations if item[1]["content"] == winner["content"])
    assert core.execute(*winning_request) == winner


@pytest.mark.parametrize("accept", [True, False])
def test_resolve_withdraw_race_never_changes_completed_decision(tmp_path, accept):
    core = Core(tmp_path / "db")
    (a, a_id), (b, b_id) = actors(core, tmp_path)
    task = core.execute("create_task", {**a, "title": "Race", "request_id": "create"})
    lease = core.execute(
        "claim_task",
        {**a, "task_id": task["id"], "expected_version": task["version"], "request_id": "claim"},
    )
    transfer = core.execute(
        "submit_handoff",
        {
            **a,
            "task_id": task["id"],
            "lease_token": lease["lease_token"],
            "expected_version": lease["version"],
            "target_agent_id": b_id,
            "package": {"summary": "Race decision"},
            "request_id": "submit",
        },
    )
    common = {
        "handoff_id": transfer["id"],
        "expected_version": transfer["task_version"],
        "reason": "Decision",
    }
    operations = [
        ("resolve_handoff", {**b, **common, "accept": accept, "request_id": "resolve"}),
        ("withdraw_handoff", {**a, **common, "request_id": "withdraw"}),
    ]
    winner = compete(core, operations)
    assert core.execute("get_handoff", {**a, "handoff_id": transfer["id"]}) == winner
    current = core.execute("list_tasks", a)["tasks"][0]
    assert current["version"] == transfer["task_version"] + 1
    assert current["status"] == "pending"
    assert current["assigned_agent_id"] == (b_id if winner["status"] == "accepted" else a_id)
    for operation, request in operations:
        with pytest.raises(AgentSyncError):
            core.execute(operation, {**request, "request_id": request["request_id"] + "-again"})
    assert core.execute("list_tasks", a)["tasks"][0] == current


def test_context_update_concurrent_with_handoff_pins_requested_revision(tmp_path):
    core = Core(tmp_path / "db")
    (a, _), (_, b_id) = actors(core, tmp_path)
    initial = core.execute(
        "publish_context",
        {**a, "kind": "note", "title": "Pinned", "content": "Original", "request_id": "initial"},
    )
    task = core.execute("create_task", {**a, "title": "Transfer", "request_id": "create"})
    lease = core.execute(
        "claim_task",
        {**a, "task_id": task["id"], "expected_version": task["version"], "request_id": "claim"},
    )
    operations = [
        (
            "publish_context",
            {
                **a,
                "kind": "note",
                "title": "New",
                "content": "Revised",
                "context_id": initial["id"],
                "expected_version": 1,
                "request_id": "update",
            },
        ),
        (
            "submit_handoff",
            {
                **a,
                "task_id": task["id"],
                "expected_version": lease["version"],
                "lease_token": lease["lease_token"],
                "target_agent_id": b_id,
                "package": {
                    "summary": "Fixed snapshot",
                    "context_refs": [{"context_id": initial["id"], "version": 1}],
                },
                "request_id": "handoff",
            },
        ),
    ]
    barrier = Barrier(2)

    def execute(item):
        contender = Core(core.data_dir)
        barrier.wait(timeout=15)
        return contender.execute(*item)

    with ThreadPoolExecutor(max_workers=2) as executor:
        updated, transfer = list(executor.map(execute, operations))
    assert updated["version"] == 2
    assert transfer["contexts"] == [initial]
    reopened = Core(core.data_dir)
    assert reopened.execute("get_handoff", {**a, "handoff_id": transfer["id"]})["contexts"] == [
        initial
    ]

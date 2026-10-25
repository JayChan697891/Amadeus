"""Local Mock simulation never changes the authoritative Core task lifecycle."""

import pytest
from conftest import owner_grant

from agentsync.adapters import AdapterTask, MockAdapter
from agentsync.core.service import Core


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True], ids=["pending", "running"])
@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled", "timed_out"])
async def test_mock_terminal_result_preserves_core_task_and_persisted_state(
    tmp_path, claimed, outcome
):
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "Mock boundary", "root_path": str(tmp_path)})
    registered = core.execute(
        "register_agent",
        {
            "project_id": project["project_id"],
            "admin_token": project["admin_token"],
            "name": "Local adapter observer",
            "capabilities": [],
        },
    )
    owner_grant(core, project, registered, roles=("worker",))
    actor = {
        "project_id": project["project_id"],
        "session_id": registered["session_id"],
        "session_token": registered["session_token"],
    }
    task = core.execute(
        "create_task", {**actor, "title": "Unverified simulation", "request_id": "create"}
    )
    if claimed:
        lease = core.execute(
            "claim_task",
            {
                **actor,
                "task_id": task["id"],
                "expected_version": task["version"],
                "request_id": "claim",
            },
        )
        core.execute(
            "update_task",
            {
                **actor,
                "task_id": task["id"],
                "expected_version": lease["version"],
                "lease_token": lease["lease_token"],
                "status": "running",
                "request_id": "run",
            },
        )
    before = core.execute("list_tasks", actor)["tasks"]
    assert before[0]["status"] == ("running" if claimed else "pending")
    now = [10.0]
    adapter = MockAdapter(actor["project_id"], actor["session_id"], clock=lambda: now[0])
    run = await adapter.start_task(
        AdapterTask(actor["project_id"], actor["session_id"], task["id"], "mock-only")
    )
    if outcome == "cancelled":
        await adapter.cancel_task(run.run_id)
    elif outcome == "timed_out":
        now[0] = 310.0
        await adapter.get_status(run.run_id)
    else:
        await adapter.finish_run(
            run.run_id, output="Explicit simulated result", failed=outcome == "failed"
        )
    result = await adapter.get_result(run.run_id)
    assert result.run.status == outcome
    assert result.simulated is True
    assert result.execution_connected is False
    assert result.verification == "unverified"
    assert core.execute("list_tasks", actor)["tasks"] == before
    reopened = Core(tmp_path / "state")
    assert reopened.execute("list_tasks", actor)["tasks"] == before

"""Synthetic Claude JSONL from known Python never grants real Core acceptance."""

import asyncio
import json
import sys

import pytest
from conftest import owner_grant

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def claude_core_world(tmp_path):
    core = Core(tmp_path / "core-state")
    project = core.execute(
        "create_project", {"name": "Claude protocol fixture", "root_path": str(tmp_path)}
    )
    registered = core.execute(
        "register_agent", {**project, "name": "Fixture actor", "capabilities": []}
    )
    owner_grant(core, project, registered, roles=("worker",))
    actor = {
        "project_id": project["project_id"],
        "session_id": registered["session_id"],
        "session_token": registered["session_token"],
    }
    task = core.execute(
        "create_task", {**actor, "title": "Protocol cannot accept", "request_id": "create"}
    )
    return core, actor, task


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True], ids=["pending", "running"])
async def test_claude_protocol_success_preserves_actual_core_and_reopened_state(
    tmp_path, claude_core_world, claimed
):
    core, actor, task = claude_core_world
    if claimed:
        claim = core.execute(
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
                "expected_version": claim["version"],
                "lease_token": claim["lease_token"],
                "status": "running",
                "request_id": "running",
            },
        )
    before = core.execute("get_project_state", actor)
    tasks_before = core.execute("list_tasks", actor)
    text = "\n".join(
        json.dumps(event)
        for event in [
            {"type": "system", "subtype": "init", "session_id": "synthetic-client-correlation"},
            {
                "type": "result",
                "subtype": "success",
                "session_id": "synthetic-client-correlation",
                "is_error": False,
                "result": "Synthetic protocol result, never evidence of task acceptance",
            },
        ]
    )
    request = AdapterTask(
        actor["project_id"], actor["session_id"], task["id"], "observe", timeout_seconds=3
    )
    calls = []

    async def known_python_factory(received):
        calls.append(received)
        source = f"import sys;sys.stdout.buffer.write({text.encode('utf-8')!r})"
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", source),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
        )

    adapter = ClaudeAdapter(actor["project_id"], actor["session_id"], factory=known_python_factory)
    begun = await adapter.start_task(request)
    async with asyncio.timeout(5):
        while (await adapter.get_status(begun.run_id)).status in {"starting", "running"}:
            await asyncio.sleep(0.01)
    result = await adapter.get_result(begun.run_id)
    assert result.run.status == "succeeded" and calls == [request]
    assert result.client_session_id == "synthetic-client-correlation"
    assert result.client_session_id != actor["session_id"]
    assert result.real_client_verified is False and result.core_authorization == "unverified"
    assert core.execute("get_project_state", actor) == before
    assert core.execute("list_tasks", actor) == tasks_before
    reopened = Core(core.data_dir)
    assert reopened.execute("get_project_state", actor) == before
    assert reopened.execute("list_tasks", actor) == tasks_before
    assert tasks_before["tasks"][0]["status"] == ("running" if claimed else "pending")


@pytest.mark.asyncio
async def test_claude_default_unsupported_does_not_mutate_core(claude_core_world):
    core, actor, task = claude_core_world
    before = core.execute("get_project_state", actor)
    adapter = ClaudeAdapter(actor["project_id"], actor["session_id"])
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(
            AdapterTask(actor["project_id"], actor["session_id"], task["id"], "unsupported")
        )
    assert error.value.code == "unsupported"
    assert core.execute("get_project_state", actor) == before
    assert Core(core.data_dir).execute("get_project_state", actor) == before

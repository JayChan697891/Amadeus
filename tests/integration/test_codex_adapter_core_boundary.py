"""Hand-authored JSONL from local Python, never a real Codex client or relay.

Real Core/SQLite state is compared across adapter observation and reopening.
The trusted test factory only prints fixed protocol data; it receives no Core
credential, runs no task instruction and cannot authorize task completion.
"""

import asyncio
import json
import sys

import pytest
from conftest import owner_grant

from agentsync.adapters import AdapterTask
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def protocol_core_world(tmp_path):
    core = Core(tmp_path / "state")
    project = core.execute(
        "create_project", {"name": "Protocol-only boundary", "root_path": str(tmp_path)}
    )
    registered = core.execute(
        "register_agent",
        {
            "project_id": project["project_id"],
            "admin_token": project["admin_token"],
            "name": "Protocol fixture observer",
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
        "create_task",
        {**actor, "title": "Protocol output does not grant acceptance", "request_id": "create"},
    )
    return core, actor, task


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True], ids=["pending", "running"])
async def test_codex_protocol_fixture_success_preserves_complete_core_and_reopened_state(
    tmp_path, protocol_core_world, claimed
):
    core, actor, task = protocol_core_world
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
    assert tasks_before["tasks"][0]["status"] == ("running" if claimed else "pending")
    text = "\n".join(
        json.dumps(event)
        for event in (
            {"type": "thread.started", "thread_id": "hand-authored-thread-only"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "fixture-message",
                    "type": "agent_message",
                    "text": "Protocol fixture only; never verified completion",
                },
            },
            {"type": "turn.completed"},
        )
    )
    calls = []
    request = AdapterTask(
        actor["project_id"], actor["session_id"], task["id"], "protocol-only", timeout_seconds=3
    )

    async def local_fixture_factory(adapter_task):
        calls.append(adapter_task)
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", f"import sys; sys.stdout.write({text!r})"),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
        )

    adapter = CodexAdapter(actor["project_id"], actor["session_id"], factory=local_fixture_factory)
    started = await adapter.start_task(request)
    async with asyncio.timeout(5):
        observed = await adapter.get_status(started.run_id)
        while observed.status in {"starting", "running"}:
            await asyncio.sleep(0.01)
            observed = await adapter.get_status(started.run_id)
    result = await adapter.get_result(started.run_id)
    assert calls == [request]
    assert observed.status == result.run.status == "succeeded"
    assert result.run.run_id == started.run_id
    assert result.run.project_id == actor["project_id"]
    assert result.run.session_id == actor["session_id"]
    assert result.run.task_id == task["id"]
    assert result.run.request_id == request.request_id
    assert result.client_thread_id == "hand-authored-thread-only"
    assert result.agent_messages == ("Protocol fixture only; never verified completion",)
    assert result.usage is None
    for view in (result, result.run):
        assert view.scope == "host_process_protocol"
        assert view.real_client_verified is False
        assert view.verification == "unverified"
        assert view.core_authorization == "unverified"
        assert view.tree_cleanup == "unverified"
    assert core.execute("get_project_state", actor) == before
    assert core.execute("list_tasks", actor) == tasks_before
    reopened = Core(core.data_dir)
    assert reopened.execute("get_project_state", actor) == before
    assert reopened.execute("list_tasks", actor) == tasks_before


@pytest.mark.asyncio
async def test_codex_default_factory_unavailable_preserves_authoritative_core_state(
    protocol_core_world,
):
    core, actor, task = protocol_core_world
    before = core.execute("get_project_state", actor)
    adapter = CodexAdapter(actor["project_id"], actor["session_id"])
    capability = await adapter.capabilities()
    assert capability.supports_start is False
    assert capability.real_client_verified is False
    assert capability.core_authorization == "unverified"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(
            AdapterTask(actor["project_id"], actor["session_id"], task["id"], "unavailable")
        )
    assert error.value.code == "unsupported"
    assert core.execute("get_project_state", actor) == before
    assert Core(core.data_dir).execute("get_project_state", actor) == before

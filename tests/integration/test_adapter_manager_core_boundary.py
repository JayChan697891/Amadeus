"""Local Python protocol fixtures are not real Agent executions or Core acceptance."""

import asyncio
import json
import sys

import pytest
from test_claude_adapter_core_boundary import claude_core_world as claude_core_world

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.manager import RunManager
from agentsync.adapters.mock import MockAdapter
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.core.service import Core


@pytest.mark.asyncio
async def test_heterogeneous_routes_preserve_protocol_markers_and_core(tmp_path, claude_core_world):
    core, actor, task = claude_core_world
    project, session = actor["project_id"], actor["session_id"]
    before = core.execute("get_project_state", actor)
    streams = {
        "codex": [
            {"type": "thread.started", "thread_id": "fixture"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "one", "type": "agent_message", "text": "fixture codex"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1},
            },
        ],
        "claude": [
            {"type": "system", "subtype": "init", "session_id": "fixture"},
            {
                "type": "result",
                "subtype": "success",
                "session_id": "fixture",
                "is_error": False,
                "result": "fixture claude",
            },
        ],
    }

    def factory(name):
        async def start(_task):
            text = "\n".join(json.dumps(event) for event in streams[name])
            return await CapturedProcess.start(
                (sys.executable, "-I", "-u", "-c", f"print({text!r})"),
                cwd=tmp_path,
                stdin_text="",
                timeout_seconds=5,
            )

        return start

    mock = MockAdapter(project, session)
    manager = RunManager(
        project,
        session,
        {
            "codex": CodexAdapter(project, session, factory=factory("codex")),
            "claude": ClaudeAdapter(project, session, factory=factory("claude")),
            "mock": mock,
        },
    )
    requests = [AdapterTask(project, session, task["id"], name) for name in streams]
    runs = await asyncio.gather(
        *(
            manager.start_task(name, request)
            for name, request in zip(streams, requests, strict=True)
        )
    )
    async with asyncio.timeout(10):
        for run in runs:
            while (await manager.get_status(run.handle)).run.status in {"starting", "running"}:
                await asyncio.sleep(0.01)
    results = [await manager.get_result(run.handle) for run in runs]
    assert results[0].agent_messages == ("fixture codex",)
    assert results[1].result_text == "fixture claude"
    for result in results:
        assert result.run.status == "succeeded"
        assert result.real_client_verified is False
        assert result.core_authorization == result.verification == "unverified"
    simulated = await manager.start_task("mock", AdapterTask(project, session, task["id"], "mock"))
    await mock.finish_run(simulated.run.run_id, output="simulation")
    simulated_result = await manager.get_result(simulated.handle)
    assert simulated_result.simulated is True
    assert simulated_result.execution_connected is False
    assert len({run.handle for run in [*runs, simulated]}) == 3
    assert core.execute("get_project_state", actor) == before
    assert Core(core.data_dir).execute("get_project_state", actor) == before

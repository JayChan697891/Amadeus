"""Synthetic local process results do not establish real Cursor or task acceptance."""

import asyncio
import json
import sys

import pytest
from test_claude_adapter_core_boundary import claude_core_world as claude_core_world

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor import CursorAdapter
from agentsync.adapters.manager import RunManager
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.usage import UsageLedger


@pytest.mark.parametrize("exit_code", [0, 7])
async def test_cursor_fixture_through_manager_preserves_actual_core(
    tmp_path, claude_core_world, exit_code
):
    core, actor, task = claude_core_world
    before = core.execute("get_project_state", actor)
    text = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 5,
            "duration_api_ms": 3,
            "session_id": "synthetic-client-id",
            "request_id": "untrusted-client-request",
            "result": "synthetic Cursor response",
        }
    )

    async def known_python(_task):
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", f"import sys;print({text!r});sys.exit({exit_code})"),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=5,
        )

    adapter = CursorAdapter(actor["project_id"], actor["session_id"], factory=known_python)
    manager = RunManager(actor["project_id"], actor["session_id"], {"cursor": adapter})
    run = await manager.start_task(
        "cursor", AdapterTask(actor["project_id"], actor["session_id"], task["id"], "observe")
    )
    async with asyncio.timeout(10):
        while (await manager.get_status(run.handle)).run.status in {"starting", "running"}:
            await asyncio.sleep(0.01)
    result = await manager.get_result(run.handle)
    assert result.run.status == ("failed" if exit_code else "succeeded")
    assert result.result_text == ("" if exit_code else "synthetic Cursor response")
    assert result.real_client_verified is False
    assert result.verification == result.core_authorization == "unverified"
    assert result.run.exit_code == exit_code
    ledger = UsageLedger(actor["project_id"])
    assert ledger.record_result(result) is True
    assert ledger.record_result(result) is False
    summary = ledger.summary()
    assert summary.protocol_records == 1 and summary.simulated_records == 0
    assert summary.input_tokens.value is summary.output_tokens.value is None
    assert summary.input_tokens.unknown_runs == summary.output_tokens.unknown_runs == 1
    assert summary.cost_usd is None and summary.billing_verified is False
    assert summary.adapter_elapsed_ms.value is not None
    assert core.execute("get_project_state", actor) == before
    assert Core(core.data_dir).execute("get_project_state", actor) == before


async def test_default_cursor_route_cannot_launch_or_change_core(claude_core_world):
    core, actor, task = claude_core_world
    before = core.execute("get_project_state", actor)
    adapter = CursorAdapter(actor["project_id"], actor["session_id"])
    manager = RunManager(actor["project_id"], actor["session_id"], {"cursor": adapter})
    assert (await manager.capabilities("cursor")).supports_start is False
    with pytest.raises(AgentSyncError) as error:
        await manager.start_task(
            "cursor", AdapterTask(actor["project_id"], actor["session_id"], task["id"], "denied")
        )
    assert error.value.code == "unsupported"
    assert core.execute("get_project_state", actor) == before
    assert Core(core.data_dir).execute("get_project_state", actor) == before

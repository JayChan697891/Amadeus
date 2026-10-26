"""Accidental trusted-host factory misuse; no subprocess or actual client."""

import asyncio

import pytest

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


@pytest.mark.parametrize("adapter_class", [CodexAdapter, ClaudeAdapter])
@pytest.mark.parametrize("stop", ["cancel", "deadline"])
@pytest.mark.asyncio
async def test_unstarted_factory_capture_stops_unknown_without_hanging(adapter_class, stop):
    processes = []

    async def factory(_request):
        process = CapturedProcess()
        processes.append(process)
        return process

    adapter = adapter_class("project", "session", factory=factory)
    task = AdapterTask("project", "session", "task", "request", timeout_seconds=1)
    run = await adapter.start_task(task)
    async with asyncio.timeout(3):
        while (await adapter.get_status(run.run_id)).status == "starting":
            await asyncio.sleep(0)
        if stop == "cancel":
            finished = await adapter.cancel_task(run.run_id)
        else:
            while (finished := await adapter.get_status(run.run_id)).status == "running":
                await asyncio.sleep(0.01)
    assert finished.status == "unknown" and finished.slot_held is True
    assert finished.timed_out is (stop == "deadline")
    assert finished.error_code == (
        "adapter_timeout" if stop == "deadline" else "local_cancel_requested"
    )
    assert finished.finished_at is not None
    assert finished.exit_code is None and finished.parent_ended is False
    assert finished.capture_state == "unknown"
    capture = await processes[0].snapshot()
    assert capture.error_code == "capture_not_started"
    assert capture.state == "unknown" and capture.parent_ended is False
    assert await adapter.start_task(task) == finished
    assert await adapter.cancel_task(run.run_id) == finished
    result = await adapter.get_result(run.run_id)
    assert result.run == finished
    assert result.real_client_verified is False and result.core_authorization == "unverified"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(AdapterTask("project", "session", "other", "replacement"))
    assert error.value.code == "running_capacity_exceeded"
    assert len(processes) == 1

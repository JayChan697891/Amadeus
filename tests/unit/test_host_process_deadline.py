"""Deterministic shared adapter deadline tests with zero real subprocesses."""

import asyncio
import sys
from types import SimpleNamespace

import pytest
from test_codex_adapter import stream
from test_process_capture_deadline import ClockLoop

from agentsync.adapters import _host_process
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.cursor import CursorAdapter
from agentsync.adapters.process_capture import CapturedProcess


@pytest.mark.parametrize(
    ("adapter_type", "outcome"),
    [
        (CodexAdapter, "factory-timeout"),
        (ClaudeAdapter, "capture-timeout"),
        (CursorAdapter, "cancel"),
        (CodexAdapter, "exit"),
    ],
    ids=["pending-factory", "owned-parent", "cancel-wins", "natural-exit-wins"],
)
@pytest.mark.asyncio
async def test_early_adapter_callback_waits_for_absolute_deadline(
    tmp_path, monkeypatch, adapter_type, outcome
):
    clock = ClockLoop(asyncio.get_running_loop())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: clock)
    monkeypatch.setattr(
        _host_process, "get_clock_info", lambda _: SimpleNamespace(resolution=0.025), raising=False
    )
    ready, release, factory_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pending = outcome == "factory-timeout"

    async def factory(_task):
        try:
            if pending:
                ready.set()
                await release.wait()
                raise RuntimeError("Pending factory fixture released without launching")
            capture = await CapturedProcess.start(
                (sys.executable, "-I", "-c", "pass"),
                cwd=tmp_path,
                stdin_text="",
                timeout_seconds=5,
                env={},
            )
            ready.set()
            return capture
        finally:
            factory_done.set()

    adapter = adapter_type("p", "s", factory=factory)
    run = await adapter.start_task(AdapterTask("p", "s", "t", "r", timeout_seconds=1))
    deadline = run.started_at + 1
    cancel_job = None
    try:
        await asyncio.wait_for(ready.wait(), 1)
        status = "starting" if pending else "running"
        assert (await adapter.get_status(run.run_id)).status == status
        timer = clock.timers[0]
        assert timer.when == deadline
        for early_by in (0.006, 0.001):
            clock.fire(timer, deadline - early_by)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert (await adapter.get_status(run.run_id)).status == status
            assert clock.transport is None if pending else clock.transport.kills == 0
            assert clock.timers[-1] is not timer
            timer = clock.timers[-1]
            assert timer.when >= clock.now + 0.025

        if outcome == "exit":
            clock.transport.protocol.pipe_data_received(1, stream().encode())
            clock.transport.exit(0)
            finished = await adapter.wait_terminal(run.run_id, timeout_seconds=1)
            assert finished.status == "succeeded" and not finished.timed_out
            assert finished.finished_at < deadline and clock.transport.kills == 0
        elif outcome == "cancel":

            def delay_parent_exit():
                clock.transport.kills += 1

            monkeypatch.setattr(clock.transport, "kill", delay_parent_exit)
            cancel_job = asyncio.create_task(adapter.cancel_task(run.run_id))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not cancel_job.done() and clock.transport.kills == 1
            clock.fire(timer, deadline)
            await asyncio.sleep(0)
            clock.transport.exit(-9)
            finished = await cancel_job
            assert finished.error_code == "local_cancel_requested" and not finished.timed_out
        else:
            clock.fire(timer, deadline)
            clock.fire(timer, deadline)
            finished = await adapter.wait_terminal(run.run_id, timeout_seconds=1)
            assert finished.status == "unknown" and finished.timed_out
            assert finished.error_code == ("factory_timeout" if pending else "adapter_timeout")
            assert finished.finished_at == deadline

        assert timer.cancelled
        clock.fire(timer, deadline)
        await asyncio.sleep(0)
        assert await adapter.get_status(run.run_id) == finished
        if pending:
            assert clock.transport is None
        else:
            assert finished.parent_ended and clock.transport.kills == (
                0 if outcome == "exit" else 1
            )
    finally:
        if cancel_job is not None and not cancel_job.done():
            clock.transport.exit(-9)
            await cancel_job
        await adapter.cancel_task(run.run_id)
        release.set()
        await asyncio.wait_for(factory_done.wait(), 1)

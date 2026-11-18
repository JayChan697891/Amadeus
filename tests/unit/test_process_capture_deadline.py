"""Deterministic timer/exit protocol fixtures, not real-client acceptance."""

import asyncio
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from agentsync.adapters import process_capture
from agentsync.adapters.process_capture import CapturedProcess


@dataclass
class Timer:
    when: float
    callback: object
    args: tuple
    cancelled: bool = False

    def cancel(self):
        self.cancelled = True


class Transport:
    def __init__(self, loop, protocol):
        self.loop = loop
        self.protocol = protocol
        self.returncode = None
        self.kills = 0

    def get_returncode(self):
        return self.returncode

    def get_pipe_transport(self, fd):
        return None

    def kill(self):
        self.kills += 1
        self.exit(-9)

    def exit(self, code):
        self.returncode = code
        self.loop.call_soon(self.protocol.pipe_connection_lost, 1, None)
        self.loop.call_soon(self.protocol.pipe_connection_lost, 2, None)
        self.loop.call_soon(self.protocol.process_exited)

    def close(self):
        pass


class ClockLoop:
    def __init__(self, real_loop):
        self.real_loop = real_loop
        self.now = 100.0
        self.timers = []
        self.transport = None

    def time(self):
        return self.now

    def create_future(self):
        return self.real_loop.create_future()

    def call_at(self, when, callback, *args):
        timer = Timer(when, callback, args)
        self.timers.append(timer)
        return timer

    def call_later(self, delay, callback, *args):
        return self.call_at(self.now + delay, callback, *args)

    async def subprocess_exec(self, protocol_factory, *args, **kwargs):
        protocol = protocol_factory()
        self.transport = Transport(self.real_loop, protocol)
        protocol.connection_made(self.transport)
        return self.transport, protocol

    def fire(self, timer, now):
        self.now = now
        # Also exercise callbacks already queued when their handle was cancelled.
        timer.callback(*timer.args)


async def start_fixture(tmp_path, monkeypatch):
    clock = ClockLoop(asyncio.get_running_loop())
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: clock)
    process = await CapturedProcess.start(
        (sys.executable, "-I", "-c", "pass"),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=0.1,
    )
    return process, clock


@pytest.mark.asyncio
@pytest.mark.parametrize("late_by", [0, 0.007])
async def test_early_callbacks_cannot_terminate_parent_before_deadline(
    tmp_path, monkeypatch, late_by
):
    monkeypatch.setattr(
        process_capture,
        "get_clock_info",
        lambda name: SimpleNamespace(resolution=0.025),
        raising=False,
    )
    process, clock = await start_fixture(tmp_path, monkeypatch)
    deadline = (await process.snapshot()).deadline_at
    assert clock.timers[0].when == deadline
    for early_by in (0.006, 0.001):
        timer = clock.timers[-1]
        clock.fire(timer, deadline - early_by)
        snapshot = await process.snapshot()
        assert snapshot.state == "running" and snapshot.finished_at is None
        assert snapshot.error_code is None and clock.transport.kills == 0
        assert clock.timers[-1] is not timer
        assert clock.timers[-1].when >= deadline
        assert clock.timers[-1].when > clock.now
        assert clock.timers[-1].when >= clock.now + 0.025
    clock.fire(clock.timers[-1], deadline + late_by)
    snapshot = await process.wait()
    assert snapshot.state == "timed_out" and snapshot.parent_ended is True
    assert snapshot.finished_at == deadline + late_by
    assert clock.transport.kills == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancelled", "exited"])
async def test_rearmed_deadline_cannot_override_cancel_or_natural_exit(
    tmp_path, monkeypatch, outcome
):
    process, clock = await start_fixture(tmp_path, monkeypatch)
    deadline = (await process.snapshot()).deadline_at
    clock.fire(clock.timers[-1], deadline - 0.006)
    rearmed = clock.timers[-1]
    if outcome == "cancelled":
        snapshot = await process.cancel()
    else:
        clock.transport.exit(0)
        snapshot = await process.wait()
    assert snapshot.state == outcome and snapshot.finished_at < deadline
    assert rearmed.cancelled
    count = len(clock.timers)
    clock.fire(rearmed, deadline)
    assert await process.snapshot() == snapshot
    assert len(clock.timers) == count
    assert clock.transport.kills == (1 if outcome == "cancelled" else 0)


@pytest.mark.asyncio
async def test_deadline_observes_returncode_before_queued_exit_callback(tmp_path, monkeypatch):
    process, clock = await start_fixture(tmp_path, monkeypatch)
    deadline = (await process.snapshot()).deadline_at
    clock.transport.exit(0)
    clock.fire(clock.timers[0], deadline)
    snapshot = await process.wait()
    assert snapshot.state == "exited" and snapshot.exit_code == 0
    assert clock.transport.kills == 0


@pytest.mark.asyncio
async def test_timeout_reason_survives_later_cancel_and_exit(tmp_path, monkeypatch):
    process, clock = await start_fixture(tmp_path, monkeypatch)
    deadline = (await process.snapshot()).deadline_at
    clock.fire(clock.timers[0], deadline)
    snapshot = await process.cancel()
    assert snapshot.state == "timed_out" and snapshot.finished_at == deadline
    assert await process.wait() == snapshot
    assert clock.transport.kills == 1


@pytest.mark.asyncio
async def test_pending_cancel_blocks_old_deadline_before_parent_exit(tmp_path, monkeypatch):
    process, clock = await start_fixture(tmp_path, monkeypatch)
    deadline = (await process.snapshot()).deadline_at
    clock.fire(clock.timers[0], deadline - 0.006)
    rearmed = clock.timers[-1]

    def delayed_kill():
        clock.transport.kills += 1

    monkeypatch.setattr(clock.transport, "kill", delayed_kill)
    cancelled = asyncio.create_task(process.cancel())
    try:
        await asyncio.sleep(0)
        assert not cancelled.done()
        assert (await process.snapshot()).error_code == "cancelled"
        timer_count = len(clock.timers)
        clock.fire(rearmed, deadline)
        assert clock.transport.kills == 1
        assert len(clock.timers) == timer_count
        assert (await process.snapshot()).error_code == "cancelled"
    finally:
        clock.transport.exit(-9)
        snapshot = await cancelled
    assert snapshot.state == "cancelled" and snapshot.parent_ended is True

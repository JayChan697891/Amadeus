"""Bounded routing and dispatch ownership, without clients or process execution."""

import asyncio
from dataclasses import replace

import pytest

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.manager import RunManager
from agentsync.adapters.mock import MockAdapter
from agentsync.errors import AgentSyncError


def task(request_id="request", **changes):
    return replace(AdapterTask("project", "session", "task", request_id), **changes)


class GateAdapter(MockAdapter):
    def __init__(self, *, failure=False):
        super().__init__("project", "session")
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.failure = failure

    async def start_task(self, task):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.failure:
            raise RuntimeError("private factory detail")
        return await super().start_task(task)


async def test_cancelled_caller_concurrent_replay_and_independent_start():
    slow = GateAdapter()
    fast = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"slow": slow, "fast": fast})
    caller = asyncio.create_task(manager.start_task("slow", task()))
    await slow.entered.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    fast_run = await asyncio.wait_for(manager.start_task("fast", task("other")), 1)
    replays = [asyncio.create_task(manager.start_task("slow", task())) for _ in range(5)]
    slow.release.set()
    results = await asyncio.gather(*replays)
    assert slow.calls == 1
    assert len({run.handle for run in results}) == 1
    assert results[0].run.run_id != results[0].handle
    assert manager.history() == (results[0].handle, fast_run.handle)
    assert (await manager.get_status(results[0].handle)).run == results[0].run


async def test_failed_dispatch_is_sanitized_and_permanently_consumes_capacity():
    adapter = GateAdapter(failure=True)
    adapter.release.set()
    manager = RunManager("project", "session", {"worker": adapter}, max_runs=1)
    for _ in range(2):
        with pytest.raises(AgentSyncError) as error:
            await manager.start_task("worker", task())
        assert error.value.code == "adapter_start_unknown"
        assert "private" not in str(error.value)
    assert adapter.calls == 1
    assert len(manager.history()) == 1
    with pytest.raises(AgentSyncError, match="history"):
        await manager.start_task("worker", task("new"))


async def test_scope_conflicts_registration_snapshot_and_terminal_history():
    adapter = MockAdapter("project", "session")
    registry = {"one": adapter, "two": MockAdapter("project", "session")}
    manager = RunManager("project", "session", registry, max_runs=1)
    registry.clear()
    first = await manager.start_task("one", task())
    for worker, request, code in [
        ("two", task(), "idempotency_conflict"),
        ("one", task(instruction="changed"), "idempotency_conflict"),
        ("one", task(session_id="foreign"), "namespace_mismatch"),
    ]:
        with pytest.raises(AgentSyncError) as error:
            await manager.start_task(worker, request)
        assert error.value.code == code
    other = RunManager("project", "session", {"one": adapter})
    for handle in (first.handle, first.run.run_id):
        with pytest.raises(AgentSyncError) as error:
            await other.get_status(handle)
        assert error.value.code == "not_found"
    assert (await manager.capabilities("one")).simulated is True
    cancelled = await manager.cancel_task(first.handle)
    result = await manager.get_result(first.handle)
    assert result.run == cancelled.run
    assert result.simulated is True and result.verification == "unverified"
    with pytest.raises(AgentSyncError) as error:
        await manager.resume_task(first.handle)
    assert error.value.code == "unsupported"
    with pytest.raises(AgentSyncError) as error:
        await manager.start_task("one", task("new"))
    assert error.value.code == "history_capacity_exceeded"


async def test_foreign_start_and_result_are_rejected():
    class Broken(MockAdapter):
        async def start_task(self, request):
            return replace(await super().start_task(request), session_id="foreign")

    manager = RunManager("project", "session", {"bad": Broken("project", "session")})
    with pytest.raises(AgentSyncError) as error:
        await manager.start_task("bad", task())
    assert error.value.code == "invalid_adapter_run"

    class BrokenResult(MockAdapter):
        async def get_result(self, run_id):
            result = await super().get_result(run_id)
            return replace(result, run=replace(result.run, run_id="foreign"))

    manager = RunManager("project", "session", {"bad": BrokenResult("project", "session")})
    run = await manager.start_task("bad", task())
    await manager.cancel_task(run.handle)
    with pytest.raises(AgentSyncError) as error:
        await manager.get_result(run.handle)
    assert error.value.code == "invalid_adapter_run"


@pytest.mark.parametrize("failure", [False, True])
async def test_dispatch_inspection_is_nonblocking_and_sanitized(failure):
    adapter = GateAdapter(failure=failure)
    manager = RunManager("project", "session", {"worker": adapter})
    caller = asyncio.create_task(manager.start_task("worker", task(instruction="private prompt")))
    await adapter.entered.wait()
    (handle,) = manager.history()
    pending = manager.get_dispatch(handle)
    assert pending.state == "pending" and pending.error_code is None
    assert (pending.project_id, pending.session_id, pending.task_id, pending.request_id) == (
        "project",
        "session",
        "task",
        "request",
    )
    foreign = RunManager("project", "session", {"worker": adapter})
    with pytest.raises(AgentSyncError) as error:
        foreign.get_dispatch(handle)
    assert error.value.code == "not_found"
    adapter.release.set()
    if failure:
        with pytest.raises(AgentSyncError):
            await caller
    else:
        receipt = await caller
        assert receipt.run.status == "running"
    observed = manager.get_dispatch(handle)
    assert observed.state == ("error" if failure else "returned")
    assert observed.error_code == ("adapter_start_unknown" if failure else None)
    assert "private" not in repr(observed)
    assert pending.state == "pending"
    assert adapter.calls == 1

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


async def test_wait_dispatch_timeout_preserves_original_receipt_and_capacity():
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter}, max_runs=1)
    caller = asyncio.create_task(manager.start_task("worker", task()))
    await adapter.entered.wait()
    (handle,) = manager.history()
    pending = await manager.wait_dispatch(handle, timeout_seconds=0.001)
    assert pending == manager.get_dispatch(handle)
    assert pending.state == "pending" and pending.error_code is None
    assert manager.history() == (handle,) and adapter.calls == 1
    with pytest.raises(AgentSyncError) as error:
        await manager.start_task("worker", task("other"))
    assert error.value.code == "history_capacity_exceeded"
    adapter.release.set()
    observed = await asyncio.wait_for(manager.wait_dispatch(handle, timeout_seconds=300), 1)
    receipt = await caller
    replay = await manager.start_task("worker", task())
    assert observed.state == "returned"
    assert observed.handle == receipt.handle == replay.handle == handle
    assert replay.run is receipt.run
    assert receipt.run.status == "running"
    assert pending.state == "pending" and adapter.calls == 1


async def test_cancelled_dispatch_waiter_leaves_driver_and_other_waiter_running():
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter})
    caller = asyncio.create_task(manager.start_task("worker", task()))
    await adapter.entered.wait()
    (handle,) = manager.history()
    cancelled = asyncio.create_task(manager.wait_dispatch(handle, timeout_seconds=300))
    survivor = asyncio.create_task(manager.wait_dispatch(handle, timeout_seconds=300))
    await asyncio.sleep(0)
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert manager.get_dispatch(handle).state == "pending"
    assert not caller.done() and not survivor.done()
    adapter.release.set()
    observed = await asyncio.wait_for(survivor, 1)
    assert observed.state == "returned"
    assert (await caller).handle == handle
    assert manager.history() == (handle,) and adapter.calls == 1


@pytest.mark.parametrize("failure", [False, True])
async def test_wait_dispatch_terminal_observation_is_prompt_and_sanitized(failure):
    adapter = GateAdapter(failure=failure)
    manager = RunManager("project", "session", {"worker": adapter})
    caller = asyncio.create_task(manager.start_task("worker", task(instruction="private prompt")))
    await adapter.entered.wait()
    (handle,) = manager.history()
    waiter = asyncio.create_task(manager.wait_dispatch(handle, timeout_seconds=300))
    await asyncio.sleep(0)
    assert not waiter.done()
    adapter.release.set()
    observed = await asyncio.wait_for(waiter, 1)
    if failure:
        with pytest.raises(AgentSyncError) as error:
            await caller
        assert error.value.code == "adapter_start_unknown"
    else:
        assert (await caller).run.status == "running"
    assert observed.state == ("error" if failure else "returned")
    assert observed.error_code == ("adapter_start_unknown" if failure else None)
    assert "private" not in repr(observed)
    assert await asyncio.wait_for(manager.wait_dispatch(handle, timeout_seconds=300), 1) == observed
    assert adapter.calls == 1


async def test_wait_dispatch_zero_is_an_immediate_poll():
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter})
    caller = asyncio.create_task(manager.start_task("worker", task()))
    await adapter.entered.wait()
    (handle,) = manager.history()
    observed = await asyncio.wait_for(manager.wait_dispatch(handle, timeout_seconds=0), 1)
    assert observed == manager.get_dispatch(handle)
    assert observed.state == "pending"
    adapter.release.set()
    await caller
    terminal = await manager.wait_dispatch(handle, timeout_seconds=0.0)
    assert terminal.state == "returned" and adapter.calls == 1


@pytest.mark.parametrize(
    "timeout",
    [
        True,
        False,
        None,
        "1",
        -1,
        300.001,
        float("nan"),
        float("inf"),
        float("-inf"),
        pytest.param(10**10000, id="huge-integer"),
    ],
)
async def test_wait_dispatch_rejects_invalid_timeout_without_dispatch(timeout):
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter})
    with pytest.raises(AgentSyncError) as error:
        await manager.wait_dispatch("missing", timeout_seconds=timeout)
    assert error.value.code == "validation_error"
    assert manager.history() == () and adapter.calls == 0


@pytest.mark.parametrize("handle", [None, "", 123, True, "missing"])
async def test_wait_dispatch_validates_handle_and_requires_existing_dispatch(handle):
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter})
    with pytest.raises(AgentSyncError) as error:
        await manager.wait_dispatch(handle, timeout_seconds=0)
    assert error.value.code == ("not_found" if handle == "missing" else "validation_error")
    assert manager.history() == () and adapter.calls == 0


async def test_dispatch_task_returns_pending_handle_for_wait_and_original_receipt():
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter})
    pending = await asyncio.wait_for(manager.dispatch_task("worker", task()), 1)
    await adapter.entered.wait()
    assert pending.state == "pending" and pending.error_code is None
    assert manager.history() == (pending.handle,)
    assert await manager.dispatch_task("worker", task()) == pending
    assert await manager.wait_dispatch(pending.handle, timeout_seconds=0) == pending
    adapter.release.set()
    observed = await manager.wait_dispatch(pending.handle, timeout_seconds=1)
    receipt = await manager.start_task("worker", task())
    assert observed.state == "returned" and observed.handle == receipt.handle == pending.handle
    assert await manager.dispatch_task("worker", task()) == observed
    assert receipt.run.status == "running" and adapter.calls == 1
    assert pending.state == "pending"


@pytest.mark.parametrize("start_first", [False, True])
async def test_concurrent_mixed_dispatch_and_start_admit_exactly_once(start_first):
    adapter = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter}, max_runs=1)
    starts, dispatches = [], []
    for _ in range(4):
        for start in (start_first, not start_first):
            if start:
                starts.append(asyncio.create_task(manager.start_task("worker", task())))
            else:
                dispatches.append(asyncio.create_task(manager.dispatch_task("worker", task())))
    snapshots = await asyncio.wait_for(asyncio.gather(*dispatches), 1)
    await adapter.entered.wait()
    (handle,) = manager.history()
    assert all(snapshot.handle == handle and snapshot.state == "pending" for snapshot in snapshots)
    assert all(not caller.done() for caller in starts)
    assert adapter.calls == 1
    adapter.release.set()
    receipts = await asyncio.gather(*starts)
    assert all(receipt.handle == handle and receipt.run is receipts[0].run for receipt in receipts)
    assert adapter.calls == 1


async def test_dispatch_task_rejects_changed_replay_and_foreign_scope():
    adapter = GateAdapter()
    other = GateAdapter()
    manager = RunManager("project", "session", {"worker": adapter, "other": other})
    pending = await manager.dispatch_task("worker", task())
    for worker, request, code in [
        ("other", task(), "idempotency_conflict"),
        ("worker", task(instruction="changed"), "idempotency_conflict"),
        ("worker", task(session_id="foreign"), "namespace_mismatch"),
    ]:
        with pytest.raises(AgentSyncError) as error:
            await manager.dispatch_task(worker, request)
        assert error.value.code == code
    assert manager.history() == (pending.handle,) and other.calls == 0
    adapter.release.set()
    assert (await manager.wait_dispatch(pending.handle, timeout_seconds=1)).state == "returned"
    assert adapter.calls == 1


async def test_dispatch_task_failure_replay_is_sanitized_and_consumes_capacity():
    adapter = GateAdapter(failure=True)
    manager = RunManager("project", "session", {"worker": adapter}, max_runs=1)
    pending = await manager.dispatch_task("worker", task(instruction="private prompt"))
    adapter.release.set()
    failed = await manager.wait_dispatch(pending.handle, timeout_seconds=1)
    assert failed.state == "error" and failed.error_code == "adapter_start_unknown"
    assert "private" not in repr(failed)
    assert await manager.dispatch_task("worker", task(instruction="private prompt")) == failed
    with pytest.raises(AgentSyncError) as error:
        await manager.start_task("worker", task(instruction="private prompt"))
    assert error.value.code == "adapter_start_unknown"
    with pytest.raises(AgentSyncError) as error:
        await manager.dispatch_task("worker", task("new"))
    assert error.value.code == "history_capacity_exceeded"
    assert manager.history() == (pending.handle,) and adapter.calls == 1

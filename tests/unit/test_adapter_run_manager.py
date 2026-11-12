"""Bounded routing and dispatch ownership, without clients or process execution."""

import asyncio
import traceback
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


async def test_manager_start_limit_rejects_new_requests_without_spawning_queued_starts():
    slow = GateAdapter()
    fast = MockAdapter("project", "session")
    manager = RunManager(
        "project",
        "session",
        {"slow": slow, "fast": fast},
        max_pending_starts=1,
    )
    first = await manager.dispatch_task("slow", task())
    await slow.entered.wait()
    try:
        assert await manager.dispatch_task("slow", task()) == first
        assert manager.capacity().pending_starts == manager.capacity().pending_start_limit == 1
        with pytest.raises(AgentSyncError) as rejected:
            await manager.dispatch_task("fast", task("second"))
        assert rejected.value.code == "pending_start_capacity_exceeded"
        assert manager.history() == (first.handle,)
    finally:
        slow.release.set()
        await asyncio.wait_for(manager.start_task("slow", task()), 5)
    second = await manager.start_task("fast", task("second"))
    assert manager.history() == (first.handle, second.handle)


async def test_active_run_limit_waits_for_a_terminal_observation_across_adapters():
    first = MockAdapter("project", "session")
    second = MockAdapter("project", "session")
    manager = RunManager(
        "project",
        "session",
        {"one": first, "two": second},
        max_active_runs=1,
    )
    running = await manager.start_task("one", task())
    assert await manager.start_task("one", task()) == running
    with pytest.raises(AgentSyncError) as limited:
        await manager.dispatch_task("two", task("other"))
    assert limited.value.code == "running_capacity_exceeded"
    assert manager.history() == (running.handle,)

    await first.cancel_task(running.run.run_id)
    with pytest.raises(AgentSyncError):
        await manager.dispatch_task("two", task("other"))
    observed = await manager.get_status(running.handle)
    assert observed.run.status == "cancelled"
    assert manager.capacity().held_active_slots == 0
    admitted = await manager.start_task("two", task("other"))
    assert manager.history() == (running.handle, admitted.handle)


async def test_active_run_limit_retains_uncertain_start():
    adapter = GateAdapter(failure=True)
    adapter.release.set()
    manager = RunManager("project", "session", {"worker": adapter}, max_active_runs=1)
    with pytest.raises(AgentSyncError) as unknown:
        await manager.start_task("worker", task())
    assert unknown.value.code == "adapter_start_unknown"
    with pytest.raises(AgentSyncError) as limited:
        await manager.dispatch_task("worker", task("other"))
    assert limited.value.code == "running_capacity_exceeded"
    assert adapter.calls == 1
    assert manager.capacity().held_active_slots == manager.capacity().active_limit == 1


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


LIFECYCLE_OPERATIONS = ("capabilities", "get_status", "get_result", "cancel_task", "resume_task")


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
@pytest.mark.parametrize("failure", ["runtime", "unknown_domain", "public_domain"])
async def test_lifecycle_errors_have_fixed_public_details(operation, failure, monkeypatch):
    class FailingAdapter(MockAdapter):
        async def fail(self, *args):
            if failure == "runtime":
                raise RuntimeError("private credential/prompt detail")
            raise AgentSyncError(
                "not_found" if failure == "public_domain" else "private_adapter_code",
                "private credential/prompt detail",
                599,
            )

    adapter = FailingAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    monkeypatch.setattr(adapter, operation, adapter.fail)
    with pytest.raises(AgentSyncError) as error:
        await getattr(manager, operation)(
            "worker" if operation == "capabilities" else receipt.handle
        )
    public = error.value
    assert public.code == (
        "not_found" if failure == "public_domain" else "adapter_operation_unknown"
    )
    assert public.message == (
        "Adapter run was not found."
        if failure == "public_domain"
        else "Adapter operation did not complete."
    )
    assert public.status_code == (404 if failure == "public_domain" else 409)
    assert public.__cause__ is None and public.__context__ is None
    assert "private" not in "".join(traceback.format_exception(public))
    assert manager.history() == (receipt.handle,)
    assert manager.get_dispatch(receipt.handle).state == "returned"
    assert (await manager.start_task("worker", task())).run is receipt.run


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
async def test_lifecycle_caller_cancellation_is_preserved(operation, monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(adapter, operation, blocked)
    caller = asyncio.create_task(
        getattr(manager, operation)("worker" if operation == "capabilities" else receipt.handle)
    )
    await entered.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert manager.history() == (receipt.handle,)
    assert manager.get_dispatch(receipt.handle).state == "returned"
    assert (await manager.start_task("worker", task())).run is receipt.run


@pytest.mark.parametrize("operation", ["start_task", *LIFECYCLE_OPERATIONS[1:]])
@pytest.mark.parametrize("field", ["run_id", "project_id"])
async def test_run_property_errors_are_invalid_receipts(operation, field, monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    class BrokenRun:
        def __getattr__(self, name):
            if name == field:
                raise RuntimeError("private credential/prompt detail")
            return getattr(receipt.run, name)

    async def malformed(*args):
        if operation == "get_result":
            return type("BrokenResult", (), {"run": BrokenRun()})()
        return BrokenRun()

    monkeypatch.setattr(adapter, operation, malformed)
    with pytest.raises(AgentSyncError) as error:
        if operation == "start_task":
            await manager.start_task("worker", task("other"))
        else:
            await getattr(manager, operation)(receipt.handle)
    assert error.value.code == "invalid_adapter_run"
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert manager.get_dispatch(receipt.handle).state == "returned"


async def test_result_property_errors_are_invalid_receipts(monkeypatch):
    class BrokenResult:
        @property
        def run(self):
            raise RuntimeError("private credential/prompt detail")

    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    async def malformed(*args):
        return BrokenResult()

    monkeypatch.setattr(adapter, "get_result", malformed)
    with pytest.raises(AgentSyncError) as error:
        await manager.get_result(receipt.handle)
    assert error.value.code == "invalid_adapter_run"
    assert error.value.__cause__ is None and error.value.__context__ is None


async def test_successful_private_result_is_returned_unchanged():
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    await adapter.finish_run(receipt.run.run_id, output="private prompt/result bytes: 密钥\n\x01")
    expected = await adapter.get_result(receipt.run.run_id)
    assert await manager.get_result(receipt.handle) is expected


@pytest.mark.parametrize(
    ("code", "message", "status"),
    [
        ("unsupported", "Operation is unsupported by this adapter.", 400),
        ("not_found", "Adapter run was not found.", 404),
        ("result_not_ready", "Adapter result is not ready.", 409),
        ("invalid_state", "Adapter run is in an invalid state.", 409),
        ("invalid_adapter_run", "Adapter returned an inconsistent run.", 409),
        ("namespace_mismatch", "Request does not match adapter namespace.", 403),
        ("capacity_exceeded", "Adapter capacity is exhausted.", 409),
        ("history_capacity_exceeded", "Adapter history capacity is exhausted.", 409),
        ("running_capacity_exceeded", "Adapter running capacity is exhausted.", 409),
        ("task_already_active", "Task already has an active adapter run.", 409),
        ("idempotency_conflict", "Request ID has different inputs.", 409),
        ("validation_error", "Invalid adapter input.", 400),
        pytest.param([], "Adapter operation did not complete.", 409, id="malformed-code"),
    ],
)
async def test_lifecycle_public_codes_have_static_messages_and_statuses(
    code, message, status, monkeypatch
):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    async def fail(*args):
        raise AgentSyncError(code, "private credential/prompt detail", 599)

    monkeypatch.setattr(adapter, "get_status", fail)
    with pytest.raises(AgentSyncError) as error:
        await manager.get_status(receipt.handle)
    assert error.value.code == (code if type(code) is str else "adapter_operation_unknown")
    assert error.value.message == message and error.value.status_code == status
    assert error.value.__cause__ is None and error.value.__context__ is None


async def test_start_with_malformed_error_code_has_fixed_failure_and_replay():
    class BrokenAdapter(MockAdapter):
        async def start_task(self, request):
            raise AgentSyncError([], "private credential/prompt detail", 599)

    manager = RunManager("project", "session", {"worker": BrokenAdapter("project", "session")})
    for _ in range(2):
        with pytest.raises(AgentSyncError) as error:
            await manager.start_task("worker", task())
        assert error.value.code == "adapter_start_unknown"
        assert error.value.__cause__ is None and error.value.__context__ is None
        assert "private" not in "".join(traceback.format_exception(error.value))
    (handle,) = manager.history()
    snapshot = manager.get_dispatch(handle)
    assert snapshot.state == "error" and snapshot.error_code == "adapter_start_unknown"


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS[1:])
async def test_lifecycle_uses_frozen_receipt_id_after_callback(operation, monkeypatch):
    class StatefulRun:
        def __init__(self, run):
            self.original = run
            self.broken = False
            self.id_reads = 0

        @property
        def run_id(self):
            self.id_reads += 1
            if self.broken:
                raise RuntimeError("private credential/prompt detail")
            return self.original.run_id

        def __getattr__(self, name):
            return getattr(self.original, name)

    class StatefulAdapter(MockAdapter):
        async def start_task(self, request):
            return StatefulRun(await super().start_task(request))

    adapter = StatefulAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    initial = receipt.run
    assert initial.id_reads == 1
    original_id = initial.original.run_id
    seen = []

    async def callback(run_id):
        seen.append(run_id)
        initial.broken = True
        if operation == "get_result":
            return type("Result", (), {"run": initial.original})()
        return initial.original

    monkeypatch.setattr(adapter, operation, callback)
    for _ in range(2):
        result = await getattr(manager, operation)(receipt.handle)
        assert result.run is initial.original
    assert seen == [original_id, original_id] and initial.id_reads == 1
    assert (await manager.start_task("worker", task())).run is initial


async def test_capabilities_descriptor_errors_have_fixed_public_details():
    class BrokenAdapter(MockAdapter):
        @property
        def capabilities(self):
            raise RuntimeError("private credential/prompt detail")

    manager = RunManager("project", "session", {"worker": BrokenAdapter("project", "session")})
    with pytest.raises(AgentSyncError) as error:
        await manager.capabilities("worker")
    assert error.value.code == "adapter_operation_unknown"
    assert error.value.__cause__ is None and error.value.__context__ is None


@pytest.mark.parametrize("operation", ["start_task", "capabilities"])
async def test_error_code_descriptor_errors_have_fixed_public_details(operation, monkeypatch):
    class BrokenError(AgentSyncError):
        def __init__(self):
            Exception.__init__(self, "private credential/prompt detail")

        @property
        def code(self):
            raise RuntimeError("private credential/prompt detail")

    adapter = MockAdapter("project", "session")

    async def callback(*args):
        raise BrokenError()

    monkeypatch.setattr(adapter, operation, callback)
    manager = RunManager("project", "session", {"worker": adapter})
    with pytest.raises(AgentSyncError) as error:
        if operation == "start_task":
            await manager.start_task("worker", task())
        else:
            await manager.capabilities("worker")
    assert error.value.code == (
        "adapter_start_unknown" if operation == "start_task" else "adapter_operation_unknown"
    )
    assert error.value.__cause__ is None and error.value.__context__ is None


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
async def test_lifecycle_internal_cancellation_has_fixed_public_details(operation, monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    async def fail(*args):
        raise asyncio.CancelledError("private credential/prompt detail")

    monkeypatch.setattr(adapter, operation, fail)
    with pytest.raises(AgentSyncError) as error:
        await getattr(manager, operation)(
            "worker" if operation == "capabilities" else receipt.handle
        )
    public = error.value
    assert public.code == "adapter_operation_unknown"
    assert public.message == "Adapter operation did not complete." and public.status_code == 409
    assert public.__cause__ is None and public.__context__ is None
    assert "private" not in "".join(traceback.format_exception(public))
    assert manager.history() == (receipt.handle,)
    assert manager.get_dispatch(receipt.handle).state == "returned"
    assert (await manager.start_task("worker", task())).run is receipt.run


@pytest.mark.parametrize("operation", ["start_task", *LIFECYCLE_OPERATIONS[1:]])
@pytest.mark.parametrize("field", ["run_id", "project_id"])
async def test_run_property_internal_cancellation_is_invalid_receipt(operation, field, monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    class BrokenRun:
        def __getattr__(self, name):
            if name == field:
                raise asyncio.CancelledError("private credential/prompt detail")
            return getattr(receipt.run, name)

    async def malformed(*args):
        if operation == "get_result":
            return type("BrokenResult", (), {"run": BrokenRun()})()
        return BrokenRun()

    monkeypatch.setattr(adapter, operation, malformed)
    with pytest.raises(AgentSyncError) as error:
        if operation == "start_task":
            await manager.start_task("worker", task("other"))
        else:
            await getattr(manager, operation)(receipt.handle)
    public = error.value
    assert public.code == "invalid_adapter_run"
    assert public.message in (
        "Adapter returned an inconsistent run.",
        "Adapter start did not return a usable run.",
    )
    assert public.status_code == 409
    assert public.__cause__ is None and public.__context__ is None
    assert "private" not in "".join(traceback.format_exception(public))
    assert manager.get_dispatch(receipt.handle).state == "returned"


async def test_result_property_internal_cancellation_is_invalid_receipt(monkeypatch):
    class BrokenResult:
        @property
        def run(self):
            raise asyncio.CancelledError("private credential/prompt detail")

    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())

    async def malformed(*args):
        return BrokenResult()

    monkeypatch.setattr(adapter, "get_result", malformed)
    with pytest.raises(AgentSyncError) as error:
        await manager.get_result(receipt.handle)
    public = error.value
    assert public.code == "invalid_adapter_run"
    assert public.message == "Adapter returned an inconsistent run." and public.status_code == 409
    assert public.__cause__ is None and public.__context__ is None
    assert "private" not in "".join(traceback.format_exception(public))


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
async def test_lifecycle_caller_cancellation_rewrapped_by_adapter_is_sanitized(
    operation, monkeypatch
):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError as error:
            raise asyncio.CancelledError("private credential/prompt detail") from error

    monkeypatch.setattr(adapter, operation, blocked)
    caller = asyncio.create_task(
        getattr(manager, operation)("worker" if operation == "capabilities" else receipt.handle)
    )
    await entered.wait()
    caller.cancel("private caller detail")
    with pytest.raises(asyncio.CancelledError) as error:
        await caller
    assert error.value.args == ()
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert caller.cancelled() and caller.cancelling() == 1
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert manager.history() == (receipt.handle,)
    assert manager.get_dispatch(receipt.handle).state == "returned"


@pytest.mark.parametrize("operation", LIFECYCLE_OPERATIONS)
async def test_lifecycle_rejects_uncleared_cancellation_before_callback(operation, monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    receipt = await manager.start_task("worker", task())
    entered = False

    async def callback(*args):
        nonlocal entered
        entered = True
        raise asyncio.CancelledError("private adapter detail")

    monkeypatch.setattr(adapter, operation, callback)

    async def caller_with_uncleared_cancellation():
        current = asyncio.current_task()
        current.cancel("private prior caller detail")
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        assert current.cancelling() == 1
        try:
            await getattr(manager, operation)(
                "worker" if operation == "capabilities" else receipt.handle
            )
        finally:
            current.uncancel()

    caller = asyncio.create_task(caller_with_uncleared_cancellation())
    with pytest.raises(asyncio.CancelledError) as error:
        await caller
    assert not entered
    assert error.value.args == ()
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert manager.history() == (receipt.handle,)
    assert manager.get_dispatch(receipt.handle).state == "returned"


async def test_capabilities_callback_cannot_swallow_uncleared_caller_cancellation(monkeypatch):
    adapter = MockAdapter("project", "session")
    manager = RunManager("project", "session", {"worker": adapter})
    entered = asyncio.Event()

    async def blocked():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return "private adapter result"

    monkeypatch.setattr(adapter, "capabilities", blocked)
    caller = asyncio.create_task(manager.capabilities("worker"))
    await entered.wait()
    caller.cancel("private caller detail")
    with pytest.raises(asyncio.CancelledError) as error:
        await caller
    assert caller.cancelled() and caller.cancelling() == 1
    assert error.value.args == ()
    assert error.value.__cause__ is None and error.value.__context__ is None
    assert "private" not in "".join(traceback.format_exception(error.value))
    assert manager.history() == ()

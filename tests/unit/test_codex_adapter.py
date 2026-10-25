"""Trusted factory and known Python process fixtures, never real Codex evidence."""

import asyncio
import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


def stream():
    return "\n".join(
        json.dumps(event)
        for event in [
            {"type": "thread.started", "thread_id": "fixture-thread"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "m", "type": "agent_message", "text": "fixture answer"},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 2, "cached_input_tokens": 0, "output_tokens": 1},
            },
        ]
    )


def task(request="r", **changes):
    payload = dict(
        project_id="p",
        session_id="s",
        task_id="t",
        request_id=request,
        instruction="private prompt",
    )
    payload.update(changes)
    return AdapterTask(**payload)


async def terminal(adapter, run_id):
    for _ in range(500):
        snapshot = await adapter.get_status(run_id)
        if snapshot.status not in {"starting", "running"}:
            return snapshot
        await asyncio.sleep(0.01)
    pytest.fail("Known fixture did not reach a terminal observation")


def factory_for(tmp_path, *, text=None, exit_code=0, delay=0, timeout=3, output_limit=1048576):
    async def factory(_task):
        source = f"import sys,time; time.sleep({delay!r}); sys.stdout.write({stream() if text is None else text!r}); sys.exit({exit_code!r})"
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", source),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=timeout,
            output_limit=output_limit,
        )

    return factory


@pytest.mark.asyncio
async def test_fixture_protocol_success_has_independent_unverified_records(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path))
    started = await adapter.start_task(task())
    finished = await terminal(adapter, started.run_id)
    result = await adapter.get_result(started.run_id)
    assert finished.status == "succeeded" and finished.capture_state == "exited"
    assert finished.exit_code == 0 and finished.parent_ended is True
    assert result.agent_messages == ("fixture answer",)
    assert result.client_thread_id == "fixture-thread"
    assert result.usage.input_tokens == 2
    assert finished.scope == "host_process_protocol"
    assert finished.provenance == "trusted_host_factory"
    assert finished.real_client_verified is False
    assert finished.verification == finished.core_authorization == "unverified"
    assert not hasattr(finished, "simulated")
    assert "private prompt" not in repr(finished)


@pytest.mark.asyncio
async def test_default_capabilities_do_not_authorize_or_start_any_client():
    adapter = CodexAdapter("p", "s")
    capabilities = await adapter.capabilities()
    assert capabilities.supports_start is False
    assert capabilities.supports_server_cancel is capabilities.supports_resume is False
    assert capabilities.cancel_scope == "owned_parent_only"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task())
    assert error.value.code == "unsupported"


@pytest.mark.parametrize(
    "options,status,error",
    [
        ({"exit_code": 7}, "failed", "process_failed"),
        ({"text": '{"type":"thread.started","thread_id":"t"}'}, "unknown", "incomplete_stream"),
        ({"text": "malformed private payload"}, "unknown", "protocol_invalid"),
        ({"text": '{"type":"error","message":"private failure"}'}, "failed", "upstream_error"),
    ],
)
@pytest.mark.asyncio
async def test_process_and_protocol_observations_are_not_task_acceptance(
    tmp_path, options, status, error
):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path, **options))
    started = await adapter.start_task(task())
    finished = await terminal(adapter, started.run_id)
    assert (finished.status, finished.error_code) == (status, error)
    assert finished.slot_held is (status == "unknown")
    assert "private failure" not in repr(finished)
    if status == "unknown":
        assert (await adapter.get_result(started.run_id)).agent_messages == ()


@pytest.mark.parametrize(
    "options,state,timed_out",
    [
        ({"delay": 0.3, "timeout": 0.1}, "timed_out", True),
        ({"text": "x" * 1000, "output_limit": 128}, "output_limit", False),
    ],
)
@pytest.mark.asyncio
async def test_terminated_or_truncated_parent_keeps_client_unknown_and_slot_held(
    tmp_path, options, state, timed_out
):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path, **options))
    started = await adapter.start_task(task())
    finished = await terminal(adapter, started.run_id)
    assert finished.status == "unknown"
    assert finished.capture_state == state and finished.timed_out is timed_out
    assert finished.parent_ended is True and finished.slot_held is True
    assert (await adapter.get_result(started.run_id)).agent_messages == ()
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("replacement", task_id="other-task"))
    assert error.value.code == "running_capacity_exceeded"


@pytest.mark.asyncio
async def test_starting_replay_is_atomic_and_calls_factory_once(tmp_path):
    gate = asyncio.Event()
    called = asyncio.Event()
    count = 0
    real_factory = factory_for(tmp_path)

    async def factory(request):
        nonlocal count
        count += 1
        called.set()
        await gate.wait()
        return await real_factory(request)

    adapter = CodexAdapter("p", "s", factory=factory)
    first, second = await asyncio.gather(adapter.start_task(task()), adapter.start_task(task()))
    await called.wait()
    assert first.run_id == second.run_id and count == 1
    assert (await adapter.get_status(first.run_id)).status == "starting"
    gate.set()
    await terminal(adapter, first.run_id)
    assert (await adapter.start_task(task())).run_id == first.run_id
    assert count == 1


@pytest.mark.asyncio
async def test_request_conflict_and_namespace_errors_do_not_call_factory(tmp_path):
    count = 0
    real_factory = factory_for(tmp_path)

    async def factory(request):
        nonlocal count
        count += 1
        return await real_factory(request)

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    await terminal(adapter, first.run_id)
    for request, code in [
        (task(instruction="changed"), "idempotency_conflict"),
        (task("other", session_id="foreign"), "namespace_mismatch"),
    ]:
        with pytest.raises(AgentSyncError) as error:
            await adapter.start_task(request)
        assert error.value.code == code
    assert count == 1


@pytest.mark.asyncio
async def test_factory_failure_is_static_unknown_and_never_retried():
    count = 0

    async def factory(_request):
        nonlocal count
        count += 1
        raise RuntimeError("private argv and credentials")

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_failed"
    assert finished.slot_held is True and "private" not in repr(finished)
    assert await adapter.start_task(task()) == finished
    assert count == 1


@pytest.mark.asyncio
async def test_running_result_not_ready_and_parent_cancel_is_not_server_cancel(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path, delay=0.4))
    first = await adapter.start_task(task())
    assert first.status == "starting"
    with pytest.raises(AgentSyncError) as error:
        await adapter.get_result(first.run_id)
    assert error.value.code == "result_not_ready"
    for _ in range(100):
        if (await adapter.get_status(first.run_id)).status == "running":
            break
        await asyncio.sleep(0.005)
    running = await adapter.get_status(first.run_id)
    assert running.capture_state == "running" and running.capture_id is not None
    cancelled = await adapter.cancel_task(first.run_id)
    assert cancelled.status == "unknown" and cancelled.capture_state == "cancelled"
    assert cancelled.slot_held is True
    assert await adapter.cancel_task(first.run_id) == cancelled


@pytest.mark.asyncio
async def test_history_never_evicts_and_replay_precedes_capacity(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path), max_runs=1)
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    assert finished.slot_held is False
    assert await adapter.start_task(task()) == finished
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("new"))
    assert error.value.code == "history_capacity_exceeded"


@pytest.mark.asyncio
async def test_running_capacity_is_atomic_for_different_requests(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path, delay=0.1))
    results = await asyncio.gather(
        adapter.start_task(task("one", task_id="first")),
        adapter.start_task(task("two", task_id="second")),
        return_exceptions=True,
    )
    errors = [value for value in results if isinstance(value, AgentSyncError)]
    runs = [value for value in results if not isinstance(value, Exception)]
    assert len(errors) == len(runs) == 1
    assert errors[0].code == "running_capacity_exceeded"
    await terminal(adapter, runs[0].run_id)
    next_run = await adapter.start_task(task("three"))
    assert (await terminal(adapter, next_run.run_id)).status == "succeeded"


@pytest.mark.asyncio
async def test_cancelled_factory_has_static_unknown_history_and_once_call():
    count = 0

    async def factory(_request):
        nonlocal count
        count += 1
        raise asyncio.CancelledError("private factory detail")

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_cancelled"
    assert finished.slot_held and count == 1
    assert await adapter.start_task(task()) == finished


@pytest.mark.asyncio
async def test_invalid_factory_return_does_not_leave_starting_or_enable_retry():
    async def factory(_request):
        return None

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_invalid_result"
    assert await adapter.start_task(task()) == finished


@pytest.mark.asyncio
async def test_factory_deadline_late_handle_cleanup_does_not_rewrite_unknown(tmp_path):
    gate, called, returned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    processes = []
    real_factory = factory_for(tmp_path, delay=0.1)

    async def factory(request):
        process = await real_factory(request)
        processes.append(process)
        called.set()
        await gate.wait()
        returned.set()
        return process

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task(timeout_seconds=1))
    await called.wait()
    assert (await processes[0].wait()).state == "exited"
    finished = await terminal(adapter, first.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_timeout"
    assert finished.timed_out and finished.slot_held and finished.capture_id is None
    gate.set()
    await returned.wait()
    await asyncio.sleep(0.05)
    assert await adapter.get_status(first.run_id) == finished
    result = await adapter.get_result(first.run_id)
    assert result.agent_messages == () and result.client_thread_id is None
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("new", task_id="other-task"))
    assert error.value.code == "running_capacity_exceeded"


@pytest.mark.asyncio
async def test_caller_cancellation_does_not_cancel_background_factory(tmp_path):
    gate, called = asyncio.Event(), asyncio.Event()
    real_factory = factory_for(tmp_path)

    async def factory(request):
        called.set()
        await gate.wait()
        return await real_factory(request)

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    await called.wait()
    observer = asyncio.create_task(terminal(adapter, first.run_id))
    await asyncio.sleep(0)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    gate.set()
    assert (await terminal(adapter, first.run_id)).status == "succeeded"


@pytest.mark.asyncio
async def test_cancel_before_factory_returns_is_frozen_unknown_and_late_parent_is_observed(
    tmp_path,
):
    gate, called, returned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    processes = []
    real_factory = factory_for(tmp_path, delay=0.15)

    async def factory(request):
        process = await real_factory(request)
        processes.append(process)
        called.set()
        await gate.wait()
        returned.set()
        return process

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    await called.wait()
    cancelled = await adapter.cancel_task(first.run_id)
    assert cancelled.status == "unknown" and cancelled.slot_held
    gate.set()
    await returned.wait()
    assert (await processes[0].wait()).state in {"cancelled", "exited"}
    assert await adapter.get_status(first.run_id) == cancelled


@pytest.mark.asyncio
async def test_terminal_results_are_frozen_private_and_resume_unsupported(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path))
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    result = await adapter.get_result(first.run_id)
    with pytest.raises(FrozenInstanceError):
        result.agent_messages = ("changed",)
    with pytest.raises(FrozenInstanceError):
        finished.status = "unknown"
    with pytest.raises(AgentSyncError) as error:
        await adapter.resume_task(first.run_id)
    assert error.value.code == "unsupported"
    assert await adapter.cancel_task(first.run_id) == finished
    assert "fixture answer" not in repr(result)


@pytest.mark.asyncio
async def test_run_ids_are_isolated_and_unknown_access_does_not_invoke_factory(tmp_path):
    left = CodexAdapter("p", "s", factory=factory_for(tmp_path))
    right = CodexAdapter("p", "s", factory=factory_for(tmp_path))
    first = await left.start_task(task())
    finished = await terminal(left, first.run_id)
    for operation in (right.get_status, right.get_result, right.cancel_task, right.resume_task):
        with pytest.raises(AgentSyncError) as error:
            await operation(first.run_id)
        assert error.value.code == "not_found"
    assert await left.get_status(first.run_id) == finished


@pytest.mark.parametrize(
    "options",
    [
        {"max_runs": True},
        {"max_runs": 0},
        {"running_limit": 101},
        {"running_limit": 1.0},
        {"factory": "not a callable"},
    ],
)
def test_constructor_limits_and_factory_are_strict(options):
    with pytest.raises(AgentSyncError) as error:
        CodexAdapter("p", "s", **options)
    assert error.value.code == "validation_error"


@pytest.mark.asyncio
async def test_invalid_task_and_invalid_namespace_never_execute():
    adapter = CodexAdapter("p", "s")
    for value, code in [
        (None, "validation_error"),
        (task(project_id="foreign"), "namespace_mismatch"),
    ]:
        with pytest.raises(AgentSyncError) as error:
            await adapter.start_task(value)
        assert error.value.code == code


@pytest.mark.asyncio
async def test_same_task_active_request_is_not_spawned_twice_but_terminal_can_restart(tmp_path):
    gate = asyncio.Event()
    count = 0
    real_factory = factory_for(tmp_path)

    async def factory(request):
        nonlocal count
        count += 1
        await gate.wait()
        return await real_factory(request)

    adapter = CodexAdapter("p", "s", factory=factory, running_limit=2)
    values = await asyncio.gather(
        adapter.start_task(task("one")), adapter.start_task(task("two")), return_exceptions=True
    )
    gate.set()
    for value in values:
        if not isinstance(value, Exception):
            await terminal(adapter, value.run_id)
    errors = [value for value in values if isinstance(value, AgentSyncError)]
    assert len(errors) == 1 and errors[0].code == "task_already_active"
    assert count == 1
    restarted = await adapter.start_task(task("three"))
    assert (await terminal(adapter, restarted.run_id)).status == "succeeded"
    assert count == 2


@pytest.mark.asyncio
async def test_cancelling_local_cancel_waiter_preserves_cleanup_and_unknown_task_slot(tmp_path):
    adapter = CodexAdapter("p", "s", factory=factory_for(tmp_path, delay=0.3), running_limit=2)
    first = await adapter.start_task(task())
    for _ in range(100):
        if (await adapter.get_status(first.run_id)).status == "running":
            break
        await asyncio.sleep(0.005)
    cancellation = asyncio.create_task(adapter.cancel_task(first.run_id))
    await asyncio.sleep(0)
    cancellation.cancel()
    try:
        await cancellation
    except asyncio.CancelledError:
        pass
    finished = await terminal(adapter, first.run_id)
    assert finished.status == "unknown" and finished.capture_state == "cancelled"
    assert finished.slot_held
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("same-task-replacement"))
    assert error.value.code == "task_already_active"


@pytest.mark.asyncio
async def test_local_spawn_failure_is_unknown_without_raw_stderr_or_missing_path(tmp_path):
    async def factory(_request):
        return await CapturedProcess.start(
            (str(tmp_path / "private-missing-client"),),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=1,
        )

    adapter = CodexAdapter("p", "s", factory=factory)
    first = await adapter.start_task(task())
    finished = await terminal(adapter, first.run_id)
    result = await adapter.get_result(first.run_id)
    assert finished.status == "unknown" and finished.capture_state == "failed_to_start"
    assert finished.slot_held and finished.error_code == "spawn_failed"
    assert result.agent_messages == () and result.client_thread_id is None
    assert not hasattr(result, "stderr")
    assert "private" not in repr(finished)


@pytest.mark.asyncio
async def test_factory_capture_reuse_is_unknown_without_cancelling_first_owner(tmp_path):
    processes = []

    async def factory(_request):
        if not processes:
            processes.append(await factory_for(tmp_path, delay=0.25)(_request))
        return processes[0]

    adapter = CodexAdapter("p", "s", factory=factory, running_limit=2)
    first = await adapter.start_task(task("first", task_id="one"))
    try:
        for _ in range(100):
            if (await adapter.get_status(first.run_id)).status == "running":
                break
            await asyncio.sleep(0.005)
        second = await adapter.start_task(task("second", task_id="two"))
        rejected = await terminal(adapter, second.run_id)
        accepted = await terminal(adapter, first.run_id)
        assert rejected.status == "unknown" and rejected.error_code == "capture_reused"
        assert rejected.slot_held and rejected.capture_id is None
        assert (await adapter.get_result(second.run_id)).agent_messages == ()
        assert accepted.status == "succeeded" and accepted.exit_code == 0
        assert (await adapter.get_result(first.run_id)).agent_messages == ("fixture answer",)
    finally:
        if processes:
            await processes[0].cancel()


@pytest.mark.asyncio
async def test_factory_cannot_bind_preexisting_finished_capture_to_new_task(tmp_path):
    process = await factory_for(tmp_path)(task())
    await process.wait()

    async def factory(_request):
        return process

    adapter = CodexAdapter("p", "s", factory=factory)
    try:
        first = await adapter.start_task(task())
        rejected = await terminal(adapter, first.run_id)
        assert rejected.status == "unknown" and rejected.error_code == "capture_stale"
        assert rejected.slot_held and rejected.capture_id is None
        result = await adapter.get_result(first.run_id)
        assert result.agent_messages == () and result.client_thread_id is None
    finally:
        await process.cancel()

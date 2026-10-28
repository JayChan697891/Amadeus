"""Known local Python helpers with synthetic Claude events; no actual client."""

import asyncio
import json
import sys
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.base import AdapterTask, AgentAdapter
from agentsync.adapters.claude import ClaudeAdapter, ClaudeResult, ClaudeRun
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


@pytest.mark.asyncio
async def test_default_adapter_contract_is_unverified_and_start_unsupported():
    adapter = ClaudeAdapter("project", "session")
    assert isinstance(adapter, AgentAdapter)
    caps = await adapter.capabilities()
    assert caps.supports_start is False
    assert caps.supports_server_cancel is caps.supports_resume is False
    assert caps.cancel_scope == "owned_parent_only"
    assert caps.scope == "host_process_protocol"
    assert caps.real_client_verified is False
    assert caps.core_authorization == caps.verification == "unverified"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(AdapterTask("project", "session", "task", "request"))
    assert error.value.code == "unsupported"


def task(request="request", **changes):
    values = dict(
        project_id="p",
        session_id="s",
        task_id="task",
        request_id=request,
        instruction="Private task data; never execute this text",
    )
    values.update(changes)
    return AdapterTask(**values)


def stream(*, result_changes=None, assistant_stop=None):
    events = [{"type": "system", "subtype": "init", "session_id": "private-client-session"}]
    if assistant_stop is not None:
        events.append(
            {
                "type": "assistant",
                "session_id": "private-client-session",
                "message": {"content": [], "stop_reason": assistant_stop},
            }
        )
    events.append(
        {
            "type": "result",
            "subtype": "success",
            "session_id": "private-client-session",
            "is_error": False,
            "result": "你好 fixture result",
            "usage": {"input_tokens": 2, "output_tokens": 3},
            **(result_changes or {}),
        }
    )
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def factory_for(tmp_path, *, text=None, exit_code=0, delay=0, timeout=3, output_limit=1048576):
    async def factory(_request):
        payload = stream() if text is None else text
        source = (
            f"import sys,time;time.sleep({delay!r});"
            f"sys.stdout.buffer.write({payload.encode('utf-8')!r});sys.exit({exit_code!r})"
        )
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", source),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=timeout,
            output_limit=output_limit,
        )

    return factory


async def terminal(adapter, run_id):
    async with asyncio.timeout(7):
        while True:
            state = await adapter.get_status(run_id)
            if state.status not in {"starting", "running"}:
                return state
            await asyncio.sleep(0.01)


async def running(adapter, run_id):
    async with asyncio.timeout(5):
        while True:
            state = await adapter.get_status(run_id)
            if state.status == "running":
                return state
            assert state.status == "starting"
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_known_helper_lifecycle_returns_private_typed_claude_observation(tmp_path):
    adapter = ClaudeAdapter("p", "s", factory=factory_for(tmp_path))
    begun = await adapter.start_task(task())
    assert type(begun) is ClaudeRun and begun.status == "starting"
    with pytest.raises(AgentSyncError) as error:
        await adapter.get_result(begun.run_id)
    assert error.value.code == "result_not_ready"
    finished = await terminal(adapter, begun.run_id)
    result = await adapter.get_result(begun.run_id)
    assert type(finished) is ClaudeRun and type(result) is ClaudeResult
    assert finished.status == "succeeded" and finished.exit_code == 0
    assert finished.parent_ended is True and finished.slot_held is False
    assert result.run == finished
    assert result.result_text == "你好 fixture result"
    assert result.client_session_id == "private-client-session"
    assert not hasattr(result, "client_thread_id")
    assert result.usage.input_tokens == 2 and result.usage.output_tokens == 3
    for value in (finished, result):
        assert value.scope == "host_process_protocol"
        assert value.provenance == "trusted_host_factory"
        assert value.real_client_verified is False
        assert value.verification == value.core_authorization == "unverified"
        assert value.tree_cleanup == "unverified"
        assert "Private task data" not in repr(value)
        assert "private-client-session" not in repr(value)
        assert "fixture result" not in repr(value)
    with pytest.raises(FrozenInstanceError):
        result.real_client_verified = True
    assert await adapter.get_result(begun.run_id) == result


@pytest.mark.parametrize(
    "text,exit_code,expected,error,slot",
    [
        (stream(), 7, "failed", "process_failed", False),
        (stream(result_changes={"is_error": True}), 0, "failed", "upstream_error", False),
        (stream(result_changes={"api_error_status": 429}), 0, "failed", "upstream_error", False),
        (stream(assistant_stop="max_tokens"), 0, "unknown", "incomplete_response", True),
        (stream(assistant_stop="refusal"), 0, "unknown", "incomplete_response", True),
        (
            '{"type":"system","subtype":"init","session_id":"fixture"}',
            0,
            "unknown",
            "incomplete_stream",
            True,
        ),
        ("not-json", 0, "unknown", "protocol_invalid", True),
        ('{"type":"future"}', 0, "unknown", "protocol_invalid", True),
    ],
    ids=[
        "nonzero",
        "upstream-error",
        "api-error",
        "max-tokens",
        "refusal",
        "partial",
        "invalid",
        "unsupported",
    ],
)
@pytest.mark.asyncio
async def test_known_helper_failure_or_incomplete_never_returns_completion_text(
    tmp_path, text, exit_code, expected, error, slot
):
    adapter = ClaudeAdapter("p", "s", factory=factory_for(tmp_path, text=text, exit_code=exit_code))
    begun = await adapter.start_task(task())
    finished = await terminal(adapter, begun.run_id)
    result = await adapter.get_result(begun.run_id)
    assert finished.status == expected and finished.error_code == error
    assert finished.slot_held is slot
    assert result.result_text == ""
    assert result.real_client_verified is False
    if slot:
        assert result.usage is None and result.client_session_id is None


@pytest.mark.asyncio
async def test_concurrent_request_replay_calls_factory_once_and_conflict_rejects(tmp_path):
    calls = []
    create = factory_for(tmp_path, delay=0.05)

    async def factory(request):
        calls.append(request)
        return await create(request)

    adapter = ClaudeAdapter("p", "s", factory=factory)
    views = await asyncio.gather(*(adapter.start_task(task()) for _ in range(20)))
    assert len({view.run_id for view in views}) == 1
    end = await terminal(adapter, views[0].run_id)
    assert end.status == "succeeded" and calls == [task()]
    assert await adapter.start_task(task()) == end
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task(instruction="Changed data"))
    assert error.value.code == "idempotency_conflict"
    assert calls == [task()]


@pytest.mark.asyncio
async def test_local_cancel_only_ends_owned_parent_and_keeps_unknown_slot(tmp_path):
    adapter = ClaudeAdapter("p", "s", factory=factory_for(tmp_path, delay=5, timeout=3))
    begun = await adapter.start_task(task())
    await running(adapter, begun.run_id)
    stopped = await adapter.cancel_task(begun.run_id)
    assert stopped.status == "unknown" and stopped.parent_ended is True
    assert stopped.error_code == "local_cancel_requested" and stopped.slot_held is True
    assert stopped.tree_cleanup == "unverified" and stopped.timed_out is False
    result = await adapter.get_result(begun.run_id)
    assert result.result_text == "" and result.client_session_id is result.usage is None
    assert await adapter.cancel_task(begun.run_id) == stopped
    assert await adapter.start_task(task()) == stopped
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("another", task_id="different-task"))
    assert error.value.code == "running_capacity_exceeded"
    with pytest.raises(AgentSyncError) as error:
        await adapter.resume_task(begun.run_id)
    assert error.value.code == "unsupported"


@pytest.mark.asyncio
async def test_adapter_timeout_observes_only_owned_parent_as_unknown(tmp_path):
    adapter = ClaudeAdapter("p", "s", factory=factory_for(tmp_path, delay=5, timeout=3))
    begun = await adapter.start_task(task(timeout_seconds=1))
    stopped = await terminal(adapter, begun.run_id)
    assert stopped.status == "unknown" and stopped.timed_out is True
    assert stopped.error_code == "adapter_timeout" and stopped.slot_held is True
    assert stopped.parent_ended is True and stopped.tree_cleanup == "unverified"
    assert (await adapter.get_result(begun.run_id)).result_text == ""


@pytest.mark.asyncio
async def test_factory_deadline_freezes_unknown_then_cleans_only_fresh_late_parent(tmp_path):
    release = asyncio.Event()
    captures = []

    async def delayed_factory(request):
        await release.wait()
        capture = await factory_for(tmp_path, delay=5, timeout=3)(request)
        captures.append(capture)
        return capture

    adapter = ClaudeAdapter("p", "s", factory=delayed_factory)
    begun = await adapter.start_task(task(timeout_seconds=1))
    stopped = await terminal(adapter, begun.run_id)
    assert stopped.status == "unknown" and stopped.error_code == "factory_timeout"
    assert stopped.slot_held is True and stopped.timed_out is True
    release.set()
    async with asyncio.timeout(4):
        while not captures:
            await asyncio.sleep(0.01)
        while not (await captures[0].snapshot()).parent_ended:
            await asyncio.sleep(0.01)
    assert await adapter.get_status(begun.run_id) == stopped
    assert (await adapter.get_result(begun.run_id)).result_text == ""


@pytest.mark.asyncio
async def test_reused_capture_is_rejected_without_stopping_first_run_parent(tmp_path):
    captures = []

    async def factory(request):
        if captures:
            return captures[0]
        capture = await factory_for(tmp_path, delay=5, timeout=3)(request)
        captures.append(capture)
        return capture

    adapter = ClaudeAdapter("p", "s", factory=factory, running_limit=2)
    first = await adapter.start_task(task())
    await running(adapter, first.run_id)
    try:
        second = await adapter.start_task(task("second", task_id="second-task"))
        rejected = await terminal(adapter, second.run_id)
        assert rejected.status == "unknown" and rejected.error_code == "capture_reused"
        assert rejected.slot_held is True
        assert (await adapter.get_status(first.run_id)).status == "running"
        assert (await captures[0].snapshot()).parent_ended is False
        assert (await adapter.get_result(second.run_id)).result_text == ""
    finally:
        await adapter.cancel_task(first.run_id)


@pytest.mark.asyncio
async def test_preexisting_capture_is_rejected_without_stopping_external_owner(tmp_path):
    external = await factory_for(tmp_path, delay=5, timeout=3)(task())

    async def borrowed(_request):
        return external

    adapter = ClaudeAdapter("p", "s", factory=borrowed)
    try:
        begun = await adapter.start_task(task())
        rejected = await terminal(adapter, begun.run_id)
        assert rejected.status == "unknown" and rejected.error_code == "capture_stale"
        assert rejected.slot_held is True
        assert (await external.snapshot()).parent_ended is False
    finally:
        await external.cancel()


@pytest.mark.asyncio
async def test_namespace_history_and_unknown_task_dedup_reject_without_new_factory(tmp_path):
    calls = []
    create = factory_for(tmp_path)

    async def factory(request):
        calls.append(request)
        return await create(request)

    adapter = ClaudeAdapter("p", "s", factory=factory, max_runs=1)
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task(project_id="other-project"))
    assert error.value.code == "namespace_mismatch" and calls == []
    begun = await adapter.start_task(task())
    assert (await terminal(adapter, begun.run_id)).status == "succeeded"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task("second", task_id="second-task"))
    assert error.value.code == "history_capacity_exceeded" and calls == [task()]
    unknown_adapter = ClaudeAdapter("p", "s", factory=factory_for(tmp_path, text="not-json"))
    unknown_run = await unknown_adapter.start_task(task())
    assert (await terminal(unknown_adapter, unknown_run.run_id)).status == "unknown"
    with pytest.raises(AgentSyncError) as error:
        await unknown_adapter.start_task(task("new-request"))
    assert error.value.code == "task_already_active"


@pytest.mark.parametrize(
    "configuration",
    [{"factory": False}, {"max_runs": True}, {"max_runs": 0}, {"running_limit": 0}],
)
def test_invalid_host_configuration_uses_client_specific_static_error(configuration):
    with pytest.raises(AgentSyncError) as error:
        ClaudeAdapter("p", "s", **configuration)
    assert error.value.code == "validation_error"
    assert error.value.message == "Invalid Claude adapter configuration."


@pytest.mark.asyncio
async def test_factory_exception_keeps_unknown_without_exposing_private_detail():
    async def failed_factory(_request):
        raise RuntimeError("private factory failure detail")

    adapter = ClaudeAdapter("p", "s", factory=failed_factory)
    begun = await adapter.start_task(task())
    stopped = await terminal(adapter, begun.run_id)
    assert stopped.status == "unknown" and stopped.error_code == "factory_failed"
    assert stopped.slot_held is True and "private factory" not in repr(stopped)
    result = await adapter.get_result(begun.run_id)
    assert result.result_text == "" and result.client_session_id is None

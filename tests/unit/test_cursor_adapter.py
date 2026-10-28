"""Known isolated Python helpers emit synthetic Cursor JSON, never Cursor."""

import asyncio
import json
import os
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from agentsync.adapters.base import AdapterTask, AgentAdapter
from agentsync.adapters.cursor import CursorAdapter, CursorResult, CursorRun
from agentsync.adapters.manager import RunManager
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


def known_python():
    # Own the base interpreter itself, rather than a Windows venv redirector.
    candidate = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def explicit_env():
    return {"SystemRoot": os.environ["SystemRoot"]} if "SystemRoot" in os.environ else {}


def task(request="request", **changes):
    return AdapterTask(
        "p", "s", "task", request, instruction="Private data, never execute", **changes
    )


def payload():
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 12,
            "duration_api_ms": 9,
            "result": "Synthetic 你好 reply",
            "session_id": "private-client-session",
            "request_id": "private-client-request",
        }
    )


def factory_for(tmp_path, *, text=None, exit_code=0, delay=0):
    async def factory(_request):
        data = payload() if text is None else text
        source = (
            f"import sys,time;time.sleep({delay!r});"
            f"sys.stdout.buffer.write({data.encode('utf-8')!r});sys.exit({exit_code!r})"
        )
        return await CapturedProcess.start(
            (sys.executable, "-I", "-u", "-c", source),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
            output_limit=1048576,
        )

    return factory


async def terminal(adapter, run_id):
    async with asyncio.timeout(7):
        while True:
            run = await adapter.get_status(run_id)
            if run.status not in {"starting", "running"}:
                return run
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_default_has_no_launch_factory_or_resume_authority():
    adapter = CursorAdapter("p", "s")
    assert isinstance(adapter, AgentAdapter)
    caps = await adapter.capabilities()
    assert caps.supports_start is caps.supports_resume is caps.supports_server_cancel is False
    assert caps.supports_cancel is True and caps.cancel_scope == "owned_parent_only"
    assert caps.real_client_verified is False
    assert caps.verification == caps.core_authorization == "unverified"
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(task())
    assert error.value.code == "unsupported"


@pytest.mark.asyncio
async def test_contextual_factory_binds_exact_task_and_observes_known_python_result(tmp_path):
    calls = []

    async def factory(request, context):
        calls.append(request)
        with pytest.raises(AgentSyncError) as error:
            context.check(replace(request, instruction="different input"))
        assert error.value.code == "validation_error"
        source = (
            "import json,sys; print(json.dumps({'type':'result','subtype':'success',"
            "'is_error':False,'duration_ms':1,'duration_api_ms':1,"
            "'session_id':'synthetic-session','result':sys.stdin.buffer.read().decode('utf-8')}))"
        )
        return await context.start(
            request,
            (known_python(), "-I", "-u", "-c", source),
            cwd=tmp_path,
            stdin_text=request.instruction,
            timeout_seconds=3,
            output_limit=4096,
            env=explicit_env(),
        )

    adapter = CursorAdapter("p", "s", contextual_factory=factory)
    request = task(timeout_seconds=5)
    assert (await adapter.capabilities()).supports_start
    start = await adapter.start_task(request)
    end = await terminal(adapter, start.run_id)
    result = await adapter.get_result(start.run_id)
    assert end.status == "succeeded" and end.parent_ended and not end.slot_held
    assert (
        result.result_text == request.instruction
        and result.client_session_id == "synthetic-session"
    )
    assert result.real_client_verified is False
    assert result.verification == result.core_authorization == result.tree_cleanup == "unverified"
    assert await adapter.start_task(request) == end and calls == [request]


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
@pytest.mark.asyncio
async def test_contextual_factory_stopped_during_setup_never_enters_capture(
    tmp_path, monkeypatch, stop
):
    entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Capture entered after observed stop")

    async def factory(request, context):
        entered.set()
        try:
            await release.wait()  # Controlled trusted-host setup, no Cursor preparation or launch.
            return await context.start(
                request,
                (known_python(),),
                cwd=tmp_path,
                stdin_text=request.instruction,
                timeout_seconds=1,
                output_limit=1024,
                env=explicit_env(),
            )
        finally:
            settled.set()

    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = CursorAdapter("p", "s", contextual_factory=factory)
    start = await adapter.start_task(task(timeout_seconds=1))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        frozen = (
            await adapter.cancel_task(start.run_id)
            if stop == "cancel"
            else await terminal(adapter, start.run_id)
        )
        assert frozen.status == "unknown" and frozen.slot_held
        assert frozen.timed_out is (stop == "deadline")
        release.set()
        await asyncio.wait_for(settled.wait(), 2)
        assert not calls and await adapter.get_status(start.run_id) == frozen
        assert (await adapter.get_result(start.run_id)).result_text == ""
        with pytest.raises(AgentSyncError) as error:
            await adapter.start_task(AdapterTask("p", "s", "another", "another"))
        assert error.value.code == "running_capacity_exceeded"
    finally:
        release.set()
        await asyncio.wait_for(settled.wait(), 2)


def test_contextual_configuration_rejects_mixed_or_noncallable_factory(tmp_path):
    with pytest.raises(AgentSyncError):
        CursorAdapter(
            "p", "s", factory=factory_for(tmp_path), contextual_factory=lambda task, ctx: None
        )
    with pytest.raises(AgentSyncError):
        CursorAdapter("p", "s", contextual_factory=False)


@pytest.mark.asyncio
async def test_synthetic_success_is_typed_private_and_manager_compatible(tmp_path):
    adapter = CursorAdapter("p", "s", factory=factory_for(tmp_path))
    manager = RunManager("p", "s", {"cursor": adapter})
    start = await manager.start_task("cursor", task())
    assert type(start.run) is CursorRun
    end = await terminal(adapter, start.run.run_id)
    result = await manager.get_result(start.handle)
    assert type(result) is CursorResult and result.run == end
    assert end.status == "succeeded" and end.exit_code == 0 and end.parent_ended
    assert not end.slot_held
    assert result.result_text == "Synthetic 你好 reply"
    assert result.client_session_id == "private-client-session"
    assert result.metadata.request_id == "private-client-request"
    assert result.metadata.duration_ms == 12 and result.metadata.duration_api_ms == 9
    assert result.metadata.caller_reported and result.metadata.verification == "unverified"
    assert (await manager.get_status(start.handle)).run == end
    assert (await manager.start_task("cursor", task())).handle == start.handle
    assert manager.get_dispatch(start.handle).state == "returned"
    for value in (end, result):
        assert value.real_client_verified is False
        assert value.verification == value.core_authorization == "unverified"
        assert value.tree_cleanup == "unverified"
        assert "private-" not in repr(value) and "reply" not in repr(value)
    with pytest.raises(FrozenInstanceError):
        result.real_client_verified = True
    with pytest.raises(AgentSyncError) as error:
        await adapter.resume_task(end.run_id)
    assert error.value.code == "unsupported"


@pytest.mark.parametrize(
    "text,exit_code,status,error,slot",
    [
        ("", 2, "failed", "process_failed", False),
        (payload(), 2, "failed", "process_failed", False),
        ("", 0, "unknown", "incomplete_response", True),
        ("not-json", 0, "unknown", "protocol_invalid", True),
        ('{"type":"assistant"}', 0, "unknown", "protocol_invalid", True),
        (payload() + "\n" + payload(), 0, "unknown", "protocol_invalid", True),
    ],
)
@pytest.mark.asyncio
async def test_failure_malformed_and_stream_json_never_release_success_text(
    tmp_path,
    text,
    exit_code,
    status,
    error,
    slot,
):
    adapter = CursorAdapter("p", "s", factory=factory_for(tmp_path, text=text, exit_code=exit_code))
    start = await adapter.start_task(task())
    end = await terminal(adapter, start.run_id)
    result = await adapter.get_result(start.run_id)
    assert end.status == status and end.error_code == error and end.slot_held is slot
    assert result.result_text == "" and result.client_session_id is result.metadata is None
    assert result.real_client_verified is False


@pytest.mark.asyncio
async def test_deadline_keeps_unknown_slot_and_parent_only_cleanup(tmp_path):
    adapter = CursorAdapter("p", "s", factory=factory_for(tmp_path, delay=5))
    start = await adapter.start_task(task(timeout_seconds=1))
    end = await terminal(adapter, start.run_id)
    assert end.status == "unknown" and end.error_code == "adapter_timeout"
    assert end.slot_held and end.timed_out and end.parent_ended
    assert end.tree_cleanup == "unverified"
    result = await adapter.get_result(start.run_id)
    assert result.result_text == "" and result.client_session_id is result.metadata is None
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(AdapterTask("p", "s", "another-task", "another-request"))
    assert error.value.code == "running_capacity_exceeded"

"""Pinned launch wiring and owned Python fixtures, never actual Codex evidence."""

import asyncio
import hashlib
import os
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from agentsync.adapters import codex_process
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.codex_invocation import CodexHostProfile, prepare_invocation
from agentsync.adapters.codex_process import CodexProcessFactory
from agentsync.adapters.launch_context import LaunchContext
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError

HELPER = """import json,sys
text=sys.stdin.buffer.read().decode('utf-8')
for event in [{'type':'thread.started','thread_id':'fixture'},
              {'type':'turn.started'},
              {'type':'item.completed','item':{'id':'m','type':'agent_message','text':text}},
              {'type':'turn.completed','usage':{'input_tokens':1,'cached_input_tokens':0,'output_tokens':1}}]:
 print(json.dumps(event),flush=True)
"""


def known_python():
    # Own the interpreter itself, rather than a Windows venv redirector parent.
    candidate = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


def fixture_profile(tmp_path):
    binary = tmp_path / "synthetic-never-executed.exe"
    binary.write_bytes(b"Nonexecutable pin fixture, never real Codex.\n")
    return CodexHostProfile(
        "p", "s", binary, tmp_path, hashlib.sha256(binary.read_bytes()).hexdigest()
    )


def request():
    return AdapterTask(
        **dict(
            project_id="p",
            session_id="s",
            task_id="t",
            request_id="r",
            instruction="literal 中文; never a shell command",
            timeout_seconds=5,
        )
    )


async def terminal(adapter, run_id):
    async def wait():
        while True:
            view = await adapter.get_status(run_id)
            if view.status not in {"starting", "running"}:
                return view
            await asyncio.sleep(0.005)

    return await asyncio.wait_for(wait(), 8)


def explicit_env(tmp_path):
    result = {"HOME": str(tmp_path / "empty-home")}
    if "SystemRoot" in os.environ:
        result["SystemRoot"] = os.environ["SystemRoot"]
    return result


@pytest.mark.asyncio
async def test_exact_pinned_fields_feed_fixture_capture_and_replay_only_once(tmp_path, monkeypatch):
    profile, task = fixture_profile(tmp_path), request()
    supplied = {**explicit_env(tmp_path), "OPENAI_API_KEY": "synthetic-excluded-secret"}
    expected = prepare_invocation(profile, task, environment=supplied)
    bridge = CodexProcessFactory(profile, environment=supplied)
    supplied["HOME"] = "mutated-parent-value"
    original_start = CapturedProcess.start
    calls = []

    async def fixture_start(cls, argv, **options):
        calls.append((argv, options))
        # Observe the exact production arguments, but execute ONLY known Python.
        assert argv == expected.argv and argv[0] != sys.executable
        assert options == dict(
            cwd=expected.cwd,
            stdin_text=expected.stdin_text,
            timeout_seconds=expected.timeout_seconds,
            output_limit=expected.output_limit,
            env=expected.child_env(),
        )
        return await original_start((known_python(), "-I", "-u", "-c", HELPER), **options)

    monkeypatch.setattr(CapturedProcess, "start", classmethod(fixture_start))
    adapter = CodexAdapter("p", "s", contextual_factory=bridge)
    run = await adapter.start_task(task)
    finished = await terminal(adapter, run.run_id)
    result = await adapter.get_result(run.run_id)
    assert finished.status == "succeeded" and finished.parent_ended
    assert result.agent_messages == (task.instruction,) and len(calls) == 1
    assert await adapter.start_task(task) == finished and len(calls) == 1
    assert result.real_client_verified is False and result.core_authorization == "unverified"
    assert result.tree_cleanup == "unverified" and "synthetic-excluded-secret" not in repr(bridge)
    assert profile.executable.read_bytes().startswith(b"Nonexecutable pin fixture")
    profile.executable.write_bytes(b"Changed between two factory invocations")
    second = await adapter.start_task(replace(task, task_id="second", request_id="second"))
    assert (await terminal(adapter, second.run_id)).status == "unknown"
    assert len(calls) == 1  # A second invocation must hash afresh, not reuse its first plan.


@pytest.mark.parametrize("change", ["binary", "root", "version"])
@pytest.mark.asyncio
async def test_fresh_pin_root_and_version_fail_before_any_capture(tmp_path, monkeypatch, change):
    profile = fixture_profile(tmp_path)
    bridge = CodexProcessFactory(profile, environment={})
    if change == "binary":
        profile.executable.write_bytes(b"changed synthetic binary")
    elif change == "root":
        bridge = CodexProcessFactory(replace(profile, root=tmp_path / "absent"), environment={})
    else:
        bridge = CodexProcessFactory(
            replace(profile, expected_cli_version="unsupported"), environment={}
        )
    calls = []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Capture entered for an invalid pinned profile")

    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = CodexAdapter("p", "s", contextual_factory=bridge)
    run = await adapter.start_task(request())
    finished = await terminal(adapter, run.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_failed"
    assert finished.slot_held and not calls
    assert (await adapter.get_result(run.run_id)).agent_messages == ()


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
@pytest.mark.asyncio
async def test_stopped_threaded_preparation_never_enters_capture(tmp_path, monkeypatch, stop):
    bridge = CodexProcessFactory(fixture_profile(tmp_path), environment={})
    entered, release, done = threading.Event(), threading.Event(), asyncio.Event()
    prepare, calls = codex_process.prepare_invocation, []

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Synthetic preparation barrier timed out")
        return prepare(*args, **kwargs)

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Launch after an observed stop")

    async def factory(task, context):
        try:
            return await bridge(task, context)
        finally:
            done.set()

    monkeypatch.setattr(codex_process, "prepare_invocation", blocked)
    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = CodexAdapter("p", "s", contextual_factory=factory)
    task = replace(request(), timeout_seconds=1)
    run = await adapter.start_task(task)
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        frozen = (
            await adapter.cancel_task(run.run_id)
            if stop == "cancel"
            else await terminal(adapter, run.run_id)
        )
        assert frozen.status == "unknown" and frozen.slot_held
        release.set()
        await asyncio.wait_for(done.wait(), 3)
        assert not calls and await adapter.get_status(run.run_id) == frozen
        assert frozen.timed_out is (stop == "deadline")
    finally:
        release.set()
        await asyncio.wait_for(done.wait(), 3)


@pytest.mark.asyncio
async def test_absolute_deadline_is_checked_before_delayed_timer_callback(tmp_path, monkeypatch):
    calls, timer_calls = [], []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Expired launch")

    async def factory(task, context):
        time.sleep(1.05)  # Fixed owned fixture: delay the loop's timer callback.
        assert timer_calls == []
        return await context.start(
            task,
            (sys.executable,),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=1,
            output_limit=1024,
            env={},
        )

    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = CodexAdapter("p", "s", contextual_factory=factory)
    schedule = adapter._schedule_timeout

    def timer(entry):
        timer_calls.append(True)
        schedule(entry)

    monkeypatch.setattr(adapter, "_schedule_timeout", timer)
    run = await adapter.start_task(replace(request(), timeout_seconds=1))
    finished = await terminal(adapter, run.run_id)
    assert finished.status == "unknown" and finished.timed_out and finished.slot_held
    assert not calls


@pytest.mark.asyncio
async def test_context_task_loop_and_one_attempt_even_after_start_exception(tmp_path, monkeypatch):
    captured, release, ready, calls = [], asyncio.Event(), asyncio.Event(), []
    options = dict(cwd=tmp_path, stdin_text="", timeout_seconds=1, output_limit=1024, env={})

    async def broken(*args, **kwargs):
        calls.append(True)
        raise OSError("synthetic private failure")

    async def factory(task, context):
        captured.append((task, context))
        ready.set()
        await release.wait()
        with pytest.raises(OSError):
            await context.start(task, (sys.executable,), **options)
        return await context.start(task, (sys.executable,), **options)

    monkeypatch.setattr(CapturedProcess, "start", broken)
    adapter = CodexAdapter("p", "s", contextual_factory=factory)
    run = await adapter.start_task(request())
    await asyncio.wait_for(ready.wait(), 2)
    task, context = captured[0]
    with pytest.raises(AgentSyncError):
        await context.start(replace(task, instruction="changed"), (sys.executable,), **options)

    def foreign_loop():
        with pytest.raises(AgentSyncError):
            asyncio.run(context.start(task, (sys.executable,), **options))

    await asyncio.to_thread(foreign_loop)
    assert not calls
    release.set()
    finished = await terminal(adapter, run.run_id)
    assert finished.status == "unknown" and finished.slot_held and len(calls) == 1
    with pytest.raises(AgentSyncError):
        await context.start(task, (sys.executable,), **options)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_late_scheduled_owned_python_parent_is_cleaned_without_rewriting_unknown(tmp_path):
    created, release, cleaned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    captures = []

    async def factory(task, context):
        process = await context.start(
            task,
            (known_python(), "-I", "-u", "-c", "import time; time.sleep(20)"),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
            output_limit=1024,
            env=explicit_env(tmp_path),
        )
        captures.append(process)
        created.set()
        await release.wait()
        return process

    adapter = CodexAdapter("p", "s", contextual_factory=factory)
    run = await adapter.start_task(request())
    try:
        await asyncio.wait_for(created.wait(), 2)
        frozen = await adapter.cancel_task(run.run_id)
        assert frozen.status == "unknown" and frozen.slot_held
        release.set()
        snapshot = await asyncio.wait_for(captures[0].wait(), 4)
        assert snapshot.parent_ended and snapshot.state == "cancelled"
        assert await adapter.get_status(run.run_id) == frozen
        assert (await adapter.get_result(run.run_id)).tree_cleanup == "unverified"
    finally:
        release.set()
        for process in captures:
            await process.cancel()
        cleaned.set()


@pytest.mark.asyncio
async def test_contextual_opt_in_preserves_unsupported_defaults_and_rejects_mixed_factories():
    adapter = CodexAdapter("p", "s")
    assert not (await adapter.capabilities()).supports_start
    with pytest.raises(AgentSyncError, match="factory"):
        await adapter.start_task(request())
    with pytest.raises(AgentSyncError):
        CodexAdapter("p", "s", factory=lambda task: None, contextual_factory=lambda task, ctx: None)
    with pytest.raises(AgentSyncError):
        LaunchContext()

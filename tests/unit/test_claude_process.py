"""Claude launch wiring through known Python fixtures; no real client execution."""

import asyncio
import hashlib
import os
import sys
import threading
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from agentsync.adapters import claude_process
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.claude_invocation import ClaudeHostProfile, prepare_invocation
from agentsync.adapters.claude_process import ClaudeProcessFactory
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError

HELPER = """import json,os,sys
text=sys.stdin.buffer.read().decode('utf-8')
assert 'ANTHROPIC_API_KEY' not in os.environ
assert 'AGENTSYNC_CLAUDE_PARENT_ONLY' not in os.environ
for event in [{'type':'system','subtype':'init','session_id':'synthetic-session'},
              {'type':'result','subtype':'success','session_id':'synthetic-session',
               'is_error':False,'result':text,'usage':{'input_tokens':2,'output_tokens':3}}]:
 print(json.dumps(event),flush=True)
"""


def fixture_profile(tmp_path):
    binary = tmp_path / "synthetic-never-executed-claude.exe"
    binary.write_bytes(b"Nonexecutable Claude pin fixture.\n")
    return ClaudeHostProfile(
        "p",
        "s",
        binary,
        tmp_path,
        hashlib.sha256(binary.read_bytes()).hexdigest(),
        model="explicit-fixture-model",
        max_timeout_seconds=3,
        output_limit=4096,
    )


def request():
    return AdapterTask("p", "s", "task", "request", "literal 中文 --model inert; $(data)", 5)


def explicit_env(tmp_path):
    result = {"HOME": str(tmp_path / "empty-home")}
    if "SystemRoot" in os.environ:
        result["SystemRoot"] = os.environ["SystemRoot"]
    return result


def known_python():
    # Use the owned interpreter, rather than a Windows venv redirector parent.
    candidate = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.is_file() else sys.executable


async def terminal(adapter, run_id):
    async with asyncio.timeout(7):
        while True:
            view = await adapter.get_status(run_id)
            if view.status not in {"starting", "running"}:
                return view
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_exact_claude_plan_private_input_copies_environment_and_replay_once(
    tmp_path, monkeypatch
):
    profile, task = fixture_profile(tmp_path), request()
    monkeypatch.setenv("AGENTSYNC_CLAUDE_PARENT_ONLY", "synthetic-parent-value")
    supplied = {**explicit_env(tmp_path), "ANTHROPIC_API_KEY": "synthetic-excluded-secret"}
    expected = prepare_invocation(profile, task, environment=supplied)
    bridge = ClaudeProcessFactory(profile, environment=supplied)
    assert bridge._profile == profile and bridge._profile is not profile
    with pytest.raises(FrozenInstanceError):
        bridge._profile = profile
    supplied["HOME"] = "mutated-parent-value"
    original_start, calls = CapturedProcess.start, []

    async def fixture_start(cls, argv, **options):
        calls.append((argv, options))
        assert argv == expected.argv and argv[0] != known_python()
        assert options == dict(
            cwd=expected.cwd,
            stdin_text=expected.stdin_text,
            timeout_seconds=expected.timeout_seconds,
            output_limit=expected.output_limit,
            env=expected.child_env(),
        )
        # A wiring spy substitutes ONLY the known local helper, never the plan binary.
        return await original_start((known_python(), "-I", "-u", "-c", HELPER), **options)

    monkeypatch.setattr(CapturedProcess, "start", classmethod(fixture_start))
    adapter = ClaudeAdapter("p", "s", contextual_factory=bridge)
    run = await adapter.start_task(task)
    finished = await terminal(adapter, run.run_id)
    result = await adapter.get_result(run.run_id)
    assert finished.status == "succeeded" and finished.parent_ended
    assert result.result_text == task.instruction and len(calls) == 1
    assert result.usage.input_tokens == 2 and result.usage.output_tokens == 3
    assert await adapter.start_task(task) == finished and len(calls) == 1
    assert result.real_client_verified is False
    assert result.verification == result.core_authorization == result.tree_cleanup == "unverified"
    assert "synthetic-excluded-secret" not in repr(bridge)
    assert os.environ["AGENTSYNC_CLAUDE_PARENT_ONLY"] == "synthetic-parent-value"
    profile.executable.write_bytes(b"Changed between invocations")
    second = await adapter.start_task(replace(task, task_id="second", request_id="second"))
    assert (await terminal(adapter, second.run_id)).status == "unknown"
    assert len(calls) == 1  # Every new invocation rechecks pinned bytes.


@pytest.mark.asyncio
async def test_cancelled_threaded_preparation_never_starts_and_keeps_unknown_slot(
    tmp_path, monkeypatch
):
    bridge = ClaudeProcessFactory(fixture_profile(tmp_path), environment={})
    entered, release, done = threading.Event(), threading.Event(), asyncio.Event()
    prepare, calls = claude_process.prepare_invocation, []

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Synthetic preparation barrier timed out")
        return prepare(*args, **kwargs)

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Capture entered after observed cancellation")

    async def factory(task, context):
        try:
            return await bridge(task, context)
        finally:
            done.set()

    monkeypatch.setattr(claude_process, "prepare_invocation", blocked)
    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = ClaudeAdapter("p", "s", contextual_factory=factory)
    run = await adapter.start_task(request())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        frozen = await adapter.cancel_task(run.run_id)
        assert frozen.status == "unknown" and frozen.slot_held
        release.set()
        await asyncio.wait_for(done.wait(), 3)
        assert not calls and await adapter.get_status(run.run_id) == frozen
        assert (await adapter.get_result(run.run_id)).result_text == ""
        with pytest.raises(AgentSyncError) as error:
            await adapter.start_task(replace(request(), task_id="other", request_id="other"))
        assert error.value.code == "running_capacity_exceeded"
    finally:
        release.set()
        await asyncio.wait_for(done.wait(), 3)


@pytest.mark.parametrize("change", ["root", "version"])
@pytest.mark.asyncio
async def test_invalid_host_plan_never_enters_capture(tmp_path, monkeypatch, change):
    profile = fixture_profile(tmp_path)
    profile = replace(
        profile,
        **(
            {"root": tmp_path / "absent"}
            if change == "root"
            else {"expected_cli_version": "unsupported"}
        ),
    )
    bridge, calls = ClaudeProcessFactory(profile, environment={}), []

    async def forbidden(*args, **kwargs):
        calls.append(True)
        pytest.fail("Capture entered for an invalid profile")

    monkeypatch.setattr(CapturedProcess, "start", forbidden)
    adapter = ClaudeAdapter("p", "s", contextual_factory=bridge)
    run = await adapter.start_task(request())
    finished = await terminal(adapter, run.run_id)
    assert finished.status == "unknown" and finished.error_code == "factory_failed"
    assert finished.slot_held and not calls


@pytest.mark.asyncio
async def test_contextual_factory_is_explicit_and_default_stays_unsupported(tmp_path):
    adapter = ClaudeAdapter("p", "s")
    assert not (await adapter.capabilities()).supports_start
    with pytest.raises(AgentSyncError) as error:
        await adapter.start_task(request())
    assert error.value.code == "unsupported"
    with pytest.raises(AgentSyncError):
        ClaudeAdapter(
            "p", "s", factory=lambda task: None, contextual_factory=lambda task, ctx: None
        )
    with pytest.raises(AgentSyncError):
        ClaudeAdapter("p", "s", contextual_factory=False)
    profile = fixture_profile(tmp_path)
    with pytest.raises(AgentSyncError):
        ClaudeProcessFactory(profile, environment=None)
    with pytest.raises(AgentSyncError):
        ClaudeProcessFactory(object(), environment={})
    with pytest.raises(AgentSyncError):
        await ClaudeProcessFactory(profile, environment={})(request(), object())

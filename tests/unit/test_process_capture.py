"""Known local Python helpers only; no real client, sandbox or tree-cleanup evidence."""

import asyncio
import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError


def selected_fixture_env(**markers):
    environment = dict(markers)
    if sys.platform == "win32" and "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    return environment


def helper(source):
    return (sys.executable, "-I", "-u", "-c", source)


@pytest.mark.asyncio
async def test_owned_parent_exit_and_private_bytes_are_observed(tmp_path):
    process = await CapturedProcess.start(
        helper(
            "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); sys.stderr.write('note')"
        ),
        cwd=tmp_path,
        stdin_text="literal input",
        timeout_seconds=3,
    )
    snapshot = await process.wait()
    result = await process.get_result()
    assert snapshot.state == "exited"
    assert snapshot.exit_code == 0
    assert snapshot.parent_ended is True
    assert result.snapshot == snapshot
    assert result.stdout == b"literal input"
    assert result.stderr == b"note"
    assert snapshot.termination_scope == "parent_only"
    assert snapshot.tree_cleanup == "unverified"
    assert snapshot.sandbox is False
    assert snapshot.real_client_verified is False
    assert "literal input" not in repr(snapshot)
    assert str(tmp_path) not in repr(snapshot)


@pytest.mark.asyncio
async def test_nonzero_exit_is_observed_not_converted_to_task_failure(tmp_path):
    process = await CapturedProcess.start(
        helper("raise SystemExit(7)"), cwd=tmp_path, stdin_text="", timeout_seconds=3
    )
    snapshot = await process.wait()
    assert (snapshot.state, snapshot.exit_code) == ("exited", 7)


@pytest.mark.asyncio
async def test_spawn_failure_is_a_static_retained_result(tmp_path):
    process = await CapturedProcess.start(
        (str(tmp_path / "private-missing-program"),),
        cwd=tmp_path,
        stdin_text="private-input",
        timeout_seconds=1,
    )
    snapshot = await process.wait()
    assert snapshot.state == "failed_to_start"
    assert snapshot.error_code == "spawn_failed"
    assert snapshot.exit_code is None and snapshot.parent_ended is False
    assert "private" not in repr(snapshot)
    assert (await process.get_result()).stdout == b""
    assert await process.cancel() == snapshot


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.asyncio
async def test_each_output_stream_is_bounded_and_limit_stops_parent(tmp_path, stream):
    process = await CapturedProcess.start(
        helper(f"import sys; sys.{stream}.write('x'*20000); sys.{stream}.flush()"),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=3,
        output_limit=128,
    )
    snapshot = await process.wait()
    result = await process.get_result()
    assert snapshot.state == "output_limit"
    assert snapshot.parent_ended is True
    assert getattr(snapshot, f"{stream}_truncated") is True
    assert len(getattr(result, stream)) == 128
    assert len(result.stdout) <= 128 and len(result.stderr) <= 128


@pytest.mark.asyncio
async def test_deadline_observation_runs_without_polling_and_stdin_reader(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; time.sleep(0.4)"),
        cwd=tmp_path,
        stdin_text="x" * 16384,
        timeout_seconds=0.1,
    )
    await asyncio.sleep(0.6)
    snapshot = await process.snapshot()
    assert snapshot.state == "timed_out"
    assert snapshot.parent_ended is True
    assert snapshot.finished_at >= snapshot.deadline_at


@pytest.mark.asyncio
async def test_cancel_waits_for_only_owned_parent_and_is_terminal(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; time.sleep(0.3)"), cwd=tmp_path, stdin_text="", timeout_seconds=3
    )
    snapshot = await process.cancel()
    assert snapshot.state == "cancelled" and snapshot.parent_ended is True
    assert await process.cancel() == snapshot
    assert await process.wait() == snapshot


@pytest.mark.asyncio
async def test_running_result_is_not_ready_and_observed_snapshots_are_immutable(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; time.sleep(0.2)"), cwd=tmp_path, stdin_text="", timeout_seconds=3
    )
    snapshot = await process.snapshot()
    assert snapshot.state == "running" and snapshot.finished_at is None
    with pytest.raises(FrozenInstanceError):
        snapshot.state = "exited"
    with pytest.raises(AgentSyncError) as error:
        await process.get_result()
    assert error.value.code == "result_not_ready"
    await process.wait()


@pytest.mark.asyncio
async def test_cancelling_waiter_does_not_cancel_background_observation(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; time.sleep(0.15); print('done')"),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=3,
    )
    waiter = asyncio.create_task(process.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    snapshot = await process.wait()
    assert snapshot.state == "exited"
    assert (await process.get_result()).stdout.strip() == b"done"


@pytest.mark.asyncio
async def test_concurrent_cancel_and_exit_publish_one_stable_terminal(tmp_path):
    process = await CapturedProcess.start(
        helper("print('done')"), cwd=tmp_path, stdin_text="", timeout_seconds=3
    )
    first, second = await asyncio.gather(process.wait(), process.cancel())
    assert first == second == await process.snapshot()
    assert first.state in {"exited", "cancelled"}
    assert first.parent_ended is True


@pytest.mark.parametrize(
    "change",
    [
        {"timeout_seconds": True},
        {"timeout_seconds": float("inf")},
        {"output_limit": True},
        {"output_limit": 0},
        {"stdin_text": "x" * 16385},
        {"argv": [sys.executable, "-c", "print('known')"]},
        {"cwd": "string-instead-of-Path"},
        {"timeout_seconds": 301},
    ],
)
@pytest.mark.asyncio
async def test_invalid_inputs_are_rejected_before_a_process_is_returned(tmp_path, change):
    arguments = dict(argv=helper("print('known')"), cwd=tmp_path, stdin_text="", timeout_seconds=3)
    arguments.update(change)
    try:
        process = await CapturedProcess.start(**arguments)
    except AgentSyncError as error:
        assert error.code == "validation_error"
        assert error.message == "Invalid process capture input."
    else:
        await process.wait()
        pytest.fail("Invalid inputs must be rejected rather than launch a helper")


@pytest.mark.asyncio
async def test_early_cancel_terminal_and_results_remain_stable_after_late_callbacks(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; print('early'); time.sleep(0.2); print('late')"),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=3,
    )
    cancelled = await process.cancel()
    original = await process.get_result()
    await asyncio.sleep(0.3)
    assert await process.snapshot() == cancelled == original.snapshot
    assert await process.cancel() == cancelled
    assert await process.get_result() == original
    with pytest.raises(FrozenInstanceError):
        original.stdout = b"changed"


@pytest.mark.asyncio
async def test_cancelling_cancel_waiter_does_not_cancel_parent_cleanup(tmp_path):
    process = await CapturedProcess.start(
        helper("import time; time.sleep(0.3)"), cwd=tmp_path, stdin_text="", timeout_seconds=3
    )
    cancellation = asyncio.create_task(process.cancel())
    await asyncio.sleep(0)
    cancellation.cancel()
    try:
        await cancellation
    except asyncio.CancelledError:
        pass  # Parent may have exited before this waiter's cancellation.
    snapshot = await process.wait()
    assert snapshot.state == "cancelled" and snapshot.parent_ended is True


@pytest.mark.asyncio
async def test_independent_handles_do_not_mix_private_streams_or_capture_ids(tmp_path):
    left, right = await asyncio.gather(
        *[
            CapturedProcess.start(
                helper("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"),
                cwd=tmp_path,
                stdin_text=text,
                timeout_seconds=3,
            )
            for text in ("first; never a shell command", "第二")
        ]
    )
    first, second = await asyncio.gather(left.wait(), right.wait())
    assert first.capture_id != second.capture_id
    assert (await left.get_result()).stdout == b"first; never a shell command"
    assert (await right.get_result()).stdout == "第二".encode()


@pytest.mark.asyncio
async def test_exact_per_stream_caps_are_valid_not_a_combined_cap(tmp_path):
    process = await CapturedProcess.start(
        helper("import sys; sys.stdout.write('a'*128); sys.stderr.write('b'*128)"),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=3,
        output_limit=128,
    )
    snapshot = await process.wait()
    result = await process.get_result()
    assert snapshot.state == "exited"
    assert result.stdout == b"a" * 128 and result.stderr == b"b" * 128
    assert not snapshot.stdout_truncated and not snapshot.stderr_truncated


@pytest.mark.asyncio
async def test_other_strict_numeric_text_and_argv_bounds_have_static_errors(tmp_path):
    for change in [
        {"argv": ()},
        {"argv": (sys.executable, "bad\x00argument")},
        {"argv": (sys.executable,) * 65},
        {"argv": ("x" * 4097,)},
        {"argv": ("x" * 4096,) * 9},
        {"stdin_text": "\ud800"},
        {"stdin_text": False},
        {"stdin_text": "\x00"},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": 0.01},
        {"timeout_seconds": 2**10000},
        {"output_limit": 1048577},
        {"output_limit": 1.0},
    ]:
        arguments = dict(
            argv=helper("print('known')"), cwd=tmp_path, stdin_text="", timeout_seconds=3
        )
        arguments.update(change)
        with pytest.raises(AgentSyncError) as error:
            await CapturedProcess.start(**arguments)
        assert error.value.message == "Invalid process capture input."


@pytest.mark.asyncio
async def test_parent_exit_with_known_self_ending_child_has_bounded_incomplete_capture(tmp_path):
    marker = tmp_path / "child-finished.txt"
    child_source = (
        "import time; from pathlib import Path; time.sleep(0.8); "
        f"Path({str(marker)!r}).write_text('child finished naturally', encoding='utf-8')"
    )
    parent_source = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-I','-c',{child_source!r}], "
        "stdout=sys.stdout,stderr=sys.stderr); "
        "print('known parent output',flush=True)"
    )
    process = await CapturedProcess.start(
        helper(parent_source), cwd=tmp_path, stdin_text="", timeout_seconds=3, output_limit=128
    )
    snapshot = await process.wait()
    result = await process.get_result()
    assert snapshot.state == "capture_incomplete"
    assert snapshot.error_code == "capture_incomplete"
    assert snapshot.parent_ended is True and snapshot.exit_code == 0
    assert snapshot.tree_cleanup == "unverified"
    assert snapshot.termination_scope == "parent_only"
    assert b"known parent output" in result.stdout
    assert len(result.stdout) <= 128 and len(result.stderr) <= 128
    # This child belongs to the fixture and ends by itself. A marker proves its
    # planned work continued after parent exit; capture does not claim tree kill.
    deadline = asyncio.get_running_loop().time() + 3
    while not marker.is_file() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.03)
    assert marker.read_text(encoding="utf-8") == "child finished naturally"
    await asyncio.sleep(0.15)
    assert await process.snapshot() == snapshot
    assert await process.get_result() == result


@pytest.mark.asyncio
async def test_explicit_environment_selects_only_fixture_values_without_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AGENTSYNC_PARENT_FIXTURE", "parent-only-marker")
    monkeypatch.delenv("AGENTSYNC_CHILD_FIXTURE", raising=False)
    environment = selected_fixture_env(AGENTSYNC_CHILD_FIXTURE="selected-child-marker")
    original = dict(environment)
    process = await CapturedProcess.start(
        helper(
            "import os,json; print(json.dumps([os.getenv('AGENTSYNC_PARENT_FIXTURE'),os.getenv('AGENTSYNC_CHILD_FIXTURE')]))"
        ),
        cwd=tmp_path,
        stdin_text="",
        timeout_seconds=3,
        env=environment,
    )
    snapshot = await process.wait()
    assert snapshot.state == "exited" and snapshot.exit_code == 0
    assert json.loads((await process.get_result()).stdout) == [None, "selected-child-marker"]
    assert environment == original
    assert os.environ["AGENTSYNC_PARENT_FIXTURE"] == "parent-only-marker"
    assert "AGENTSYNC_CHILD_FIXTURE" not in os.environ
    assert "selected-child-marker" not in repr(snapshot)


@pytest.mark.asyncio
async def test_none_and_omitted_environment_preserve_parent_inheritance(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTSYNC_PARENT_FIXTURE", "inherited-dummy-marker")
    for options in ({}, {"env": None}):
        process = await CapturedProcess.start(
            helper("import os; print(os.getenv('AGENTSYNC_PARENT_FIXTURE'))"),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
            **options,
        )
        assert (await process.wait()).state == "exited"
        assert (await process.get_result()).stdout.strip() == b"inherited-dummy-marker"
    assert os.environ["AGENTSYNC_PARENT_FIXTURE"] == "inherited-dummy-marker"


@pytest.mark.asyncio
async def test_explicit_environment_is_copied_before_delayed_public_factory(tmp_path, monkeypatch):
    loop = asyncio.get_running_loop()
    original_factory = loop.subprocess_exec
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_factory(protocol_factory, *args, **kwargs):
        entered.set()
        await release.wait()
        return await original_factory(protocol_factory, *args, **kwargs)

    monkeypatch.setattr(loop, "subprocess_exec", delayed_factory)
    environment = selected_fixture_env(AGENTSYNC_CHILD_FIXTURE="original-dummy-marker")
    caller = asyncio.create_task(
        CapturedProcess.start(
            helper(
                "import os; print(os.getenv('AGENTSYNC_CHILD_FIXTURE')); print(os.getenv('AGENTSYNC_ADDED_FIXTURE'))"
            ),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=3,
            env=environment,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        environment["AGENTSYNC_CHILD_FIXTURE"] = "changed-dummy-marker"
        environment["AGENTSYNC_ADDED_FIXTURE"] = "added-dummy-marker"
    finally:
        release.set()
    process = await caller
    assert (await process.wait()).exit_code == 0
    assert (await process.get_result()).stdout.splitlines() == [b"original-dummy-marker", b"None"]
    assert environment["AGENTSYNC_CHILD_FIXTURE"] == "changed-dummy-marker"


@pytest.mark.parametrize(
    "environment",
    [True, [], {False: "dummy"}, {"DUMMY": True}],
    ids=["bool", "list", "bool-key", "bool-value"],
)
@pytest.mark.asyncio
async def test_invalid_environment_types_never_reach_subprocess(tmp_path, monkeypatch, environment):
    calls = []

    async def forbidden_factory(*args, **kwargs):
        calls.append(True)
        pytest.fail("Invalid environment reached subprocess factory")

    monkeypatch.setattr(asyncio.get_running_loop(), "subprocess_exec", forbidden_factory)
    with pytest.raises(AgentSyncError) as error:
        await CapturedProcess.start(
            helper("print('known')"),
            cwd=tmp_path,
            stdin_text="",
            timeout_seconds=1,
            env=environment,
        )
    assert error.value.message == "Invalid process capture input."
    assert calls == []


@pytest.mark.asyncio
async def test_invalid_environment_text_and_sizes_never_reach_subprocess(tmp_path, monkeypatch):
    calls = []

    async def forbidden_factory(*args, **kwargs):
        calls.append(True)
        pytest.fail("Invalid environment reached subprocess factory")

    monkeypatch.setattr(asyncio.get_running_loop(), "subprocess_exec", forbidden_factory)
    invalid = [
        {"": "dummy"},
        {"A=B": "dummy"},
        {"DUMMY": "x\x00y"},
        {"D\x00UMMY": "x"},
        {"DUMMY": "\ud800"},
        {"\ud800": "dummy"},
        {"X" * 257: "dummy"},
        {"DUMMY": "x" * 16385},
        {f"K{i}": "v" for i in range(257)},
        {f"K{i}": "x" * 16384 for i in range(4)},
    ]
    for environment in invalid:
        with pytest.raises(AgentSyncError) as error:
            await CapturedProcess.start(
                helper("print('known')"),
                cwd=tmp_path,
                stdin_text="",
                timeout_seconds=1,
                env=environment,
            )
        assert error.value.message == "Invalid process capture input."
    assert calls == []

"""Terminal host boundaries with owned Python protocol and synthetic verification."""

import getpass
import json
import os
import runpy
import select
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_candidate_execution import synthetic_backend
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_task_proposals import world as world
from verified_flow_process_fixture import emit_proposal

from agentsync.adapters import codex_invocation
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError
from agentsync.verification import candidate_executor


@pytest.mark.skipif(sys.platform != "linux", reason="Real Linux terminal input")
@pytest.mark.parametrize("mode", ["cancel", "line", "eof", "overlong"])
def test_real_hidden_terminal_input(terminal_host, mode):
    import pty

    example = os.environ.get("AGENTSYNC_TERMINAL_INPUT_EXAMPLE", terminal_host["__file__"])
    program = r"""
import asyncio,json,os,runpy,sys,termios,time
host=runpy.run_path(sys.argv[1])
mode=sys.argv[2]
async def check():
    original=termios.tcgetattr(0)
    descriptors=set(os.listdir('/proc/self/fd'))
    started=time.monotonic()
    matched=False
    async def read():
        if 'prompt_async' in host:
            return await host['prompt_async']('Approve fixture: ')
        return host['prompt']('Approve fixture: ')
    try:
        async with asyncio.timeout(0.1 if mode=='cancel' else 2):
            value=await read()
        status='accepted'
        matched=value=='fixture-secret'
    except TimeoutError:
        status='cancelled'
    except EOFError:
        status='eof'
    except ValueError:
        status='rejected'
    print(json.dumps({'status':status,'matched':matched,'elapsed':time.monotonic()-started,
                      'restored':termios.tcgetattr(0)==original,
                      'descriptors_restored':set(os.listdir('/proc/self/fd'))==descriptors}),flush=True)
asyncio.run(check())
"""
    pid, descriptor = pty.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, "-I", "-B", "-c", program, example, mode])
    output = bytearray()
    prompt_at = None
    sent = exited = False
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([descriptor], [], [], 0.02)
            if readable:
                try:
                    chunk = os.read(descriptor, 4096)
                except OSError:
                    chunk = b""
                output.extend(chunk)
            if b"Approve fixture: " in output and prompt_at is None:
                prompt_at = time.monotonic()
            if prompt_at is not None and not sent:
                if mode != "cancel" or time.monotonic() - prompt_at >= 0.35:
                    payload = {
                        "cancel": b"late\n",
                        "line": b"fixture-secret\n",
                        "eof": b"\x04",
                        "overlong": b"x" * 300 + b"\n",
                    }[mode]
                    os.write(descriptor, payload)
                    sent = True
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                exited = True
                assert os.waitstatus_to_exitcode(status) == 0, output.decode(errors="replace")
                while select.select([descriptor], [], [], 0)[0]:
                    try:
                        remaining = os.read(descriptor, 4096)
                    except OSError:
                        break
                    if not remaining:
                        break
                    output.extend(remaining)
                break
        assert exited, "Terminal subprocess did not end."
    finally:
        if not exited:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        os.close(descriptor)
    assert b"fixture-secret" not in output
    text = output.decode()
    result = json.JSONDecoder().raw_decode(text[text.index('{"status":') :])[0]
    assert (
        result["status"]
        == {"cancel": "cancelled", "line": "accepted", "eof": "eof", "overlong": "rejected"}[mode]
    )
    assert result["restored"] and result["descriptors_restored"]
    if mode == "cancel":
        assert not sent and result["elapsed"] < 0.35
    elif mode == "line":
        assert result["matched"]


@pytest.fixture
def terminal_host():
    path = Path(__file__).resolve().parents[2] / "examples/verified_codex_task.py"
    return runpy.run_path(str(path))


@pytest.mark.parametrize("field,limit", [("task", 1000), ("cases", 32768)])
def test_inputs_bound_oversized_file_reads(terminal_host, tmp_path, monkeypatch, field, limit):
    task, cases = tmp_path / "task.txt", tmp_path / "cases.json"
    task.write_bytes(b"Sum JSON arrays.")
    cases.write_bytes(b'[{"input":[2,3],"expected":5}]')
    oversized = {"task": task, "cases": cases}[field]
    oversized.write_bytes(b"x" * (1024 * 1024))
    args = SimpleNamespace(task=task, cases=cases, image_id="sha256:" + "a" * 64)
    original_open = Path.open
    requests, received = [], []

    @contextmanager
    def tracked_open(path, *args, **kwargs):
        with original_open(path, *args, **kwargs) as stream:
            if path != oversized:
                yield stream
                return

            def read(size=-1):
                requests.append(size)
                result = stream.read(size)
                received.append(len(result))
                return result

            yield SimpleNamespace(read=read)

    monkeypatch.setattr(Path, "open", tracked_open)
    with pytest.raises(ValueError, match="^input_limit$"):
        terminal_host["inputs"](args)
    assert requests == [limit + 1]
    assert received == [limit + 1]


@pytest.mark.parametrize("field,limit", [("task", 1000), ("cases", 32768)])
@pytest.mark.parametrize("extra", [0, 1])
def test_inputs_preserve_byte_limits(terminal_host, tmp_path, field, limit, extra):
    task, cases = tmp_path / "task.txt", tmp_path / "cases.json"
    task.write_bytes(b"Sum JSON arrays.")
    content = b'[{"input":[2,3],"expected":5}]'
    cases.write_bytes(content)
    if field == "task":
        task.write_bytes(b"x" * (limit + extra))
    else:
        cases.write_bytes(content + b" " * (limit + extra - len(content)))
    args = SimpleNamespace(task=task, cases=cases, image_id="sha256:" + "a" * 64)
    if extra:
        with pytest.raises(ValueError, match="^input_limit$"):
            terminal_host["inputs"](args)
    else:
        goal, examples, profile = terminal_host["inputs"](args)
        assert goal == ("x" * 1000 if field == "task" else "Sum JSON arrays.")
        assert examples == [{"input": [2, 3], "expected": 5}]
        assert profile == terminal_host["DockerProfile"](
            args.image_id, (terminal_host["JsonCase"]([2, 3], 5),)
        )


def test_prompt_refuses_insecure_terminal_without_fallback(terminal_host, monkeypatch):
    monkeypatch.setattr(terminal_host["sys"].stdin, "isatty", lambda: False)
    monkeypatch.setattr(getpass, "getpass", lambda _: pytest.fail("No fallback credential read"))
    with pytest.raises(ValueError, match="secure_terminal_required"):
        terminal_host["prompt"]("Private input")


@pytest.mark.parametrize(
    "deny",
    [None, "launch", "staging", "execution", "completion", "receiver-launch", "receiver-failed"],
)
async def test_terminal_uses_real_core_and_exact_decisions(world, terminal_host, monkeypatch, deny):
    core, owner, _, old_auth, _, _, source = world
    cancel_fixture_load(world)
    binary = source.parent / "fixture-codex"
    binary.write_bytes(b"Known local Python boundary; never execute this file.")
    home = source.parent / "private-home"
    home.mkdir()
    args = SimpleNamespace(
        root=source.parent,
        project_id=owner["project_id"],
        codex=binary,
        codex_sha256=terminal_host["hashlib"].sha256(binary.read_bytes()).hexdigest(),
        codex_version="0.167.0-alpha.3.2",
        codex_home=home,
    )
    profile = terminal_host["DockerProfile"](
        "sha256:" + "b" * 64,
        (terminal_host["JsonCase"]([2, 3], 5), terminal_host["JsonCase"]([-4, 1], -3)),
    )
    records, prompts, launched, verifications, failed_captures = [], [], [], [], []
    original = CapturedProcess.start
    content = "import json,sys\nfor line in sys.stdin:\n print(json.dumps(sum(json.loads(line))))\n"

    async def process(_cls, argv, **options):
        contract, _ = json.JSONDecoder().raw_decode(
            options["stdin_text"].split("Host contract: ", 1)[1]
        )
        (path,) = contract["allowed_paths"]
        launched.append(path)
        if path == "review.md" and deny == "receiver-failed":
            captured = await original(
                (sys.executable, "-I", "-B", "-c", "raise SystemExit(3)"), **options
            )
            failed_captures.append(captured)
            return captured
        return await emit_proposal(
            original,
            path,
            content if path == "solution.py" else "Review text.",
            cwd=options["cwd"],
            timeout_seconds=options["timeout_seconds"],
            output_limit=options["output_limit"],
            env={},
        )

    def answer(label):
        prompts.append(label)
        record = records[-1]
        if label.startswith("Confirm subscription"):
            return "CONFIRM"
        if "launch" in label:
            rejected = deny == "launch" or (deny == "receiver-launch" and len(launched) == 1)
            return "wrong" if rejected else record["plan_sha256"]
        value = record["value"]
        if record["stage"] == "staging":
            assert record["proposal_files"] == [{"path": "solution.py", "content": content}]
            return "wrong" if deny == "staging" else value["plan_sha256"]
        if record["stage"] == deny:
            return "wrong"
        return value["metadata_sha256" if record["stage"] == "execution" else "decision_sha256"]

    def verify(source, **options):
        verifications.append(source)
        return synthetic_backend(source, **options)

    async def async_answer(label):
        return answer(label)

    # Only approved process/verifier and terminal-input boundaries are synthetic.
    monkeypatch.setattr(codex_invocation, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(CapturedProcess, "start", classmethod(process))
    monkeypatch.setattr(candidate_executor, "verify_python_json_lines", verify)
    monkeypatch.setitem(terminal_host["run"].__globals__, "emit", records.append)
    monkeypatch.setitem(terminal_host["run"].__globals__, "prompt_async", async_answer)
    if deny == "launch":
        with pytest.raises(AgentSyncError):
            await terminal_host["run"](
                args,
                owner["admin_token"],
                "Sum JSON arrays.",
                [{"input": [2, 3], "expected": 5}],
                profile,
            )
        assert launched == []
        assert verifications == []
        assert (args.root / "terminal-run/stopped.json").is_file()
    else:
        status = await terminal_host["run"](
            args,
            owner["admin_token"],
            "Sum JSON arrays.",
            [{"input": [2, 3], "expected": 5}],
            profile,
        )
        assert status == int(deny is not None)
        if deny == "receiver-failed":
            assert launched == ["solution.py", "review.md"] and len(verifications) == 1
            (capture,) = failed_captures
            exited = await capture.get_result()
            assert exited.snapshot.parent_ended is True and exited.snapshot.exit_code == 3
            assert exited.stdout == exited.stderr == b""
            handed = records[-1]["flow"]["handoff"]
            assert handed["state"] == handed["wave"]["state"] == "resolved"
            assert list(handed["wave"]["tasks"]) == [
                {"task_id": handed["task_id"], "state": "confirmed_failed", "failure_code": None}
            ]
            tasks = {row["id"]: row for row in records[-1]["tasks"]}
            assert tasks[handed["pin"]["producer_task_id"]]["status"] == "completed"
            assert tasks[handed["pin"]["producer_task_id"]]["task_verification"] == "verified"
            assert tasks[handed["task_id"]]["status"] != "review"
            assert tasks[handed["task_id"]]["task_verification"] == "unverified"
        elif deny == "receiver-launch":
            assert launched == ["solution.py"] and len(verifications) == 1
            assert records[-1]["flow"]["state"] == "handoff"
            handed = records[-1]["flow"]["handoff"]
            tasks = {row["id"]: row for row in records[-1]["tasks"]}
            assert tasks[handed["pin"]["producer_task_id"]]["status"] == "completed"
            assert tasks[handed["pin"]["producer_task_id"]]["task_verification"] == "verified"
            assert tasks[handed["task_id"]]["status"] != "review"
            assert tasks[handed["task_id"]]["task_verification"] == "unverified"
            assert not (args.root / "terminal-run/launch-2-approved.json").exists()
        elif deny is not None:
            assert launched == ["solution.py"]
            assert records[-1]["flow"]["state"] == deny + "_denied"
            assert len(verifications) == int(deny == "completion")
            assert not (args.root / "terminal-run" / (deny + "-approved.json")).exists()
            stages = [record["stage"] for record in records if "stage" in record]
            assert stages == ["staging", "execution", "completion"][: len(stages)]
            assert stages[-1] == deny
        else:
            assert launched == ["solution.py", "review.md"]
            assert len(verifications) == 1
            tasks = records[-1]["tasks"]
            assert any(
                t["status"] == "completed" and t["task_verification"] == "verified" for t in tasks
            )
            assert any(
                t["status"] == "review" and t["task_verification"] == "unverified" for t in tasks
            )
    before = core.execute("list_tasks", old_auth)
    with pytest.raises(FileExistsError):
        await terminal_host["run"](args, owner["admin_token"], "Never retry", [], profile)
    assert core.execute("list_tasks", old_auth) == before
    assert owner["admin_token"] not in json.dumps(records)

import getpass
import hashlib
import io
import json
import runpy
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_codex_proposal_relay_queue import proposal_wave as proposal_wave
from test_task_proposals import world as world

import agentsync.core.service as service
from agentsync.adapters.approved_launch import digest
from agentsync.cli import main
from agentsync.controlled_relay import ControlledRelay
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue


@pytest.mark.parametrize("receipt", ["saved", "missing", "malformed", "unknown-protocol"])
async def test_owner_inspects_checkpoint_after_producer_session_expiry(
    pilot, world, proposal_wave, monkeypatch, receipt
):
    core, owner, _, _, task, _, source, receipts, _ = pilot
    relay, item, _, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    spec = replace(
        item.task, instruction="Checkpoint fixture succeeded", checkpoint_completed_proposal=True
    )
    await relay.run_codex_proposal_once(item.first, spec, admin_token=owner["admin_token"])
    expected = relay.observe_codex_checkpoint(item.first, task["id"])
    assert expected["state"] == "saved"
    other = core.execute("create_project", {"name": "Other owner", "root_path": str(source)})
    key = relay._key(item.first, task["id"])
    progress = receipts / relay._receipt_name(key, "proposal-progress")
    if receipt == "missing":
        progress.unlink()
    elif receipt == "malformed":
        progress.write_text("{", encoding="utf8")
    elif receipt == "unknown-protocol":
        value = json.loads(progress.read_bytes())
        value["checkpoint_protocol"] = "unknown-v2"
        progress.write_text(json.dumps(value), encoding="utf8")

    def files():
        return {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [core.db_path, *sorted(receipts.iterdir())]
            if path.is_file()
        }

    before = files()
    # Advance only the normal Core request clock. No session/credential bypass or DB repair.
    now = time.time() + 3601
    monkeypatch.setattr(service, "time", SimpleNamespace(time=lambda: now))
    with pytest.raises(AgentSyncError) as expired:
        relay.observe_codex_checkpoint(item.first, task["id"])
    assert expired.value.code == "session_expired"
    command = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "agentsync",
        "--data-dir",
        str(core.data_dir),
        "relay-status",
        "--scratch-root",
        str(source.parent),
        "--receipts",
        str(receipts),
        "--task-id",
        task["id"],
    ]
    # CLI owner inspection carries no agent session and therefore cannot revive it.
    child = subprocess.run(
        command,
        input=json.dumps(owner).encode(),
        capture_output=True,
        check=False,
        cwd=source.parent,
    )
    response = json.loads(child.stdout)
    assert owner["admin_token"].encode() not in child.stdout + child.stderr
    if receipt in ("saved", "missing"):
        assert child.returncode == 0 and response["ok"] is True
        checkpoint = response["data"]["checkpoint"]
        assert (
            relay.owner_observe_codex_checkpoint(
                owner["project_id"], task["id"], admin_token=owner["admin_token"]
            )
            == checkpoint
        )
        assert (
            checkpoint["scope"] == "receipt_observation"
            and checkpoint["verification"] == "unverified"
        )
        if receipt == "saved":
            assert checkpoint == expected
        else:
            assert checkpoint["state"] == "unknown" and checkpoint["checkpoint_observed"] is None
    else:
        assert child.returncode == 1 and response["ok"] is False
        with pytest.raises(AgentSyncError):
            relay.owner_observe_codex_checkpoint(
                owner["project_id"], task["id"], admin_token=owner["admin_token"]
            )
    with pytest.raises(AgentSyncError) as foreign:
        relay.owner_observe_codex_checkpoint(
            owner["project_id"], task["id"], admin_token=other["admin_token"]
        )
    assert foreign.value.code == "unauthorized"
    own_project = relay.owner_observe_codex_checkpoint(
        other["project_id"], task["id"], admin_token=other["admin_token"]
    )
    assert own_project["state"] == "unknown" and "context_id" not in own_project
    assert files() == before
    assert len(approvals) == len(captures) == 1  # Only a known local Python process fixture.


def test_owner_recovers_pending_wave_identity_without_an_agent_session(
    tmp_path, monkeypatch, capsys
):
    scratch = tmp_path.resolve()
    data = scratch / "core"
    receipts = scratch / "receipts"
    receipts.mkdir()
    core = Core(data)
    owner = core.execute("create_project", {"name": "Pilot", "root_path": str(scratch)})
    other = core.execute("create_project", {"name": "Other", "root_path": str(scratch)})
    queue = RelayQueue(ControlledRelay(core, scratch, receipts))
    project_id = owner["project_id"]
    project_key = digest(project_id)
    wave_id = digest("pending")
    queue._relay._check_receipt_anchor(project_id, bind=True)
    queue._check_journal_anchor(project_key, bind=True)
    queue._journal.admit(project_key, wave_id, ("isolated-task",))

    reopened = RelayQueue(ControlledRelay(Core(data), scratch, receipts))
    with pytest.raises(AgentSyncError) as rejected:
        reopened.owner_history(project_id, admin_token=other["admin_token"])
    assert rejected.value.code == "unauthorized"
    assert (
        reopened.owner_observe_pending(other["project_id"], admin_token=other["admin_token"])
        is None
    )

    credentials = {"project_id": project_id, "admin_token": owner["admin_token"]}
    payload = json.dumps(credentials).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))
    assert (
        main(
            [
                "--data-dir",
                str(data),
                "relay-status",
                "--scratch-root",
                str(scratch),
                "--receipts",
                str(receipts),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert owner["admin_token"] not in output
    pending = json.loads(output)["data"]
    assert pending["wave_id"] == wave_id
    assert pending["receipt_state"] == "admitted"
    assert pending["outcome"]["verification"] == "unverified"
    assert reopened.owner_history(**credentials).waves[0].wave_id == wave_id

    task_id = "isolated-task"
    queue._relay._record(
        digest([project_id, task_id]),
        "first-dispatched",
        client="codex",
        launch_request_sha256=digest("fixture request"),
    )
    other_attempts = reopened._relay.owner_inspect_attempts(
        other["project_id"],
        task_id,
        admin_token=other["admin_token"],
    )
    assert all(attempt.state == "not_dispatched" for attempt in other_attempts)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))
    assert (
        main(
            [
                "--data-dir",
                str(data),
                "relay-status",
                "--scratch-root",
                str(scratch),
                "--receipts",
                str(receipts),
                "--task-id",
                task_id,
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert owner["admin_token"] not in output
    first, second = json.loads(output)["data"]["attempts"]
    assert first["state"] == "outcome_unknown"
    assert second["state"] == "not_dispatched"


@pytest.fixture
def recover_relay():
    path = Path(__file__).resolve().parents[2] / "examples" / "recover_relay.py"
    return runpy.run_path(str(path))["main"]


def example_args(scratch, project_id):
    return [
        "--data-dir",
        str(scratch / "core"),
        "--scratch-root",
        str(scratch),
        "--receipts",
        str(scratch / "receipts"),
        "--project-id",
        project_id,
    ]


def test_recover_example_passes_credentials_only_to_stdin_and_does_not_retry(
    recover_relay, tmp_path, monkeypatch, capsys
):
    supplied = ("fixture-owner-token", "fixture-session-id", "fixture-session-token")
    prompt = Mock(side_effect=supplied)
    child = Mock(side_effect=subprocess.TimeoutExpired([], 60, output=supplied[0]))
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(getpass, "getpass", prompt)
    monkeypatch.setattr(subprocess, "run", child)
    wave = "a" * 64

    assert recover_relay([*example_args(tmp_path, "fixture-project"), "reconcile", wave]) == 1

    child.assert_called_once()
    (argv,), kwargs = child.call_args
    assert argv[:5] == [sys.executable, "-I", "-B", "-m", "agentsync"]
    assert argv[7:9] == ["relay-reconcile", wave]
    assert not any(secret in arg for arg in argv for secret in supplied)
    assert "env" not in kwargs
    assert json.loads(kwargs["input"]) == {
        "project_id": "fixture-project",
        "admin_token": supplied[0],
        "session_id": supplied[1],
        "session_token": supplied[2],
    }
    assert prompt.call_count == len(supplied)
    output = capsys.readouterr()
    assert output.out == "" and "outcome unknown" in output.err and "Check status" in output.err
    assert not any(secret in output.err for secret in supplied)


@pytest.mark.parametrize("terminal", [False, True], ids=["redirected", "echo-warning"])
def test_recover_example_declines_insecure_input(recover_relay, tmp_path, monkeypatch, terminal):
    def warn(*_args):
        warnings.warn("Input might be echoed", getpass.GetPassWarning, stacklevel=2)
        pytest.fail("The prompt attempted an insecure fallback")

    prompt = Mock(side_effect=warn)
    child = Mock()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: terminal))
    monkeypatch.setattr(getpass, "getpass", prompt)
    monkeypatch.setattr(subprocess, "run", child)
    with pytest.raises(SystemExit) as failure:
        recover_relay([*example_args(tmp_path, "fixture-project"), "status"])
    assert failure.value.code == 2
    assert prompt.call_count == int(terminal)
    child.assert_not_called()


def test_recover_example_reads_real_owner_status(recover_relay, tmp_path, monkeypatch, capfd):
    scratch = tmp_path.resolve()
    receipts = scratch / "receipts"
    receipts.mkdir()
    core = Core(scratch / "core")
    owner = core.execute("create_project", {"name": "Recovery example", "root_path": str(scratch)})
    project_id = owner["project_id"]
    project_key = digest(project_id)
    wave = digest("example pending wave")
    queue = RelayQueue(ControlledRelay(core, scratch, receipts))
    queue._relay._check_receipt_anchor(project_id, bind=True)
    queue._check_journal_anchor(project_key, bind=True)
    queue._journal.admit(project_key, wave, ("example-task",))
    prompt = Mock(return_value=owner["admin_token"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(getpass, "getpass", prompt)

    assert recover_relay([*example_args(scratch, project_id), "status"]) == 0

    prompt.assert_called_once()
    output = capfd.readouterr()
    assert owner["admin_token"] not in output.out + output.err
    response = json.loads(output.out)
    assert response["ok"] is True and response["data"]["wave_id"] == wave
    assert response["data"]["receipt_state"] == "admitted"

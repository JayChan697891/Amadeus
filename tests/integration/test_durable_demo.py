"""The installed CLI demonstrates one durable Mock recovery without exposing credentials."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentsync import durable_demo
from agentsync.cli import main
from agentsync.sdk import AgentSyncClient


def test_durable_demo_reopens_retry_and_records_handoff(tmp_path, monkeypatch, capsys):
    directory = tmp_path / "demo"
    run = durable_demo.subprocess.run
    children = {}
    owner = {}

    def observe_child(command, **kwargs):
        payload = json.loads(kwargs["input"])
        owner.update({key: payload[key] for key in ("project_id", "admin_token")})
        token = owner["admin_token"]
        assert all(token not in argument for argument in command)
        process = run(command, **kwargs)
        assert token not in process.stdout + process.stderr
        children[command[-1]] = json.loads(process.stdout)["data"]
        return process

    monkeypatch.setattr(durable_demo.subprocess, "run", observe_child)
    assert main(["--data-dir", str(directory), "demo", "--durable"], prog="amadeus") == 0
    captured = capsys.readouterr()
    assert owner["admin_token"] not in captured.out + captured.err
    assert all(
        owner["admin_token"].encode() not in file.read_bytes()
        for file in directory.iterdir()
        if file.is_file()
    )
    assert list(children) == ["start", "status", "resume"]
    result = json.loads(captured.out)["data"]
    assert result["task_status"] == "completed"
    assert result["reopened_state"] == "waiting"
    assert result["resumed_in_fresh_process"] is True
    assert result["attempts"] == ["failed", "succeeded", "succeeded"]
    assert result["peer_review"] == {
        "distinct_from_handoff_participants": True,
        "evidence": "simulation_only/unverified",
    }
    assert result["simulation_only"] is True and result["verification"] == "unverified"
    assert children["status"] == children["start"]
    assert children["status"]["tasks"][0]["id"] == result["task_id"]

    client = AgentSyncClient(directory)
    persisted = client.owner_call("status_mock_workflow", **owner)["data"]
    assert persisted["state"] == "completed" and persisted["run_id"] == result["run_id"]
    assert len(persisted["tasks"]) == 1 and persisted["tasks"][0]["id"] == result["task_id"]
    accepted = client.owner_call(
        "list_handoffs", **owner, task_id=result["task_id"], status="accepted"
    )["data"]["handoffs"]
    assert len(accepted) == 1
    assert result["handoff"] == {"id": accepted[0]["id"], "status": "accepted"}


def test_durable_demo_refuses_existing_state(tmp_path, capsys):
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "agentsync.db"
    sentinel.write_bytes(b"pre-existing state")
    with pytest.raises(SystemExit) as error:
        main(["--data-dir", str(existing), "demo", "--durable"], prog="amadeus")
    assert error.value.code == 2
    assert "requires a new --data-dir" in capsys.readouterr().err
    assert list(existing.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"pre-existing state"


def test_durable_demo_reports_unicode_directory_with_legacy_stdout(tmp_path):
    directory = tmp_path.resolve() / "持久协作"
    source = Path(durable_demo.__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            "-s",
            "-B",
            "-m",
            "agentsync",
            "--data-dir",
            str(directory),
            "demo",
            "--durable",
        ],
        env=os.environ | {"PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(source)},
        capture_output=True,
        timeout=90,
        check=False,
    )

    assert (directory / "agentsync.db").is_file()
    assert process.returncode == 0, process.stderr.decode("ascii", errors="replace")
    response = json.loads(process.stdout.decode("ascii"))
    assert response["ok"] is True
    result = response["data"]
    assert Path(result["data_dir"]) == directory
    assert result["task_status"] == "completed"
    assert result["simulation_only"] is True and result["verification"] == "unverified"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["demo", "--durable"], "requires --data-dir"),
        (["--data-dir", "relative", "demo", "--durable"], "must be absolute"),
        (["demo", "--workflow", "--durable"], "not allowed with argument"),
    ],
)
def test_durable_demo_cli_requires_a_dedicated_mode_and_absolute_directory(
    arguments, message, capsys
):
    with pytest.raises(SystemExit) as error:
        main(arguments, prog="amadeus")
    assert error.value.code == 2
    assert message in capsys.readouterr().err

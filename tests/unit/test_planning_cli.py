"""Offline user entrypoint; all state is caller-supplied, with no Core construction."""

import io
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

import agentsync
from agentsync import cli
from agentsync.dispatch_planning import plan_dispatches


def payload():
    tasks = [
        dict(
            id=label,
            project_id="p",
            status="pending",
            priority=1,
            version=1,
            created_at=0,
            updated_at=0,
            owner_session_id=None,
            lease_expires_at=None,
            assigned_agent_id=None,
            assignment_expires_at=None,
            dependencies=dependencies,
        )
        for label, dependencies in (("root", []), ("child", ["root"]))
    ]
    return dict(
        state=dict(
            project={"id": "p", "created_at": 0},
            agents=[dict(id="a", project_id="p", created_at=0, capabilities=["build"])],
            sessions=[
                dict(
                    id="s",
                    project_id="p",
                    agent_id="a",
                    created_at=0,
                    heartbeat_at=10,
                    expires_at=100,
                    online=True,
                )
            ],
            tasks=tasks,
        ),
        project_id="p",
        worker_agent_ids=["a"],
        now=10,
        global_limit=2,
        per_agent_limit=1,
        limit=2,
        required_capabilities={"root": ["build"], "child": ["build"]},
    )


def stdin(monkeypatch, raw):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def test_plan_cli_matches_existing_dispatch_advice_without_state_io(monkeypatch, capsys):
    data = payload()
    expected = plan_dispatches(
        data["state"],
        project_id="p",
        worker_agent_ids=("a",),
        now=10,
        global_limit=2,
        per_agent_limit=1,
        limit=2,
        required_capabilities={"root": ("build",), "child": ("build",)},
    )
    stdin(monkeypatch, json.dumps(data).encode())
    monkeypatch.setattr(cli, "AgentSyncClient", lambda *_: pytest.fail("Constructed Core client"))
    monkeypatch.setattr(Path, "resolve", lambda *_args, **_kwargs: pytest.fail("Path I/O"))
    assert cli.main(["plan"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == json.loads(json.dumps(asdict(expected)))
    assert result["scope"] == "planning_only" and not result["execution_connected"]
    assert result["core_authorization"] == result["snapshot_freshness"] == "unverified"


def test_invalid_planning_input_is_bounded_strict_and_never_echoed(monkeypatch, capsys):
    encoded = json.dumps(payload()).encode()
    invalid = [
        b"\xff",
        b"{}",
        b"{" + b"x" * (1024 * 1024),
        encoded.replace(b'"now": 10', b'"now": 10,"now": 11'),
        encoded.replace(b'"now": 10', b'"now": NaN'),
        encoded.replace(b'"now": 10', b'"now": 1e999'),
    ]
    for changes in (
        {"now": True},
        {"project_id": "foreign"},
        {"worker_agent_ids": "a"},
        {"required_capabilities": {"root": "build"}},
        {"session_token": "private-secret"},
        {"global_limit": False},
    ):
        invalid.append(json.dumps({**payload(), **changes}).encode())
    monkeypatch.setattr(cli, "AgentSyncClient", lambda *_: pytest.fail("Constructed Core client"))
    for raw in invalid:
        stdin(monkeypatch, raw)
        assert cli.main(["plan"]) == 2
        assert json.loads(capsys.readouterr().out) == {
            "error": {"code": "invalid_input", "message": "Invalid planning input."}
        }


def test_plan_is_standalone_and_does_not_intercept_owner_operation(monkeypatch, capsys, tmp_path):
    for arguments in (
        ["plan", "--data-dir", "private-path"],
        ["--data-dir", "private-path", "plan"],
    ):
        assert cli.main(arguments) == 2
        assert "private" not in capsys.readouterr().out

    class OwnerClient:
        def __init__(self, _directory):
            pass

        def owner_call(self, operation, **_payload):
            assert operation == "plan"
            return {"ok": False, "error": {"code": "unknown_operation"}}

    cli.AgentSyncClient(tmp_path)
    monkeypatch.setenv("AGENTSYNC_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "AgentSyncClient", OwnerClient)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert cli.main(["owner", "plan"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_operation"


def test_actual_plan_process_leaves_empty_home_and_default_state_unchanged(tmp_path):
    home, state = tmp_path / "home", tmp_path / "unused-state"
    home.mkdir()
    environment = {
        "PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "AGENTSYNC_DATA_DIR": str(state),
        "TMP": str(tmp_path),
        "TEMP": str(tmp_path),
    }
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    result = subprocess.run(
        [sys.executable, "-B", "-m", "agentsync", "plan"],
        input=json.dumps(payload()).encode(),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["dispatches"] == [
        {"task_id": "root", "expected_version": 1, "agent_id": "a", "session_id": "s"}
    ]
    assert observed["scope"] == "planning_only" and not observed["execution_connected"]
    assert list(home.iterdir()) == [] and not state.exists()
    assert set(tmp_path.iterdir()) == {home}


def test_unicode_project_plan_survives_ascii_stdout_without_state_or_private_input_echo(tmp_path):
    data = payload()
    project_id = "项目😀"
    data["project_id"] = data["state"]["project"]["id"] = project_id
    for group in ("agents", "sessions", "tasks"):
        for row in data["state"][group]:
            row["project_id"] = project_id
    data["state"]["tasks"][0]["description"] = "private-input-sentinel"
    expected = plan_dispatches(
        data["state"],
        project_id=project_id,
        worker_agent_ids=tuple(data["worker_agent_ids"]),
        now=data["now"],
        global_limit=data["global_limit"],
        per_agent_limit=data["per_agent_limit"],
        limit=data["limit"],
        required_capabilities={
            key: tuple(value) for key, value in data["required_capabilities"].items()
        },
    )
    home, state = tmp_path / "home", tmp_path / "unused-state"
    home.mkdir()
    environment = {
        "PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "ascii",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home),
        "LOCALAPPDATA": str(home),
        "AGENTSYNC_DATA_DIR": str(state),
        "TMP": str(tmp_path),
        "TEMP": str(tmp_path),
    }
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    result = subprocess.run(
        [sys.executable, "-B", "-m", "agentsync", "plan"],
        input=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == b"" and result.stdout.isascii()
    observed = json.loads(result.stdout)
    assert observed == json.loads(json.dumps(asdict(expected)))
    assert observed["project_id"] == project_id and observed["scope"] == "planning_only"
    assert not observed["execution_connected"]
    assert observed["core_authorization"] == observed["snapshot_freshness"] == "unverified"
    assert b"private-input-sentinel" not in result.stdout
    assert list(home.iterdir()) == [] and not state.exists()
    assert set(tmp_path.iterdir()) == {home}

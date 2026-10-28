"""Offline usage entrypoint; known local subprocesses never contact clients."""

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
from agentsync.adapters.base import AdapterResult, RunSnapshot
from agentsync.adapters.codex import CodexResult, CodexRun
from agentsync.adapters.codex_events import CodexUsage
from agentsync.adapters.cursor import CursorResult, CursorRun
from agentsync.usage import UsageLedger

ERROR = {"error": {"code": "invalid_input", "message": "Invalid usage input."}}


def ledger(project_id="project"):
    result = UsageLedger(project_id)
    result.record_result(
        CodexResult(
            CodexRun(
                project_id,
                "private-session",
                "task",
                "request",
                "known",
                "succeeded",
                1,
                finished_at=1.25,
            ),
            agent_messages=("private-output",),
            usage=CodexUsage(2, 0, 3),
            client_thread_id="private-client-id",
        )
    )
    result.record_result(
        CursorResult(CursorRun(project_id, "s", "t", "r", "missing", "unknown", 1))
    )
    result.record_result(
        AdapterResult(
            RunSnapshot(project_id, "s", "t", "r", "mock", "succeeded", 1, 5, finished_at=2),
            output="private-mock-output",
        )
    )
    return result


def test_usage_summary_reuses_ledger_without_constructing_core_or_resolving_paths(
    monkeypatch, capsys
):
    original = ledger()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(original.to_json().encode())))
    monkeypatch.setattr(cli, "AgentSyncClient", lambda *_: pytest.fail("Constructed Core client"))
    monkeypatch.setattr(Path, "resolve", lambda *_args, **_kwargs: pytest.fail("Resolved a path"))
    assert cli.main(["usage", "--project-id", "project"]) == 0
    observed = json.loads(capsys.readouterr().out)
    assert observed == asdict(original.summary())
    assert observed["input_tokens"] == dict(
        value=None, known_sum=2, reported_runs=1, unknown_runs=1
    )
    assert observed["simulated_records"] == 1 and observed["protocol_records"] == 2
    assert observed["cost_usd"] is None and not observed["billing_verified"]
    assert observed["verification"] == "unverified" and not observed["real_client_verified"]
    assert "private" not in json.dumps(observed)


@pytest.fixture
def invoke(tmp_path):
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
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
    }
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]

    def call(arguments, raw):
        result = subprocess.run(
            [sys.executable, "-B", "-m", "agentsync", *arguments],
            input=raw,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            timeout=20,
            check=False,
        )
        assert result.stderr == b""
        assert list(home.iterdir()) == [] and not state.exists()
        assert set(tmp_path.iterdir()) == {home}
        return result

    return call


def test_actual_usage_process_matches_mixed_summary_and_accepts_exact_byte_limit(invoke):
    original = ledger()
    raw = original.to_json().encode()
    for data in (raw, raw + b" " * (1024 * 1024 - len(raw))):
        result = invoke(["usage", "--project-id", "project"], data)
        assert result.returncode == 0
        assert json.loads(result.stdout) == asdict(original.summary())
        assert b"private" not in result.stdout and b'"records":' not in result.stdout
    unicode_project = "项目😀"
    original = ledger(unicode_project)
    result = invoke(["usage", "--project-id", unicode_project], original.to_json().encode())
    assert result.returncode == 0 and json.loads(result.stdout) == asdict(original.summary())
    assert result.stdout.isascii()


def test_actual_usage_errors_are_fixed_for_private_malformed_foreign_duplicate_and_oversize(invoke):
    raw = ledger().to_json().encode()
    invalid = [
        b'{"private-secret":"incomplete',
        b"\xffprivate-secret",
        raw.replace(b'"project_id":"project"', b'"project_id":"private-foreign-project"'),
        raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        b"private-secret" + b" " * (1024 * 1024),
    ]
    for data in invalid:
        result = invoke(["usage", "--project-id", "project"], data)
        assert result.returncode == 2 and json.loads(result.stdout) == ERROR


def test_usage_arguments_are_exact_and_owner_operation_named_usage_is_unchanged(
    invoke, monkeypatch, capsys
):
    for arguments in (
        ["usage"],
        ["usage", "--help"],
        ["usage", "--project-id"],
        ["usage", "--project-id=project"],
        ["usage", "--project-id", "project", "--project-id", "private-secret"],
        ["usage", "--data-dir", "private-secret"],
        ["--data-dir", "private-secret", "usage", "--project-id", "project"],
    ):
        result = invoke(arguments, b"private-stdin-secret")
        assert result.returncode == 2 and json.loads(result.stdout) == ERROR

    class OwnerClient:
        def __init__(self, _directory):
            pass

        def owner_call(self, operation, **_payload):
            assert operation == "usage"
            return {"ok": False, "error": {"code": "unknown_operation"}}

    monkeypatch.setattr(cli, "AgentSyncClient", OwnerClient)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert cli.main(["owner", "usage"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "unknown_operation"

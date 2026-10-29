"""Owned startup children only; synthetic protocol faults are test fixtures."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "diagnose_core_startup", Path(__file__).resolve().parents[2] / "tools/diagnose_core_startup.py"
)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_actual_two_workers_share_new_database_without_touching_parent_state(tmp_path):
    existing = tmp_path / "agentsync.db"
    existing.write_bytes(b"private-parent-state")
    report = diagnostic.run_diagnostic(tmp_path, workers=2)
    assert report["passed"] and report["owned_processes_reaped"]
    assert report["counts"] == {"completed": 2, "failed": 0, "timed_out": 0, "not_started": 0}
    assert report["source_hash_scope"] == "core_service_module_only"
    assert report["startup_wall_seconds"] > 0 and report["startup_workers_per_second"] > 0
    for worker in report["worker_observations"]:
        assert worker["exit_status"] == 0
        assert tuple(row["phase"] for row in worker["phases"]) == diagnostic._PHASES
        assert worker["phases"][-1]["source_sha256"] == report["source_sha256"]
        assert worker["phases"][-1]["schema"] == 13
    serialized = json.dumps(report)
    assert str(tmp_path) not in serialized and "private" not in serialized
    assert report["diagnostic_only"] and not report["formal_acceptance"]
    assert not report["real_client_verified"]
    assert (
        list(tmp_path.iterdir()) == [existing] and existing.read_bytes() == b"private-parent-state"
    )


def test_actual_tiny_deadline_kills_reaps_owned_process_and_cleans_private_child(
    tmp_path, monkeypatch
):
    handles = []
    popen = diagnostic.subprocess.Popen

    def track(*args, **kwargs):
        process = popen(*args, **kwargs)
        handles.append(process)
        return process

    monkeypatch.setattr(diagnostic.subprocess, "Popen", track)
    report = diagnostic.run_diagnostic(tmp_path, workers=2, deadline_seconds=1e-100)
    assert not report["passed"] and report["counts"]["timed_out"] == 1
    assert report["counts"]["not_started"] == 1
    assert report["owned_processes_reaped"] and handles
    assert all(process.poll() is not None and process.stdout.closed for process in handles)
    assert list(tmp_path.iterdir()) == []


def test_malformed_or_missing_terminal_child_protocol_fails_without_echo(tmp_path, monkeypatch):
    for child in (
        'print("private-invalid-protocol")',
        'print(\'{"phase":"before_import","elapsed_ms":0}\')',
        'print(\'{"phase":"unknown","elapsed_ms":0}\')',
    ):
        monkeypatch.setattr(diagnostic, "_CHILD", child)
        report = diagnostic.run_diagnostic(tmp_path, workers=1)
        assert not report["passed"] and report["counts"]["failed"] == 1
        assert report["owned_processes_reaped"] and "private" not in json.dumps(report)
        assert list(tmp_path.iterdir()) == []


def test_options_are_validated_before_filesystem_io(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "resolve", lambda *_args, **_kwargs: pytest.fail("Premature I/O"))
    for options in (
        {"workers": True},
        {"workers": 0},
        {"workers": 17},
        {"workers": 1.0},
        {"deadline_seconds": True},
        {"deadline_seconds": 0},
        {"deadline_seconds": 61},
        {"deadline_seconds": float("nan")},
        {"deadline_seconds": float("inf")},
        {"deadline_seconds": 10**400},
    ):
        with pytest.raises(ValueError):
            diagnostic.run_diagnostic(tmp_path, **options)
    with pytest.raises(ValueError):
        diagnostic.run_diagnostic(Path("relative"))
    assert diagnostic.main([]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_options"

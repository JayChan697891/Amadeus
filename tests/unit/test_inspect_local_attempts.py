"""Local metadata consistency observations, never execution or acceptance proof."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "inspect_local_attempts",
    Path(__file__).resolve().parents[2] / "tools/inspect_local_attempts.py",
)
assert SPEC is not None and SPEC.loader is not None
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


def record(run, check_id="pytest", outcome="exited", exit_code=0):
    logs = run / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{check_id}.log"
    log.write_text("local fixture log", encoding="utf-8")
    started = "2026-10-24T10:00:00+00:00"
    result = {
        "id": check_id,
        "status": "pass" if exit_code == 0 else "fail",
        "command": ["python", "unit-only"],
        "cwd": str(run),
        "exit_code": exit_code,
        "started_at": started,
        "finished_at": "2026-10-24T10:00:01+00:00",
        "log": f"logs/{check_id}.log",
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "credential_redactions": 0,
        "log_truncated": False,
        "provenance": "local_process",
    }
    value = {
        "schema": "agentsync.local-process-attempt.v1",
        "scope": "Command attempt only; JUnit and final acceptance remain separate.",
        "phase": "finished",
        "outcome": outcome,
        "check_id": check_id,
        "formal_acceptance": False,
        "junit_validated": False,
        "request": {
            "command": result["command"],
            "cwd": str(run),
            "started_at": started,
            "timeout_seconds": 900,
        },
        "error_type": None
        if outcome == "exited"
        else "TimeoutExpired"
        if outcome == "timed_out"
        else "OSError",
        "result": result,
    }
    sidecar = logs / f"{check_id}.process.json"
    sidecar.write_text(json.dumps(value), encoding="utf-8")
    return value, sidecar, log


def test_successful_record_is_command_observation_only(tmp_path):
    record(tmp_path)
    report = inspector.inspect_attempts(tmp_path)
    assert report["state"] == "command_succeeded"
    assert report["inspection_exit_code"] == 0
    assert report["formal_acceptance"] is False and report["junit_validated"] is False
    assert report["records"][0]["log_hash_verified"] is True


@pytest.mark.parametrize(
    "outcome,exit_code,state",
    [
        ("exited", 7, "command_failed"),
        ("timed_out", None, "timed_out"),
        ("runner_error", None, "runner_error"),
    ],
)
def test_finished_failure_outcomes_are_not_success(tmp_path, outcome, exit_code, state):
    record(tmp_path, outcome=outcome, exit_code=exit_code)
    report = inspector.inspect_attempts(tmp_path)
    assert report["records"][0]["state"] == state
    assert report["inspection_exit_code"] == 1


def test_started_record_is_unknown_not_a_process_liveness_assertion(tmp_path):
    value, sidecar, log = record(tmp_path)
    value.update(phase="started", outcome="unknown")
    del value["result"], value["error_type"]
    sidecar.write_text(json.dumps(value), encoding="utf-8")
    log.unlink()
    report = inspector.inspect_attempts(tmp_path)
    assert report["records"][0]["state"] == "started_unknown"
    assert report["records"][0]["log_hash_verified"] is False
    assert report["inspection_exit_code"] == 2


def test_missing_evidence_is_not_run_even_beside_a_completed_record(tmp_path):
    assert inspector.inspect_attempts(tmp_path)["state"] == "not_run"
    record(tmp_path)
    report = inspector.inspect_attempts(tmp_path, expected_checks=("pytest", "ruff"))
    assert {item["check_id"]: item["state"] for item in report["records"]} == {
        "pytest": "command_succeeded",
        "ruff": "not_run",
    }
    assert report["inspection_exit_code"] == 2


@pytest.mark.parametrize(
    "damage",
    ["json", "schema", "missing_result", "bool_exit", "outcome", "request_mismatch", "bad_date"],
)
def test_damaged_or_incomplete_finished_records_are_invalid(tmp_path, damage):
    value, sidecar, _ = record(tmp_path)
    if damage == "json":
        sidecar.write_text("unfinished JSON", encoding="utf-8")
    else:
        if damage == "schema":
            value["schema"] = "unknown"
        elif damage == "missing_result":
            del value["result"]
        elif damage == "bool_exit":
            value["result"]["exit_code"] = False
        elif damage == "outcome":
            value["outcome"] = "unknown"
        elif damage == "request_mismatch":
            value["request"]["command"] = ["different fixture command"]
        else:
            value["result"]["finished_at"] = "not a date"
        sidecar.write_text(json.dumps(value), encoding="utf-8")
    report = inspector.inspect_attempts(tmp_path)
    assert report["state"] == "invalid" and report["inspection_exit_code"] == 2
    assert report["records"][0]["log_hash_verified"] is False


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_missing_or_changed_log_cannot_count_as_success(tmp_path, damage):
    _, _, log = record(tmp_path)
    if damage == "missing":
        log.unlink()
    else:
        log.write_text("different ordinary log", encoding="utf-8")
    report = inspector.inspect_attempts(tmp_path)
    assert report["state"] == "invalid" and report["inspection_exit_code"] == 2


@pytest.mark.parametrize("limit", ["json", "log", "count"])
def test_metadata_and_log_processing_limits_fail_closed(tmp_path, limit):
    _, sidecar, log = record(tmp_path)
    if limit == "json":
        sidecar.write_bytes(b" " * (256 * 1024 + 1))
    elif limit == "log":
        with log.open("r+b") as stream:
            stream.truncate(32 * 1024 * 1024 + 1)
    else:
        for index in range(128):
            record(tmp_path, check_id=f"check_{index}")
    report = inspector.inspect_attempts(tmp_path)
    assert report["state"] == "invalid" and report["inspection_exit_code"] == 2


@pytest.mark.parametrize("scenario,expected", [("success", 0), ("failed", 1), ("missing", 2)])
def test_cli_reports_exit_codes_and_expected_checks(tmp_path, capsys, scenario, expected):
    if scenario != "missing":
        record(tmp_path, exit_code=0 if scenario == "success" else 7)
    code = inspector.main(["--run", str(tmp_path), "--expect", "pytest"])
    report = json.loads(capsys.readouterr().out)
    assert code == expected == report["inspection_exit_code"]
    assert report["records"][0]["check_id"] == "pytest"
    assert report["formal_acceptance"] is False and report["junit_validated"] is False


def test_invalid_run_or_expected_check_inputs_return_static_invalid(tmp_path):
    for path, expected in ((Path("relative"), ()), (tmp_path / "missing", ()), (tmp_path, ("",))):
        report = inspector.inspect_attempts(path, expected_checks=expected)
        assert report["state"] == "invalid" and report["inspection_exit_code"] == 2


def test_output_never_contains_record_commands_cwd_or_log_text(tmp_path):
    value, sidecar, _ = record(tmp_path)
    command = ["ordinary private fixture text"]
    value["request"]["command"] = command
    value["result"]["command"] = command
    sidecar.write_text(json.dumps(value), encoding="utf-8")
    rendered = json.dumps(inspector.inspect_attempts(tmp_path))
    assert "ordinary private fixture text" not in rendered
    assert "local fixture log" not in rendered
    assert str(tmp_path) not in rendered
    assert '"command"' not in rendered and '"cwd"' not in rendered


def test_current_collector_local_print_is_inspected_without_file_changes(tmp_path):
    collector_spec = importlib.util.spec_from_file_location(
        "collector_for_inspector_test",
        Path(__file__).resolve().parents[2] / "tools/release_acceptance.py",
    )
    assert collector_spec is not None and collector_spec.loader is not None
    collector = importlib.util.module_from_spec(collector_spec)
    collector_spec.loader.exec_module(collector)
    project = tmp_path / "local-project"
    project.mkdir()
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    result = collector.execute(
        "local_print",
        [sys.executable, "-I", "-c", "print('local inspector smoke')"],
        project,
        run,
        scratch,
    )
    assert result["exit_code"] == 0
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run.rglob("*")
        if path.is_file()
    }
    report = inspector.inspect_attempts(run)
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in run.rglob("*")
        if path.is_file()
    }
    assert report["state"] == "command_succeeded" and report["inspection_exit_code"] == 0
    assert before == after

"""Read local command-attempt consistency; never execute, resume or accept work.

Missing evidence does not prove a command never ran. A started record does not
prove its process is alive. Matching hashes establish consistency, not authenticity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_RECORDS = 128
MAX_JSON_BYTES = 256 * 1024
MAX_LOG_BYTES = 32 * 1024 * 1024
CHECK_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid record")


def _shape(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    _require(type(value) is dict and required <= value.keys() <= required | (optional or set()))


def _text(value: Any, limit: int = MAX_JSON_BYTES) -> None:
    _require(type(value) is str and 0 < len(value) <= limit and "\x00" not in value)
    _require(len(value.encode("utf-8")) <= limit)


def _date(value: Any) -> datetime:
    _text(value, 80)
    parsed = datetime.fromisoformat(value)
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
    return parsed


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def _nonfinite(_value: str) -> Any:
    raise ValueError("Invalid number")


def _read_record(path: Path, run: Path, check_id: str) -> dict[str, Any]:
    _require(not path.is_symlink() and path.is_file())
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    _require(len(raw) <= MAX_JSON_BYTES)
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite)
    phase = value.get("phase") if type(value) is dict else None
    required = {
        "schema",
        "scope",
        "phase",
        "outcome",
        "check_id",
        "formal_acceptance",
        "junit_validated",
        "request",
    }
    _require(phase in ("started", "finished"))
    if phase == "finished":
        required |= {"result", "error_type"}
    _shape(value, required)
    _require(value["schema"] == "agentsync.local-process-attempt.v1")
    _require(value["scope"] == "Command attempt only; JUnit and final acceptance remain separate.")
    _require(value["check_id"] == check_id)
    _require(value["formal_acceptance"] is False and value["junit_validated"] is False)
    request = value["request"]
    _shape(request, {"command", "cwd", "started_at", "timeout_seconds"})
    _require(type(request["command"]) is list and 0 < len(request["command"]) <= 1024)
    for argument in request["command"]:
        # Empty command arguments are valid, but strings must remain bounded.
        _require(type(argument) is str and len(argument.encode("utf-8")) <= MAX_JSON_BYTES)
    _text(request["cwd"])
    started = _date(request["started_at"])
    timeout = request["timeout_seconds"]
    _require(type(timeout) is int and 1 <= timeout <= 7200)
    _require(timeout == 900 or check_id in {"pytest", "wheel_pytest", "sdist_pytest"})
    if phase == "started":
        _require(value["outcome"] == "unknown")
        return {
            "check_id": check_id,
            "state": "started_unknown",
            "log_hash_verified": False,
            "timeout_seconds": timeout,
        }
    result = value["result"]
    _shape(
        result,
        {
            "id",
            "status",
            "command",
            "cwd",
            "exit_code",
            "started_at",
            "finished_at",
            "log",
            "log_sha256",
            "credential_redactions",
            "log_truncated",
            "provenance",
        },
        {"timeout_seconds"},
    )
    _require(result["id"] == check_id and result["provenance"] == "local_process")
    _require(all(result[key] == request[key] for key in ("command", "cwd", "started_at")))
    _require(type(result["command"]) is list)
    _require(_date(result["finished_at"]) >= started)
    _require(type(result["credential_redactions"]) is int and result["credential_redactions"] >= 0)
    _require(type(result["log_truncated"]) is bool)
    if timeout != 900 or "timeout_seconds" in result:
        _require(
            type(result.get("timeout_seconds")) is int and result["timeout_seconds"] == timeout
        )
    outcome = value["outcome"]
    code = result["exit_code"]
    if outcome == "exited":
        _require(type(code) is int and -(2**63) <= code < 2**63 and value["error_type"] is None)
        _require(result["status"] == ("pass" if code == 0 else "fail"))
        state = "command_succeeded" if code == 0 else "command_failed"
    else:
        _require(
            outcome in ("timed_out", "runner_error") and code is None and result["status"] == "fail"
        )
        _text(value["error_type"], 100)
        _require(outcome != "timed_out" or value["error_type"] == "TimeoutExpired")
        state = outcome
    _require(result["log"] == f"logs/{check_id}.log")
    expected_hash = result["log_sha256"]
    _require(
        type(expected_hash) is str and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None
    )
    log = run / "logs" / f"{check_id}.log"
    _require(not log.is_symlink() and log.is_file())
    digest = hashlib.sha256()
    size = 0
    with log.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            size += len(chunk)
            _require(size <= MAX_LOG_BYTES)
            digest.update(chunk)
    _require(digest.hexdigest() == expected_hash)
    return {
        "check_id": check_id,
        "state": state,
        "exit_code": code,
        "timeout_seconds": timeout,
        "log_hash_verified": True,
    }


def inspect_attempts(run: Path, *, expected_checks: tuple[str, ...] = ()) -> dict[str, Any]:
    """Observe bounded metadata only; missing means no evidence, never never-ran."""
    records: list[dict[str, Any]] = []
    try:
        _require(isinstance(run, Path) and run.is_absolute() and run.is_dir())
        run = run.resolve()
        _require(type(expected_checks) is tuple and len(expected_checks) <= MAX_RECORDS)
        _require(
            all(
                type(name) is str and CHECK_ID.fullmatch(name) is not None
                for name in expected_checks
            )
        )
        _require(len(set(expected_checks)) == len(expected_checks))
        logs = run / "logs"
        _require(not logs.is_symlink() and (not logs.exists() or logs.is_dir()))
        paths = []
        for path in logs.glob("*.process.json"):
            paths.append(path)
            _require(len(paths) <= MAX_RECORDS)
    except (OSError, ValueError, TypeError, RuntimeError):
        return _report(
            [
                {
                    "check_id": None,
                    "state": "invalid",
                    "reason": "invalid_run_or_record_limit",
                    "log_hash_verified": False,
                }
            ]
        )
    found = set()
    for path in sorted(paths):
        check_id = path.name.removesuffix(".process.json")
        if CHECK_ID.fullmatch(check_id) is None:
            records.append(
                {
                    "check_id": None,
                    "state": "invalid",
                    "reason": "invalid_record_name",
                    "log_hash_verified": False,
                }
            )
            continue
        found.add(check_id)
        try:
            records.append(_read_record(path, run, check_id))
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            records.append(
                {
                    "check_id": check_id,
                    "state": "invalid",
                    "reason": "invalid_record_or_log",
                    "log_hash_verified": False,
                }
            )
    records.extend(
        {"check_id": name, "state": "not_run", "log_hash_verified": False}
        for name in expected_checks
        if name not in found
    )
    return _report(records)


def _report(records: list[dict[str, Any]]) -> dict[str, Any]:
    states = {record["state"] for record in records}
    if "invalid" in states:
        state, exit_code = "invalid", 2
    elif "started_unknown" in states:
        state, exit_code = "incomplete", 2
    elif not states or "not_run" in states:
        state, exit_code = "not_run", 2
    elif states != {"command_succeeded"}:
        state, exit_code = "command_failed", 1
    else:
        state, exit_code = "command_succeeded", 0
    return {
        "schema": "agentsync.local-attempt-inspection.v1",
        "scope": "record_consistency_only",
        "formal_acceptance": False,
        "junit_validated": False,
        "state": state,
        "inspection_exit_code": exit_code,
        "records": records,
        "limitations": [
            "Missing/not_run means no record evidence, not proof that a command never ran.",
            "started_unknown does not establish whether a process is alive.",
            "Log hashes establish consistency only, not record authenticity.",
            "Command success does not validate JUnit or establish formal acceptance.",
            "Only the current v1 field shape is supported; earlier variants missing outcome/error_type are invalid, without inference or migration.",
            "At most 128 sidecars and 128 expected IDs are accepted; their union can produce up to 256 rows.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", type=Path, required=True, help="Existing absolute local run directory"
    )
    parser.add_argument(
        "--expect", nargs="*", default=[], help="Check IDs whose absent records count as not_run"
    )
    args = parser.parse_args(argv)
    report = inspect_attempts(args.run, expected_checks=tuple(args.expect))
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(report["inspection_exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())

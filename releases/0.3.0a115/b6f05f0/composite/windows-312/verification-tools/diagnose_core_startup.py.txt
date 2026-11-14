"""Owned local interpreter/Core startup diagnostic, never formal acceptance.

Wall time includes imports and OS spawning. One global deadline bounds observed
completion; process creation/kill/reap/cleanup are not preemptive hard deadlines.
Only owned interpreter handles are killed, without process-tree cleanup claims.
The source pin covers the Core service module, not the complete package.
"""

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
from typing import Any, NoReturn

import agentsync
from agentsync.storage.database import SCHEMA_VERSION

_PHASES = (
    "before_import",
    "after_import",
    "before_connect",
    "after_connect",
    "before_wal",
    "after_wal",
    "after_init",
    "verified",
)
_CHILD = r"""
import hashlib, json, sqlite3, sys
from contextlib import closing
from pathlib import Path
from time import perf_counter
started = perf_counter()
def emit(phase, **fields):
    print(json.dumps({"phase": phase, "elapsed_ms": (perf_counter()-started)*1000,
                      **fields}, separators=(",", ":")), flush=True)
try:
    emit("before_import")
    package_root, data, expected = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    source = package_root / "agentsync" / "core" / "service.py"
    with source.open("rb") as stream:
        raw = stream.read(2*1024*1024+1)
    if len(raw) > 2*1024*1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError
    sys.path.insert(0, str(package_root))
    import agentsync.core.service as service
    import agentsync.storage.database as database
    if Path(service.__file__).resolve() != source.resolve():
        raise ValueError
    emit("after_import")
    original_connect, original_wal = database.connect, database._enable_wal
    def connect(path):
        emit("before_connect")
        connection = original_connect(path)
        emit("after_connect")
        return connection
    def wal(connection):
        emit("before_wal")
        original_wal(connection)
        emit("after_wal")
    database.connect, database._enable_wal = connect, wal
    core = service.Core(data)
    emit("after_init")
    with closing(sqlite3.connect(core.db_path)) as db:
        schema = db.execute("PRAGMA user_version").fetchone()[0]
        integrity = db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall() == []
    emit("verified", source_sha256=expected, schema=schema,
         integrity=integrity, foreign_keys=foreign_keys)
    if schema != database.SCHEMA_VERSION or not integrity or not foreign_keys:
        raise SystemExit(1)
except BaseException:
    emit("failed")
    raise SystemExit(1)
"""


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _protocol(text: str, source_hash: str) -> tuple[bool, list[dict[str, Any]]]:
    """Accept only fixed phase fields; never echo unknown child text or errors."""
    events: list[dict[str, Any]] = []
    try:
        if len(text) > 8192 or not 1 <= len(text.splitlines()) <= 9:
            raise ValueError
        previous = 0.0
        for line in text.splitlines():
            row = json.loads(line, object_pairs_hook=_members)
            if type(row) is not dict or type(row.get("phase")) is not str:
                raise ValueError
            phase = row["phase"]
            elapsed: Any = row.get("elapsed_ms")
            if (
                type(elapsed) not in (int, float)
                or not math.isfinite(elapsed)
                or elapsed < previous
            ):
                raise ValueError
            expected_fields = {"phase", "elapsed_ms"}
            if phase == "verified":
                expected_fields |= {"source_sha256", "schema", "integrity", "foreign_keys"}
                if (
                    row.get("source_sha256") != source_hash
                    or type(row.get("schema")) is not int
                    or row["schema"] != SCHEMA_VERSION
                    or row.get("integrity") is not True
                    or row.get("foreign_keys") is not True
                ):
                    raise ValueError
            if set(row) != expected_fields:
                raise ValueError
            if phase == "failed":
                if line != text.splitlines()[-1]:
                    raise ValueError
            elif len(events) >= len(_PHASES) or phase != _PHASES[len(events)]:
                raise ValueError
            previous = float(elapsed)
            events.append(row)
        return tuple(row["phase"] for row in events) == _PHASES, events
    except (ValueError, TypeError, OverflowError, RecursionError):
        return False, []


def run_diagnostic(
    scratch_parent: Path, workers: int = 8, deadline_seconds: float = 30
) -> dict[str, Any]:
    if (
        not isinstance(scratch_parent, Path)
        or not scratch_parent.is_absolute()
        or type(workers) is not int
        or not 1 <= workers <= 16
        or type(deadline_seconds) not in (int, float)
        or not 0 < deadline_seconds <= 60
        or not math.isfinite(deadline_seconds)
    ):
        raise ValueError("Invalid startup diagnostic options.")
    try:
        parent = scratch_parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise ValueError("Invalid startup diagnostic scratch parent.") from None
    package_root = Path(agentsync.__file__).resolve().parents[1]
    reports: list[dict[str, Any]] = [
        dict(worker=index, state="failed", exit_status=None, phases=[]) for index in range(workers)
    ]
    source_hash = None
    elapsed = 0.0
    reaped = True
    try:
        with (package_root / "agentsync" / "core" / "service.py").open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError
        source_hash = hashlib.sha256(raw).hexdigest()
        with TemporaryDirectory(prefix="agentsync-startup-", dir=parent) as child:
            processes: list[tuple[int, subprocess.Popen[str]]] = []
            started = perf_counter()
            deadline = started + deadline_seconds
            try:
                for index in range(workers):
                    if index and perf_counter() >= deadline:
                        for row in reports[index:]:
                            row["state"] = "not_started"
                        break
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-c",
                            _CHILD,
                            str(package_root),
                            str(Path(child) / "data"),
                            source_hash,
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        encoding="utf-8",
                    )
                    processes.append((index, process))
                pending = list(processes)
                while pending and perf_counter() < deadline:
                    for index, process in list(pending):
                        if process.poll() is not None:
                            output, _ = process.communicate(timeout=5)
                            valid, events = _protocol(output, source_hash)
                            reports[index].update(
                                state="completed"
                                if valid and process.returncode == 0
                                else "failed",
                                exit_status=process.returncode,
                                phases=events,
                            )
                            pending.remove((index, process))
                    if pending:
                        sleep(min(0.01, max(0, deadline - perf_counter())))
                for index, _ in pending:
                    reports[index]["state"] = "timed_out"
            finally:
                for index, process in processes:
                    try:
                        if process.poll() is None:
                            process.kill()
                        output, _ = process.communicate(timeout=5)
                        if not reports[index]["phases"]:
                            _, events = _protocol(output, source_hash)
                            reports[index]["phases"] = events
                        reports[index]["exit_status"] = process.returncode
                    except Exception:
                        reaped = False
                        reports[index]["state"] = "failed"
                    finally:
                        if process.stdout is not None:
                            process.stdout.close()
                elapsed = perf_counter() - started
    except Exception:
        # Setup/protocol/cleanup errors cannot produce a passed report.
        if reports:
            reports[0]["state"] = "failed"
    counts = {
        state: sum(row["state"] == state for row in reports)
        for state in ("completed", "failed", "timed_out", "not_started")
    }
    return {
        "package_version": agentsync.__version__,
        "scope": "local_core_startup",
        "diagnostic_only": True,
        "formal_acceptance": False,
        "real_client_verified": False,
        "source_sha256": source_hash,
        "source_hash_scope": "core_service_module_only",
        "workers": workers,
        "deadline_seconds": float(deadline_seconds),
        "startup_wall_seconds": elapsed,
        "startup_workers_per_second": workers / elapsed
        if elapsed > 0 and counts["completed"] == workers
        else None,
        "owned_processes_reaped": reaped,
        "counts": counts,
        "worker_observations": reports,
        "passed": counts["completed"] == workers and reaped,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Invalid startup diagnostic options.")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--scratch-parent", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    try:
        options = parser.parse_args(argv)
        report = run_diagnostic(options.scratch_parent, options.workers, options.deadline_seconds)
    except ValueError:
        print(
            json.dumps(
                {
                    "passed": False,
                    "error": "invalid_options",
                    "diagnostic_only": True,
                    "formal_acceptance": False,
                    "real_client_verified": False,
                }
            )
        )
        return 2
    print(json.dumps(report, separators=(",", ":"), allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

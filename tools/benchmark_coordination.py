"""Declared local Core claim contention diagnostic, never formal acceptance.

All state is disposable under an explicit scratch parent. Core startup, barrier,
verification and cleanup are excluded from latency and throughput measurements.
Barrier/SQLite bounds are ordinary operation limits, not preemptive timeouts.
The declared latency budget is a diagnostic threshold, not a Release SLO.
"""

import argparse
import hashlib
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, BrokenBarrierError
from time import perf_counter
from typing import Any, NoReturn

from agentsync import __version__
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def _claim(
    core: Core, auth: dict[str, str], task_id: str, barrier: Barrier, request: str
) -> tuple[str, float | None, float | None, dict[str, Any]]:
    try:
        barrier.wait(timeout=10)
    except BrokenBarrierError:
        return "barrier_error", None, None, {}
    started = perf_counter()
    response = {}
    try:
        response = core.execute(
            "claim_task", {**auth, "task_id": task_id, "expected_version": 1, "request_id": request}
        )
        outcome = "winner"
    except AgentSyncError as exc:
        outcome = "version_conflict" if exc.code == "version_conflict" else "core_claim_error"
    except Exception:
        outcome = "claim_error"
    return outcome, started, perf_counter(), response


def _claim_audit(
    db: sqlite3.Connection,
    project_id: str,
    expected: dict[tuple[str, str], tuple[str, str]],
) -> dict[str, int]:
    """Compare final claim receipts by identity; return only aggregate diagnostics."""
    rows = db.execute(
        "SELECT actor_id,request_id_digest,actor_kind,outcome,code FROM audit_events "
        "WHERE project_id=? AND operation='claim_task'",
        (project_id,),
    ).fetchall()
    seen: dict[tuple[str, str], int] = {}
    counts = dict(
        expected=len(expected),
        observed=len(rows),
        success=0,
        denied=0,
        missing=0,
        duplicate=0,
        unexpected=0,
        mismatch=0,
    )
    for actor_id, request_digest, actor_kind, outcome, code in rows:
        key = (actor_id, request_digest)
        seen[key] = seen.get(key, 0) + 1
        if outcome in {"success", "denied"}:
            counts[outcome] += 1
        if key not in expected:
            counts["unexpected"] += 1
        elif actor_kind != "agent" or (outcome, code) != expected[key]:
            counts["mismatch"] += 1
    counts["missing"] = sum(key not in seen for key in expected)
    counts["duplicate"] = sum(count - 1 for count in seen.values())
    return counts


def run_benchmark(
    scratch_parent: Path, workers: int = 8, rounds: int = 8, p95_budget_ms: float = 1000
) -> dict[str, Any]:
    """Run owned simultaneous claim rounds; invalid options raise a fixed ValueError."""
    if (
        not isinstance(scratch_parent, Path)
        or not scratch_parent.is_absolute()
        or type(workers) is not int
        or not 1 <= workers <= 32
        or type(rounds) is not int
        or not 1 <= rounds <= 32
        or type(p95_budget_ms) not in (int, float)
        or not 0 < p95_budget_ms <= 60000
        or not math.isfinite(p95_budget_ms)
    ):
        raise ValueError("Invalid coordination benchmark options.")
    try:
        parent = scratch_parent.resolve(strict=True)
        if not parent.is_dir():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise ValueError("Invalid coordination benchmark scratch parent.") from None
    errors: dict[str, int] = {}
    checks = dict(
        persisted_winners=True,
        cancelled_status_versions=True,
        persisted_task_count=False,
        sqlite_integrity=False,
        foreign_keys=False,
        claim_audit_complete=False,
    )
    expected_audit: dict[tuple[str, str], tuple[str, str]] = {}
    claim_audit = dict(
        expected=0,
        observed=0,
        success=0,
        denied=0,
        missing=0,
        duplicate=0,
        unexpected=0,
        mismatch=0,
    )
    observations = []
    latencies: list[float] = []
    workload_seconds = 0.0
    try:
        with TemporaryDirectory(prefix="agentsync-coordination-", dir=parent) as child:
            root = Path(child)
            core = Core(root / "data")
            project = core.execute(
                "create_project", {"name": "local-diagnostic", "root_path": str(root)}
            )
            actors = []
            agent_ids = []
            for index in range(workers):
                actor = core.execute("register_agent", {**project, "name": f"worker-{index}"})
                agent_ids.append(actor["agent_id"])
                core.execute_owner(
                    "set_agent_roles",
                    {
                        **project,
                        "agent_id": actor["agent_id"],
                        "roles": ["worker"],
                        "expected_version": 1,
                        "request_id": f"grant-{index}",
                    },
                )
                actors.append(
                    {
                        "project_id": project["project_id"],
                        "session_id": actor["session_id"],
                        "session_token": actor["session_token"],
                    }
                )
            cores = [Core(core.data_dir) for _ in actors]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for round_index in range(1, rounds + 1):
                    task = core.execute(
                        "create_task",
                        {**actors[0], "title": "diagnostic", "request_id": f"task-{round_index}"},
                    )
                    barrier = Barrier(workers)
                    requests = [f"claim-{round_index}-{index}" for index in range(workers)]
                    futures = [
                        executor.submit(
                            _claim,
                            cores[index],
                            auth,
                            task["id"],
                            barrier,
                            requests[index],
                        )
                        for index, auth in enumerate(actors)
                    ]
                    results = [future.result() for future in futures]
                    for index, (outcome, _, _, _) in enumerate(results):
                        if outcome in {"winner", "version_conflict"}:
                            key = (
                                agent_ids[index],
                                hashlib.sha256(requests[index].encode()).hexdigest(),
                            )
                            expected_audit[key] = (
                                ("success", "ok")
                                if outcome == "winner"
                                else ("denied", "version_conflict")
                            )
                    winners = [
                        index for index, result in enumerate(results) if result[0] == "winner"
                    ]
                    conflicts = sum(result[0] == "version_conflict" for result in results)
                    timed = [
                        (start, end)
                        for _, start, end, _ in results
                        if start is not None and end is not None
                    ]
                    latencies.extend((end - start) * 1000 for start, end in timed)
                    if timed:
                        workload_seconds += max(end for _, end in timed) - min(
                            start for start, _ in timed
                        )
                    for outcome, _, _, _ in results:
                        if outcome not in {"winner", "version_conflict"}:
                            errors[outcome] = errors.get(outcome, 0) + 1
                    observations.append(
                        {
                            "round": round_index,
                            "winners": len(winners),
                            "expected_version_conflicts": conflicts,
                            "unexpected_errors": workers - len(winners) - conflicts,
                        }
                    )
                    if len(winners) != 1:
                        checks["persisted_winners"] = checks["cancelled_status_versions"] = False
                        continue
                    winner = winners[0]
                    current = next(
                        row
                        for row in core.execute("list_tasks", actors[0])["tasks"]
                        if row["id"] == task["id"]
                    )
                    checks["persisted_winners"] &= (
                        current["status"] == "claimed"
                        and current["version"] == 2
                        and current["owner_session_id"] == actors[winner]["session_id"]
                    )
                    cores[winner].execute(
                        "update_task",
                        {
                            **actors[winner],
                            "task_id": task["id"],
                            "expected_version": 2,
                            "lease_token": results[winner][3]["lease_token"],
                            "status": "cancelled",
                            "request_id": f"cancel-{round_index}",
                        },
                    )
            persisted = core.execute("list_tasks", actors[0])["tasks"]
            checks["persisted_task_count"] = len(persisted) == rounds
            checks["cancelled_status_versions"] &= all(
                row["status"] == "cancelled"
                and row["version"] == 3
                and row["lease_expires_at"] is None
                for row in persisted
            )
            with closing(sqlite3.connect(core.db_path)) as db:
                checks["sqlite_integrity"] = db.execute("PRAGMA integrity_check").fetchall() == [
                    ("ok",)
                ]
                checks["foreign_keys"] = db.execute("PRAGMA foreign_key_check").fetchall() == []
                claim_audit = _claim_audit(db, project["project_id"], expected_audit)
                checks["claim_audit_complete"] = claim_audit[
                    "expected"
                ] == workers * rounds and not any(
                    claim_audit[key] for key in ("missing", "duplicate", "unexpected", "mismatch")
                )
    except Exception:
        errors["benchmark_error"] = errors.get("benchmark_error", 0) + 1
    ordered = sorted(latencies)
    checks["persisted_winners"] &= len(observations) == rounds
    checks["cancelled_status_versions"] &= len(observations) == rounds
    percentiles = {
        f"p{percent}": ordered[math.ceil(percent / 100 * len(ordered)) - 1] if ordered else None
        for percent in (50, 95, 99)
    }
    checks.update(
        rounds_completed=len(observations) == rounds,
        claims_measured=len(latencies) == workers * rounds,
        single_winner_each_round=bool(observations)
        and all(row["winners"] == 1 for row in observations),
        expected_conflicts=all(
            row["expected_version_conflicts"] == workers - 1 for row in observations
        ),
        valid_timing=bool(latencies) and min(latencies) > 0 and workload_seconds > 0,
    )
    budget_passed = percentiles["p95"] is not None and percentiles["p95"] <= p95_budget_ms
    return {
        "package_version": __version__,
        "scope": "local_core_claim_contention",
        "diagnostic_only": True,
        "formal_acceptance": False,
        "real_client_verified": False,
        "workload": {
            "workers": workers,
            "rounds": rounds,
            "claims": len(latencies),
            "timing_scope": "claims_after_barrier_excluding_setup_verification_cleanup",
            "throughput_denominator": "sum_of_round_claim_spans",
        },
        "claim_latency_ms": percentiles,
        "timed_workload_seconds": workload_seconds,
        "throughput_claim_attempts_per_second": len(latencies) / workload_seconds
        if workload_seconds > 0
        else None,
        "declared_p95_budget_ms": float(p95_budget_ms),
        "p95_budget_passed": budget_passed,
        "round_observations": observations,
        "unexpected_errors": errors,
        "claim_audit": claim_audit,
        "functional_checks": checks,
        "passed": all(checks.values()) and not errors and budget_passed,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Invalid coordination benchmark options.")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("--scratch-parent", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--rounds", type=int, required=True)
    parser.add_argument("--p95-budget-ms", type=float, required=True)
    try:
        options = parser.parse_args(argv)
        report = run_benchmark(
            options.scratch_parent, options.workers, options.rounds, options.p95_budget_ms
        )
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

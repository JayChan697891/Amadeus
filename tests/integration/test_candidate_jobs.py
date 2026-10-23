"""Actual disposable Git/SQLite candidate queue; no execution claim."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_candidate_export import prepared as prepared
from test_candidate_export import world as world

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import candidate_jobs as module
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.jobs import VerificationJobs


def owner(prepared):
    return {k: prepared[1][k] for k in ("project_id", "admin_token")}


def counts(prepared):
    with connect(prepared[0].db_path) as db:
        return tuple(
            db.execute("SELECT count(*) FROM " + table).fetchone()[0]
            for table in ("candidate_verification_jobs", "candidate_verification_requests")
        )


def save_queue(prepared, name, receipt, current, cancel_receipt=None):
    directory = os.environ.get("AGENTSYNC_CANDIDATE_QUEUE_EVIDENCE_DIR")
    if not directory:
        return
    with connect(prepared[0].db_path) as db:
        stored = dict(
            db.execute(
                "SELECT * FROM candidate_verification_jobs WHERE id=?", (receipt["id"],)
            ).fetchone()
        )
        requests = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM candidate_verification_requests WHERE job_id=? AND project_id=? ORDER BY operation,request_id",
                (receipt["id"], receipt["project_id"]),
            )
        ]
    assert hashlib.sha256(stored["metadata_json"].encode()).hexdigest() == stored["metadata_sha256"]
    environment = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
    target = Path(directory) / environment
    assert target.is_absolute()
    target.mkdir(parents=True, exist_ok=True)
    data = {
        "environment_id": environment,
        "actual_git_candidate_export": True,
        "execution_verified": False,
        "real_clients_verified": False,
        "read_observation": "DB-only, no freshness assertion",
        "historical_receipt": receipt,
        "historical_cancel_receipt": cancel_receipt,
        "current": current,
        "stored_queue_row": stored,
        "stored_request_rows": requests,
        "expected_literal_source_sha256": hashlib.sha256(
            b"def solve(x): return 'candidate'\n"
        ).hexdigest(),
    }
    (target / (name + ".json")).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cancel(prepared, job, **extra):
    return CandidateVerificationJobs(prepared[0]).cancel(
        **(
            owner(prepared)
            | {"job_id": job["id"], "expected_version": job["version"], "request_id": "cancel"}
            | extra
        )
    )


def profile(value=True):
    return DockerProfile("sha256:" + "b" * 64, (JsonCase(None, value),))


def enqueue(prepared, **extra):
    return CandidateVerificationJobs(prepared[0]).enqueue(
        **(prepared[1] | {"profile": profile(), "request_id": "enqueue"} | extra)
    )


def test_actual_candidate_queue_roundtrip(prepared):
    result = enqueue(prepared)
    assert result["candidate_sha"] == prepared[1]["expected_candidate_sha"]
    assert (
        result["source_sha256"] == hashlib.sha256(b"def solve(x): return 'candidate'\n").hexdigest()
    )
    assert result["receipt_kind"] == "historical_enqueue" and result["current_state"] is False
    current = CandidateVerificationJobs(prepared[0]).get(
        **{k: prepared[1][k] for k in ("project_id", "admin_token")}, job_id=result["id"]
    )
    assert current["current_state"] is True and "receipt_kind" not in current
    assert (
        current["execution_connected"] is False and current["execution_assessment"] == "unverified"
    )
    assert counts(prepared) == (1, 1)
    baseline_hash = hashlib.sha256(
        (prepared[0].data_dir.parent / "user-repository" / "solution.py").read_bytes()
    ).hexdigest()
    assert baseline_hash != result["source_sha256"]
    save_queue(prepared, "actual-candidate-queue", result, current)


@pytest.mark.parametrize(
    "attribute,value",
    [("cases", ()), ("timeout_seconds", 10**400)],
    ids=["empty-cases", "overflow-timeout"],
)
def test_invalid_profile_cases_rejected_without_queue_mutation(prepared, attribute, value):
    invalid = profile()
    # Fault-injected trusted object corruption; never a serialized candidate API.
    object.__setattr__(invalid, attribute, value)
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared, profile=invalid)
    assert exc.value.code == "invalid_profile"
    assert counts(prepared) == (0, 0)


def test_historical_replays_survive_cancel_and_missing_git_storage(prepared, monkeypatch):
    original = enqueue(prepared)
    cancelled = cancel(prepared, original)
    managed = prepared[0].data_dir / "managed-git"
    managed.rename(managed.with_name("unavailable-managed-git"))

    def forbidden(*args, **kwargs):
        pytest.fail("Reads, cancellation and committed replay must never invoke Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert enqueue(prepared) == original
    assert cancel(prepared, original) == cancelled
    service = CandidateVerificationJobs(prepared[0])
    assert service.get(**owner(prepared), job_id=original["id"])["status"] == "cancelled"
    assert service.list(**owner(prepared))["jobs"][0]["version"] == 2
    restarted = CandidateVerificationJobs(Core(prepared[0].data_dir)).get(
        **owner(prepared), job_id=original["id"]
    )
    assert restarted["status"] == "cancelled" and restarted["current_state"] is True
    save_queue(prepared, "historical-replay-after-cancel-restart", original, restarted, cancelled)
    assert counts(prepared) == (1, 2)
    with connect(prepared[0].db_path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE operation LIKE 'candidate_verification_%' AND outcome='success'"
            ).fetchone()[0]
            == 2
        )


@pytest.mark.parametrize("change", ["candidate", "sha", "profile"])
def test_request_payload_conflict_is_db_only(prepared, monkeypatch, change):
    enqueue(prepared)

    def forbidden(*args, **kwargs):
        pytest.fail("Conflicting committed request must fail before Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    extra = (
        {"candidate_id": "foreign-candidate"}
        if change == "candidate"
        else {"expected_candidate_sha": "a" * 40}
        if change == "sha"
        else {"profile": profile(False)}
    )
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared, **extra)
    assert exc.value.code == "idempotency_conflict" and counts(prepared) == (1, 1)


@pytest.mark.parametrize(
    "extra",
    [{"admin_token": "private-token-sentinel"}, {"project_id": "foreign-project"}],
    ids=["wrong-owner", "foreign-project"],
)
def test_owner_auth_precedes_git_storage(prepared, monkeypatch, extra):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthenticated queue request must fail before Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared, **extra)
    assert exc.value.code == "unauthorized"
    assert "private-token-sentinel" not in str(exc.value)
    assert counts(prepared) == (0, 0)


@pytest.mark.parametrize(
    "extra",
    [
        {"request_id": ""},
        {"candidate_id": "x" * 201},
        {"request_id": "\ud800"},
        {"admin_token": "💡" * 1025},
    ],
    ids=["empty", "long-id", "surrogate", "token-bytes"],
)
def test_request_bounds_are_safe(prepared, extra):
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared, **extra)
    assert exc.value.code == "validation_error" and counts(prepared) == (0, 0)


@pytest.mark.parametrize(
    "column,value",
    [
        ("profile_sha256", "c" * 64),
        ("image_id", "sha256:" + "c" * 64),
        ("profile_kind", "changed-profile"),
    ],
)
def test_profile_column_corruption_rejected_by_get_list_and_cancel(prepared, column, value):
    job = enqueue(prepared)
    with connect(prepared[0].db_path) as db:
        db.execute(f"UPDATE candidate_verification_jobs SET {column}=?", (value,))
    service = CandidateVerificationJobs(prepared[0])
    for action in (
        lambda: service.get(**owner(prepared), job_id=job["id"]),
        lambda: service.list(**owner(prepared)),
        lambda: cancel(prepared, job),
    ):
        with pytest.raises(AgentSyncError) as exc:
            action()
        assert exc.value.code == "corrupt_candidate_queue"


@pytest.mark.parametrize(
    "change",
    ["unknown", "duplicate", "nonfinite", "deep", "oversized", "manifest", "receipt", "digest"],
    ids=str,
)
def test_stored_metadata_corruption_fails_closed(prepared, change):
    job = enqueue(prepared)
    with connect(prepared[0].db_path) as db:
        raw = db.execute("SELECT metadata_json FROM candidate_verification_jobs").fetchone()[0]
        data = json.loads(raw)
        if change == "unknown":
            data["private-secret-sentinel"] = "should-never-project"
        elif change == "manifest":
            data["snapshot"]["manifest"][0][0] = "../traversal"
        elif change == "receipt":
            data["binding"]["receipts"][0] = '{"padding":"' + "x" * 65536 + '"}'
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if change == "duplicate":
            raw = '{"schema":1,"schema":2}'
        elif change == "nonfinite":
            raw = '{"x":NaN}'
        elif change == "deep":
            raw = '{"x":' + "[" * 33 + "0" + "]" * 33 + "}"
        elif change == "oversized":
            db.execute("PRAGMA ignore_check_constraints=ON")
            raw = " " * (4 * 1024 * 1024 + 1)
        digest = "0" * 64 if change == "digest" else hashlib.sha256(raw.encode()).hexdigest()
        db.execute(
            "UPDATE candidate_verification_jobs SET metadata_json=?,metadata_sha256=?",
            (raw, digest),
        )
    with pytest.raises(AgentSyncError) as exc:
        CandidateVerificationJobs(prepared[0]).get(**owner(prepared), job_id=job["id"])
    assert exc.value.code == "corrupt_candidate_queue"
    assert "private-secret-sentinel" not in str(exc.value)


@pytest.mark.parametrize("change", ["unknown", "id", "digest"])
def test_historical_response_corruption_is_not_repaired(prepared, change):
    enqueue(prepared)
    with connect(prepared[0].db_path) as db:
        raw = db.execute("SELECT response_json FROM candidate_verification_requests").fetchone()[0]
        data = json.loads(raw)
        if change == "unknown":
            data["private-data"] = "secret-sentinel"
        elif change == "id":
            data["id"] = "different-job"
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = "0" * 64 if change == "digest" else hashlib.sha256(raw.encode()).hexdigest()
        db.execute(
            "UPDATE candidate_verification_requests SET response_json=?,response_sha256=?",
            (raw, digest),
        )
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared)
    assert exc.value.code == "corrupt_candidate_queue"
    assert counts(prepared) == (1, 1)


def test_cancel_versions_and_different_request_state(prepared):
    job = enqueue(prepared)
    with pytest.raises(AgentSyncError) as exc:
        cancel(prepared, job, expected_version=2)
    assert exc.value.code == "version_conflict"
    cancelled = cancel(prepared, job)
    with pytest.raises(AgentSyncError) as exc:
        cancel(prepared, cancelled, request_id="another-cancel")
    assert exc.value.code == "invalid_state"
    assert cancel(prepared, job) == cancelled


@pytest.mark.parametrize(
    "clock", [float("nan"), float("inf"), -1.0], ids=["nan", "inf", "backward"]
)
def test_invalid_or_regressed_clock_cannot_cancel(prepared, monkeypatch, clock):
    job = enqueue(prepared)
    monkeypatch.setattr(module.time, "time", lambda: clock)
    with pytest.raises(AgentSyncError) as exc:
        cancel(prepared, job)
    assert exc.value.code == ("clock_regressed" if clock == -1.0 else "invalid_clock")
    assert counts(prepared) == (1, 1)


@pytest.mark.parametrize("change", ["task", "owner", "receipt"])
def test_real_second_connection_race_rejects_enqueue(prepared, monkeypatch, change):
    original = module.OwnerCandidateExporter.export

    def raced(self, **kwargs):
        result = original(self, **kwargs)
        with connect(prepared[0].db_path) as db:
            if change == "task":
                db.execute(
                    "UPDATE tasks SET version=version+1 WHERE id=?", (result.binding.left_task_id,)
                )
            elif change == "owner":
                db.execute("UPDATE projects SET admin_hash=?", ("0" * 64,))
            else:
                raw = json.loads(db.execute("SELECT receipt FROM merge_candidates").fetchone()[0])
                raw["fault_injected_metadata"] = True
                db.execute("UPDATE merge_candidates SET receipt=?", (json.dumps(raw),))
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", raced)
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared)
    assert exc.value.code == ("unauthorized" if change == "owner" else "stale_candidate_input")
    assert counts(prepared) == (0, 0)
    with connect(prepared[0].db_path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE operation='candidate_verification_enqueue' AND outcome='success'"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize("different", [False, True], ids=["same-payload", "different-payload"])
def test_concurrent_requests_have_one_committed_resource(prepared, monkeypatch, different):
    original = module.OwnerCandidateExporter.export
    barrier = threading.Barrier(2)

    def synchronized(self, **kwargs):
        result = original(self, **kwargs)
        barrier.wait(timeout=30)
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", synchronized)

    def invoke(index):
        try:
            return enqueue(prepared, profile=profile(False) if different and index else profile())
        except AgentSyncError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, (0, 1)))
    assert counts(prepared) == (1, 1)
    if different:
        assert sum(isinstance(result, dict) for result in results) == 1
        assert "idempotency_conflict" in results
    else:
        assert results[0] == results[1]


def test_success_audit_failure_rolls_back_all_mutation_rows(prepared, monkeypatch):
    core = prepared[0]
    original = core._audit_event

    def injected(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("fault-injected after audit insertion")

    monkeypatch.setattr(core, "_audit_event", injected)
    with pytest.raises(AgentSyncError) as exc:
        enqueue(prepared)
    assert exc.value.code == "storage_error" and counts(prepared) == (0, 0)
    with connect(core.db_path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE operation='candidate_verification_enqueue' AND outcome='success'"
            ).fetchone()[0]
            == 0
        )


def test_process_crash_before_commit_leaves_no_partial_queue(prepared):
    program = """import json, os, sys
from agentsync.core.service import Core
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
p=json.load(sys.stdin)
core=Core(p['data_dir'])
original=core._audit_event
def injected(*args, **kwargs):
 original(*args, **kwargs)
 os._exit(83)
core._audit_event=injected
CandidateVerificationJobs(core).enqueue(**p['args'],profile=DockerProfile('sha256:'+'b'*64,(JsonCase(None,True),)),request_id='crash')
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps({"data_dir": str(prepared[0].data_dir), "args": prepared[1]}).encode(),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 83
    assert counts(prepared) == (0, 0)
    with connect(prepared[0].db_path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE operation='candidate_verification_enqueue' AND outcome='success'"
            ).fetchone()[0]
            == 0
        )


def test_restart_persistence_safe_projection_and_old_claim_rejection(prepared):
    result = enqueue(prepared, profile=profile("private-expectation-sentinel"))
    service = CandidateVerificationJobs(Core(prepared[0].data_dir))
    assert service.get(**owner(prepared), job_id=result["id"])["status"] == "queued"
    assert service.list(**owner(prepared), limit=1)["jobs"][0]["id"] == result["id"]
    with connect(prepared[0].db_path) as db:
        assert "private-expectation-sentinel" not in "\n".join(db.iterdump())
    assert all(
        word not in json.dumps(result)
        for word in (
            'receipt"',
            "creator_session",
            "admin_token",
            "managed-git",
            "private-expectation",
        )
    )
    with pytest.raises(AgentSyncError) as exc:
        VerificationJobs(prepared[0]).claim(
            project_id=owner(prepared)["project_id"], job_id=result["id"], expected_version=1
        )
    assert exc.value.code == "not_found"


def test_composite_foreign_key_rejects_cross_project_candidate(prepared, tmp_path):
    enqueue(prepared)
    root = tmp_path / "other-project"
    root.mkdir()
    other = prepared[0].execute("create_project", {"name": "other", "root_path": str(root)})
    with connect(prepared[0].db_path) as db:
        row = dict(db.execute("SELECT * FROM candidate_verification_jobs").fetchone())
        row.update(id="cross-project-row", project_id=other["project_id"])
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO candidate_verification_jobs("
                + ",".join(row)
                + ") VALUES("
                + ",".join("?" for _ in row)
                + ")",
                tuple(row.values()),
            )
    assert counts(prepared) == (1, 1)

"""Real isolated Git/SQLite owner reservations; no execution or worker token."""

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
from test_candidate_jobs import enqueue, owner, profile

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import candidate_claims as module
from agentsync.verification import candidate_jobs as queue_module
from agentsync.verification import docker
from agentsync.verification.candidate_claims import OwnerCandidateClaims
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.executor import OwnerVerificationExecutor


def claim(prepared, job=None, **extra):
    job = job or enqueue(prepared)
    return OwnerCandidateClaims(prepared[0]).claim_once(
        **(
            owner(prepared)
            | {"job_id": job["id"], "expected_version": 1, "profile": profile()}
            | extra
        )
    )


def recover(prepared, receipt, **extra):
    return OwnerCandidateClaims(prepared[0]).recover_interrupted(
        **(
            owner(prepared)
            | {"job_id": receipt["job"]["id"], "expected_version": 2, "request_id": "recover"}
            | extra
        )
    )


def counts(prepared):
    with connect(prepared[0].db_path) as db:
        return tuple(
            db.execute("SELECT count(*) FROM " + table).fetchone()[0]
            for table in ("candidate_verification_claims", "candidate_claim_recoveries")
        )


def save_claim(prepared, name, enqueue_receipt, claim_receipt, recovery_receipt=None):
    directory = os.environ.get("AGENTSYNC_CANDIDATE_CLAIM_EVIDENCE_DIR")
    if not directory:
        return
    job_id = claim_receipt["job"]["id"]
    with connect(prepared[0].db_path) as db:
        job = dict(
            db.execute("SELECT * FROM candidate_verification_jobs WHERE id=?", (job_id,)).fetchone()
        )
        stored = dict(
            db.execute(
                "SELECT * FROM candidate_verification_claims WHERE job_id=?", (job_id,)
            ).fetchone()
        )
        recoveries = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM candidate_claim_recoveries WHERE job_id=?", (job_id,)
            )
        ]
    environment = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
    target = Path(directory) / environment
    assert target.is_absolute()
    target.mkdir(parents=True, exist_ok=True)
    data = {
        "environment_id": environment,
        "actual_git_object_export": True,
        "execution_verified": False,
        "real_clients_verified": False,
        "worker_credential_issued": False,
        "cleanup_performed": False,
        "queue_row": job,
        "claim_row": stored,
        "recovery_rows": recoveries,
        "enqueue_receipt": enqueue_receipt,
        "claim_receipt": claim_receipt,
        "recovery_receipt": recovery_receipt,
        "current_view": OwnerCandidateClaims(prepared[0]).get(**owner(prepared), job_id=job_id),
        "expected_candidate_source_sha256": hashlib.sha256(
            b"def solve(x): return 'candidate'\n"
        ).hexdigest(),
    }
    (target / (name + ".json")).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def forbid_execution(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Owner reservations must never invoke Docker or an executor")

    monkeypatch.setattr(docker, "verify_python_json_lines", forbidden)
    monkeypatch.setattr(OwnerVerificationExecutor, "execute_once", forbidden)


def test_owner_claims_fresh_candidate_once(prepared, monkeypatch):
    forbid_execution(monkeypatch)
    job = enqueue(prepared)
    service = OwnerCandidateClaims(prepared[0])
    receipt = service.claim_once(
        **owner(prepared), job_id=job["id"], expected_version=1, profile=profile()
    )
    assert receipt["job"]["candidate_sha"] == prepared[1]["expected_candidate_sha"]
    assert receipt["job"]["status"] == "claimed" and receipt["job"]["version"] == 2
    assert receipt["current_state"] is False and receipt["receipt_kind"] == "historical_claim"
    assert receipt["reservation"]["kind"] == "owner_reservation_v1"
    assert service.get(**owner(prepared), job_id=job["id"])["reservation"]["lease_expired"] is False
    save_claim(prepared, "actual-owner-reservation", job, receipt)


def test_owner_recovery_is_terminal_and_has_historical_receipt(prepared, monkeypatch):
    forbid_execution(monkeypatch)
    job = enqueue(prepared)
    service = OwnerCandidateClaims(prepared[0])
    reserved = service.claim_once(
        **owner(prepared), job_id=job["id"], expected_version=1, profile=profile()
    )
    response = service.recover_interrupted(
        **owner(prepared), job_id=job["id"], expected_version=2, request_id="recover"
    )
    assert response["job"]["status"] == "interrupted" and response["job"]["version"] == 3
    assert response["receipt_kind"] == "historical_recovery"
    assert response["reservation"]["reason_code"] == "owner_interrupted"
    assert (
        service.recover_interrupted(
            **owner(prepared), job_id=job["id"], expected_version=2, request_id="recover"
        )
        == response
    )
    save_claim(prepared, "actual-owner-recovery", job, reserved, response)


def test_unreserved_and_old_cancelled_get_have_no_claim(prepared):
    job = enqueue(prepared)
    service = OwnerCandidateClaims(prepared[0])
    assert service.get(**owner(prepared), job_id=job["id"])["reservation"] is None
    queue = CandidateVerificationJobs(prepared[0])
    cancelled = queue.cancel(
        **owner(prepared), job_id=job["id"], expected_version=1, request_id="cancel"
    )
    assert service.get(**owner(prepared), job_id=job["id"])["reservation"] is None
    assert (
        queue.cancel(**owner(prepared), job_id=job["id"], expected_version=1, request_id="cancel")
        == cancelled
    )
    with pytest.raises(AgentSyncError):
        claim(prepared, job)
    assert counts(prepared) == (0, 0)


@pytest.mark.parametrize(
    "change,code",
    [("owner", "unauthorized"), ("version", "version_conflict"), ("profile", "profile_mismatch")],
)
def test_owner_version_and_profile_rejected_before_git(prepared, monkeypatch, change, code):
    job = enqueue(prepared)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected reservation must not start Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    extra = (
        {"admin_token": "private-sentinel"}
        if change == "owner"
        else {"expected_version": 2}
        if change == "version"
        else {"profile": profile(False)}
    )
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job, **extra)
    assert exc.value.code == code and counts(prepared) == (0, 0)
    assert "private-sentinel" not in str(exc.value)


def test_valid_foreign_project_owner_cannot_claim_before_git(prepared, monkeypatch, tmp_path):
    job = enqueue(prepared)
    other_root = tmp_path / "other-owner-root"
    other_root.mkdir()
    foreign = prepared[0].execute(
        "create_project", {"name": "foreign", "root_path": str(other_root)}
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Foreign-project lookup must reject before Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job, **foreign)
    assert exc.value.code == "not_found" and counts(prepared) == (0, 0)


@pytest.mark.parametrize("seconds", [0, 3601, True], ids=["zero", "long", "boolean"])
def test_strict_reservation_interval(prepared, seconds):
    job = enqueue(prepared)
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job, lease_seconds=seconds)
    assert exc.value.code == "validation_error" and counts(prepared) == (0, 0)


@pytest.mark.parametrize(
    "clock,code",
    [
        (float("nan"), "invalid_clock"),
        (10**400, "invalid_clock"),
        (1e20, "invalid_reservation_deadline"),
    ],
    ids=["nonfinite", "overflow-integer", "precision-loss"],
)
def test_clock_and_deadline_errors_are_bounded(prepared, monkeypatch, clock, code):
    job = enqueue(prepared)
    monkeypatch.setattr(queue_module.time, "time", lambda: clock)
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job)
    assert exc.value.code == code and counts(prepared) == (0, 0)


@pytest.mark.parametrize("offset,expired", [(-0.1, False), (0.0, True), (0.1, True)])
def test_expiry_read_boundary_never_changes_claim(prepared, monkeypatch, offset, expired):
    receipt = claim(prepared, lease_seconds=1)
    monkeypatch.setattr(
        queue_module.time, "time", lambda: receipt["reservation"]["lease_expires_at"] + offset
    )
    service = OwnerCandidateClaims(Core(prepared[0].data_dir))
    view = service.get(**owner(prepared), job_id=receipt["job"]["id"])
    assert view["job"]["status"] == "claimed" and view["job"]["version"] == 2
    assert view["reservation"]["lease_expired"] is expired
    assert counts(prepared) == (1, 0)


@pytest.mark.parametrize("clock_kind", ["expired", "regressed"])
def test_explicit_recovery_can_handle_expiry_and_clock_rollback(prepared, monkeypatch, clock_kind):
    reserved = claim(prepared, lease_seconds=1)
    now = (
        reserved["reservation"]["lease_expires_at"] + 1
        if clock_kind == "expired"
        else reserved["reservation"]["created_at"] - 1
    )
    monkeypatch.setattr(queue_module.time, "time", lambda: now)
    before = OwnerCandidateClaims(prepared[0]).get(**owner(prepared), job_id=reserved["job"]["id"])
    if clock_kind == "regressed":
        assert (
            before["reservation"]["clock_regressed"] is True
            and before["reservation"]["lease_expired"] is None
        )
    response = recover(prepared, reserved)
    assert response["job"]["status"] == "interrupted"
    assert response["reservation"]["proof_sha256"] == reserved["reservation"]["proof_sha256"]
    assert response["reservation"]["updated_at"] >= reserved["reservation"]["created_at"]


def test_one_reservation_forever_and_no_unused_secret(prepared):
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    with pytest.raises(AgentSyncError):
        claim(prepared, job)
    with pytest.raises(AgentSyncError) as exc:
        CandidateVerificationJobs(prepared[0]).cancel(
            **owner(prepared), job_id=job["id"], expected_version=2, request_id="claimed-cancel"
        )
    assert exc.value.code == "owner_recovery_required" and counts(prepared) == (1, 0)
    recover(prepared, reserved)
    with pytest.raises(AgentSyncError):
        claim(prepared, job, expected_version=3)
    with connect(prepared[0].db_path) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(candidate_verification_claims)")]
    assert not any("token" in key or "secret" in key for key in columns)
    assert "lease_token" not in json.dumps(reserved) and counts(prepared) == (1, 1)


def test_recovery_request_conflict_and_terminal_state(prepared):
    reserved = claim(prepared)
    original = recover(prepared, reserved)
    with pytest.raises(AgentSyncError) as exc:
        recover(prepared, reserved, expected_version=3)
    assert exc.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError) as exc:
        recover(prepared, reserved, expected_version=3, request_id="different")
    assert exc.value.code == "invalid_state"
    assert recover(prepared, reserved) == original


@pytest.mark.parametrize("change", ["task", "owner", "receipt"])
def test_second_connection_changes_after_export_are_rejected(prepared, monkeypatch, change):
    job = enqueue(prepared)
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
                data = json.loads(db.execute("SELECT receipt FROM merge_candidates").fetchone()[0])
                data["fault_injected_change"] = True
                db.execute("UPDATE merge_candidates SET receipt=?", (json.dumps(data),))
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", raced)
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job)
    assert exc.value.code == ("unauthorized" if change == "owner" else "stale_candidate_input")
    assert counts(prepared) == (0, 0)


@pytest.mark.parametrize("change", ["dirty", "missing"])
def test_invalid_disk_input_cannot_be_reserved(prepared, change):
    job = enqueue(prepared)
    if change == "dirty":
        Path(prepared[4]["candidate_path"], "dirty.txt").write_text("fixture mutation\n")
    else:
        root = prepared[0].data_dir / "managed-git"
        root.rename(root.with_name("unavailable-managed-git"))
    with pytest.raises(AgentSyncError):
        claim(prepared, job)
    assert counts(prepared) == (0, 0)


def test_same_version_concurrent_claims_create_one_reservation(prepared, monkeypatch):
    job = enqueue(prepared)
    original = module.OwnerCandidateExporter.export
    barrier = threading.Barrier(2)

    def synchronized(self, **kwargs):
        result = original(self, **kwargs)
        barrier.wait(timeout=30)
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", synchronized)

    def invoke(_):
        try:
            return claim(prepared, job)
        except AgentSyncError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(invoke, range(2)))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert "version_conflict" in values and counts(prepared) == (1, 0)


def test_queued_cancel_winning_during_export_prevents_claim(prepared, monkeypatch):
    job = enqueue(prepared)
    original = module.OwnerCandidateExporter.export

    def cancel_during_export(self, **kwargs):
        result = original(self, **kwargs)
        CandidateVerificationJobs(prepared[0]).cancel(
            **owner(prepared), job_id=job["id"], expected_version=1, request_id="race-cancel"
        )
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", cancel_during_export)
    with pytest.raises(AgentSyncError) as exc:
        claim(prepared, job)
    assert exc.value.code == "version_conflict" and counts(prepared) == (0, 0)


def test_old_enqueue_replay_and_reads_are_db_only_after_claim_recovery(prepared, monkeypatch):
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    assert enqueue(prepared) == job
    root = prepared[0].data_dir / "managed-git"
    root.rename(root.with_name("unavailable-managed-git"))

    def forbidden(*args, **kwargs):
        pytest.fail("Claim get/recovery/history are DB-only")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    recovered = recover(prepared, reserved)
    assert enqueue(prepared) == job and recover(prepared, reserved) == recovered
    queue = CandidateVerificationJobs(prepared[0])
    assert queue.get(**owner(prepared), job_id=job["id"])["status"] == "interrupted"
    assert queue.list(**owner(prepared))["jobs"][0]["version"] == 3


@pytest.mark.parametrize("operation", ["claim", "recover"])
def test_audit_failure_rolls_back_entire_transition(prepared, monkeypatch, operation):
    job = enqueue(prepared)
    reserved = claim(prepared, job) if operation == "recover" else None
    original = prepared[0]._audit_event

    def injected(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("fault-injected audit failure")

    monkeypatch.setattr(prepared[0], "_audit_event", injected)
    with pytest.raises(AgentSyncError) as exc:
        recover(prepared, reserved) if reserved else claim(prepared, job)
    assert exc.value.code == "storage_error"
    assert counts(prepared) == ((1, 0) if operation == "recover" else (0, 0))


def test_process_exit_before_commit_rolls_back_reservation(prepared):
    job = enqueue(prepared)
    program = """import json, os, sys
from agentsync.core.service import Core
from agentsync.verification.candidate_claims import OwnerCandidateClaims
from agentsync.verification.docker import DockerProfile, JsonCase
p=json.load(sys.stdin)
core=Core(p['data_dir'])
original=core._audit_event
def injected(*args, **kwargs):
 original(*args, **kwargs)
 os._exit(84)
core._audit_event=injected
OwnerCandidateClaims(core).claim_once(**p['owner'],job_id=p['job_id'],expected_version=1,profile=DockerProfile('sha256:'+'b'*64,(JsonCase(None,True),)))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps(
            {"data_dir": str(prepared[0].data_dir), "owner": owner(prepared), "job_id": job["id"]}
        ).encode(),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 84 and counts(prepared) == (0, 0)
    assert (
        CandidateVerificationJobs(prepared[0]).get(**owner(prepared), job_id=job["id"])["status"]
        == "queued"
    )


@pytest.mark.parametrize(
    "column,value", [("profile_sha256", "c" * 64), ("metadata_sha256", "c" * 64)]
)
def test_claim_pin_corruption_rejected_by_all_queue_reads(prepared, column, value):
    reserved = claim(prepared)
    with connect(prepared[0].db_path) as db:
        db.execute(f"UPDATE candidate_verification_claims SET {column}=?", (value,))
    queue = CandidateVerificationJobs(prepared[0])
    for action in (
        lambda: queue.get(**owner(prepared), job_id=reserved["job"]["id"]),
        lambda: queue.list(**owner(prepared)),
        lambda: enqueue(prepared),
        lambda: recover(prepared, reserved),
    ):
        with pytest.raises(AgentSyncError):
            action()


def test_recovery_response_corruption_blocks_bidirectional_reads(prepared):
    reserved = claim(prepared)
    recover(prepared, reserved)
    with connect(prepared[0].db_path) as db:
        data = json.loads(
            db.execute("SELECT response_json FROM candidate_claim_recoveries").fetchone()[0]
        )
        data["reservation"]["reason_code"] = "fabricated-cleanup"
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        db.execute(
            "UPDATE candidate_claim_recoveries SET response_json=?,response_sha256=?",
            (raw, hashlib.sha256(raw.encode()).hexdigest()),
        )
    with pytest.raises(AgentSyncError):
        OwnerCandidateClaims(prepared[0]).get(**owner(prepared), job_id=reserved["job"]["id"])

"""Real disposable Git/SQLite intent seams; controlled faults are labelled."""

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
from test_candidate_claims import claim, forbid_execution, recover
from test_candidate_claims import prepared as prepared
from test_candidate_claims import world as world
from test_candidate_jobs import enqueue, owner, profile

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import candidate_intents as module
from agentsync.verification import candidate_jobs as queue_module
from agentsync.verification.candidate_claims import OwnerCandidateClaims
from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents
from agentsync.verification.candidate_jobs import CandidateVerificationJobs


def test_prepare_preserves_claim_and_does_not_execute(prepared):
    reserved = claim(prepared)
    service = OwnerCandidateExecutionIntents(prepared[0])
    result = service.prepare_once(
        **owner(prepared), job_id=reserved["job"]["id"], expected_version=2, profile=profile()
    )
    assert result["receipt_kind"] == "historical_prepare"
    assert result["intent"]["status"] == "prepared"
    assert result["intent"]["revision"] == 1
    assert result["execution_connected"] is False
    assert service.get(**owner(prepared), job_id=reserved["job"]["id"])["job"] == reserved[
        "job"
    ] | {"current_state": True}


def prepare(prepared, reserved=None, **extra):
    reserved = reserved or claim(prepared)
    return OwnerCandidateExecutionIntents(prepared[0]).prepare_once(
        **(
            owner(prepared)
            | {"job_id": reserved["job"]["id"], "expected_version": 2, "profile": profile()}
            | extra
        )
    )


def abandon(prepared, receipt, **extra):
    return OwnerCandidateExecutionIntents(prepared[0]).abandon_once(
        **(
            owner(prepared)
            | {
                "job_id": receipt["intent"]["job_id"],
                "intent_id": receipt["intent"]["id"],
                "expected_revision": 1,
                "request_id": "abandon",
            }
            | extra
        )
    )


def test_prepared_intent_fences_recovery_until_explicit_abandon(prepared):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved)
    with pytest.raises(AgentSyncError) as exc:
        recover(prepared, reserved)
    assert exc.value.code == "execution_intent_active"
    abandoned = abandon(prepared, receipt)
    assert abandoned["intent"]["status"] == "abandoned"
    assert abandoned["intent"]["revision"] == 2
    assert abandoned["intent"]["proof_sha256"] == receipt["intent"]["proof_sha256"]
    assert recover(prepared, reserved)["job"]["status"] == "interrupted"
    assert abandon(prepared, receipt) == abandoned
    with pytest.raises(AgentSyncError):
        prepare(prepared, reserved, expected_version=3)


@pytest.mark.parametrize(
    "change,code",
    [("owner", "unauthorized"), ("version", "version_conflict"), ("profile", "profile_mismatch")],
)
def test_invalid_owner_version_profile_rejected_before_git(prepared, monkeypatch, change, code):
    reserved = claim(prepared)

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected preparation must not start Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    extra = (
        {"admin_token": "secret-sentinel"}
        if change == "owner"
        else {"expected_version": 3}
        if change == "version"
        else {"profile": profile(False)}
    )
    with pytest.raises(AgentSyncError) as exc:
        prepare(prepared, reserved, **extra)
    assert exc.value.code == code and "secret-sentinel" not in str(exc.value)


@pytest.mark.parametrize(
    "clock,code",
    [
        ("expired", "reservation_expired"),
        ("regressed", "clock_regressed"),
        ("nonfinite", "invalid_clock"),
    ],
)
def test_controlled_clock_rejects_prepare_before_git(prepared, monkeypatch, clock, code):
    reserved = claim(prepared)
    now = (
        reserved["reservation"]["lease_expires_at"]
        if clock == "expired"
        else reserved["reservation"]["created_at"] - 1
        if clock == "regressed"
        else float("nan")
    )
    monkeypatch.setattr(queue_module.time, "time", lambda: now)

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid clock must reject before Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(AgentSyncError) as exc:
        prepare(prepared, reserved)
    assert exc.value.code == code


@pytest.mark.parametrize("change", ["task", "owner", "receipt", "content"])
def test_controlled_post_export_changes_reject_prepare(prepared, monkeypatch, change):
    reserved = claim(prepared)
    original = module.OwnerCandidateExporter.export

    def raced(self, **kwargs):
        result = original(self, **kwargs)
        if change == "content":
            Path(prepared[4]["candidate_path"], "dirty.txt").write_text(
                "controlled fixture mutation\n"
            )
        else:
            with connect(prepared[0].db_path) as db:
                if change == "task":
                    db.execute(
                        "UPDATE tasks SET version=version+1 WHERE id=?",
                        (result.binding.left_task_id,),
                    )
                elif change == "owner":
                    db.execute("UPDATE projects SET admin_hash=?", ("0" * 64,))
                else:
                    value = json.loads(
                        db.execute("SELECT receipt FROM merge_candidates").fetchone()[0]
                    )
                    value["controlled_fault"] = True
                    db.execute("UPDATE merge_candidates SET receipt=?", (json.dumps(value),))
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", raced)
    with pytest.raises(AgentSyncError):
        prepare(prepared, reserved)


@pytest.mark.parametrize("change", ["dirty", "missing"])
def test_invalid_managed_git_prevents_intent(prepared, change):
    reserved = claim(prepared)
    if change == "dirty":
        Path(prepared[4]["candidate_path"], "dirty.txt").write_text("fixture mutation\n")
    else:
        root = prepared[0].data_dir / "managed-git"
        root.rename(root.with_name("unavailable-managed-git"))
    with pytest.raises(AgentSyncError):
        prepare(prepared, reserved)


def test_two_preparers_create_one_intent(prepared, monkeypatch):
    reserved = claim(prepared)
    original = module.OwnerCandidateExporter.export
    barrier = threading.Barrier(2)

    def synchronized(self, **kwargs):
        result = original(self, **kwargs)
        barrier.wait(timeout=30)
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", synchronized)

    def invoke(_):
        try:
            return prepare(prepared, reserved)
        except AgentSyncError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(invoke, range(2)))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert "execution_intent_exists" in values


def test_recovery_winning_during_export_prevents_intent(prepared, monkeypatch):
    reserved = claim(prepared)
    original = module.OwnerCandidateExporter.export

    def raced(self, **kwargs):
        result = original(self, **kwargs)
        recover(prepared, reserved)
        return result

    monkeypatch.setattr(module.OwnerCandidateExporter, "export", raced)
    with pytest.raises(AgentSyncError) as exc:
        prepare(prepared, reserved)
    assert exc.value.code == "version_conflict"


@pytest.mark.parametrize("clock_kind", ["expired", "regressed"])
def test_explicit_abandon_then_recovery_uses_intent_anchor(prepared, monkeypatch, clock_kind):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved)
    now = (
        receipt["intent"]["claim_lease_expires_at"] + 2
        if clock_kind == "expired"
        else receipt["intent"]["created_at"] - 2
    )
    monkeypatch.setattr(queue_module.time, "time", lambda: now)
    before = OwnerCandidateExecutionIntents(prepared[0]).get(
        **owner(prepared), job_id=reserved["job"]["id"]
    )
    assert before["intent"]["lease_expired"] is (True if clock_kind == "expired" else None)
    response = abandon(prepared, receipt)
    recovered = recover(prepared, reserved)
    assert response["intent"]["updated_at"] >= receipt["intent"]["created_at"]
    assert recovered["reservation"]["updated_at"] >= response["intent"]["updated_at"]


def test_abandon_is_terminal_and_request_conflicts(prepared):
    receipt = prepare(prepared)
    response = abandon(prepared, receipt)
    with pytest.raises(AgentSyncError) as exc:
        abandon(prepared, receipt, expected_revision=2)
    assert exc.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError):
        abandon(prepared, receipt, expected_revision=2, request_id="different")
    assert abandon(prepared, receipt) == response
    with pytest.raises(AgentSyncError):
        prepare(prepared, {"job": {"id": receipt["intent"]["job_id"]}})


def test_restart_and_db_only_histories_preserve_original_receipts(prepared, monkeypatch):
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    receipt = prepare(prepared, reserved)
    root = prepared[0].data_dir / "managed-git"
    root.rename(root.with_name("unavailable-managed-git"))

    def forbidden(*args, **kwargs):
        pytest.fail("Ledger views and history must remain DB-only")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    service = OwnerCandidateExecutionIntents(Core(prepared[0].data_dir))
    assert service.get(**owner(prepared), job_id=job["id"])["intent"]["status"] == "prepared"
    response = abandon(prepared, receipt)
    recovered = recover(prepared, reserved)
    assert (
        abandon(prepared, receipt) == response
        and recover(prepared, reserved) == recovered
        and enqueue(prepared) == job
    )
    assert service.get(**owner(prepared), job_id=job["id"])["job"]["status"] == "interrupted"


@pytest.mark.parametrize("operation", ["prepare", "abandon"])
def test_controlled_audit_failure_rolls_back_intent_transition(prepared, monkeypatch, operation):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved) if operation == "abandon" else None
    original = prepared[0]._audit_event

    def injected(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("controlled audit failure")

    monkeypatch.setattr(prepared[0], "_audit_event", injected)
    with pytest.raises(AgentSyncError) as exc:
        abandon(prepared, receipt) if receipt else prepare(prepared, reserved)
    assert exc.value.code == "storage_error"
    view = OwnerCandidateExecutionIntents(prepared[0]).get(
        **owner(prepared), job_id=reserved["job"]["id"]
    )
    assert (
        view["intent"] is None if operation == "prepare" else view["intent"]["status"] == "prepared"
    )


@pytest.mark.parametrize(
    "column,value",
    [
        ("proof_sha256", "c" * 64),
        ("profile_sha256", "c" * 64),
        ("claim_lease_expires_at", 9e20),
        ("revision", 2),
        ("status", "abandoned"),
    ],
)
def test_controlled_intent_corruption_rejected_across_public_readers(prepared, column, value):
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    receipt = prepare(prepared, reserved)
    with connect(prepared[0].db_path) as db:
        db.execute(f"UPDATE candidate_execution_intents SET {column}=?", (value,))
    queue = CandidateVerificationJobs(prepared[0])
    claims = OwnerCandidateClaims(prepared[0])
    intents = OwnerCandidateExecutionIntents(prepared[0])
    for action in (
        lambda: queue.get(**owner(prepared), job_id=job["id"]),
        lambda: queue.list(**owner(prepared)),
        lambda: enqueue(prepared),
        lambda: claims.get(**owner(prepared), job_id=job["id"]),
        lambda: recover(prepared, reserved),
        lambda: intents.get(**owner(prepared), job_id=job["id"]),
        lambda: abandon(prepared, receipt),
    ):
        with pytest.raises(AgentSyncError):
            action()


def test_controlled_abandon_receipt_corruption_blocks_all_reads(prepared):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved)
    abandon(prepared, receipt)
    with connect(prepared[0].db_path) as db:
        response = json.loads(
            db.execute("SELECT response_json FROM candidate_intent_abandonments").fetchone()[0]
        )
        response["reason_code"] = "invented-cleanup"
        raw = json.dumps(response, sort_keys=True, separators=(",", ":"))
        db.execute(
            "UPDATE candidate_intent_abandonments SET response_json=?,response_sha256=?",
            (raw, hashlib.sha256(raw.encode()).hexdigest()),
        )
    with pytest.raises(AgentSyncError):
        recover(prepared, reserved)
    with pytest.raises(AgentSyncError):
        OwnerCandidateExecutionIntents(prepared[0]).get(
            **owner(prepared), job_id=reserved["job"]["id"]
        )


def save_intent(prepared, name, job, reserved, receipt, abandoned=None, recovered=None):
    directory = os.environ.get("AGENTSYNC_CANDIDATE_INTENT_EVIDENCE_DIR")
    if not directory:
        return
    job_id = job["id"]
    with connect(prepared[0].db_path) as db:
        rows = {
            key: dict(
                db.execute(
                    "SELECT * FROM " + table + " WHERE " + column + "=?", (job_id,)
                ).fetchone()
            )
            for key, table, column in (
                ("queue_row", "candidate_verification_jobs", "id"),
                ("claim_row", "candidate_verification_claims", "job_id"),
                ("intent_row", "candidate_execution_intents", "job_id"),
            )
        }
        rows["abandonment_rows"] = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM candidate_intent_abandonments WHERE job_id=?", (job_id,)
            )
        ]
        rows["recovery_rows"] = [
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
        **rows,
        "environment_id": environment,
        "actual_git_object_export": True,
        "execution_verified": False,
        "real_clients_verified": False,
        "worker_credential_issued": False,
        "cleanup_performed": False,
        "enqueue_receipt": job,
        "claim_receipt": reserved,
        "prepare_receipt": receipt,
        "abandon_receipt": abandoned,
        "recovery_receipt": recovered,
        "current_view": OwnerCandidateExecutionIntents(prepared[0]).get(
            **owner(prepared), job_id=job_id
        ),
        "current_claim_view": OwnerCandidateClaims(prepared[0]).get(
            **owner(prepared), job_id=job_id
        ),
        "expected_candidate_source_sha256": hashlib.sha256(
            b"def solve(x): return 'candidate'\n"
        ).hexdigest(),
    }
    (target / (name + ".json")).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )


def test_actual_prepared_observation_never_executes(prepared, monkeypatch):
    forbid_execution(monkeypatch)
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    receipt = prepare(prepared, reserved)
    assert receipt["intent"]["candidate_sha"] == prepared[1]["expected_candidate_sha"]
    assert receipt["intent"]["claim_proof_sha256"] == reserved["reservation"]["proof_sha256"]
    assert "clock_regressed" not in receipt["intent"] and "lease_expired" not in receipt["intent"]
    save_intent(prepared, "actual-owner-prepared-intent", job, reserved, receipt)


def test_actual_abandoned_recovered_observation_never_executes(prepared, monkeypatch):
    forbid_execution(monkeypatch)
    job = enqueue(prepared)
    reserved = claim(prepared, job)
    receipt = prepare(prepared, reserved)
    response = abandon(prepared, receipt)
    recovered = recover(prepared, reserved)
    assert response["intent"]["proof_sha256"] == receipt["intent"]["proof_sha256"]
    assert response == abandon(prepared, receipt)
    save_intent(
        prepared,
        "actual-owner-abandoned-recovered-intent",
        job,
        reserved,
        receipt,
        response,
        recovered,
    )


def test_valid_foreign_owner_cannot_prepare(prepared, monkeypatch, tmp_path):
    reserved = claim(prepared)
    root = tmp_path / "foreign-root"
    root.mkdir()
    foreign = prepared[0].execute("create_project", {"name": "foreign", "root_path": str(root)})

    def forbidden(*args, **kwargs):
        pytest.fail("Foreign project must reject before Git")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with pytest.raises(AgentSyncError) as exc:
        prepare(prepared, reserved, **foreign)
    assert exc.value.code == "not_found"


@pytest.mark.parametrize("operation", ["prepare", "abandon"])
def test_controlled_process_exit_before_commit_has_no_partial_transition(prepared, operation):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved) if operation == "abandon" else None
    program = """import json,os,sys
from agentsync.core.service import Core
from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents
from agentsync.verification.docker import DockerProfile,JsonCase
p=json.load(sys.stdin);core=Core(p['data_dir']);original=core._audit_event
def injected(*args,**kwargs):
 original(*args,**kwargs)
 os._exit(85)
core._audit_event=injected
service=OwnerCandidateExecutionIntents(core)
if p['intent_id']:
 service.abandon_once(**p['owner'],job_id=p['job_id'],intent_id=p['intent_id'],expected_revision=1,request_id='exit')
else:
 service.prepare_once(**p['owner'],job_id=p['job_id'],expected_version=2,profile=DockerProfile('sha256:'+'b'*64,(JsonCase(None,True),)))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps(
            {
                "data_dir": str(prepared[0].data_dir),
                "owner": owner(prepared),
                "job_id": reserved["job"]["id"],
                "intent_id": receipt["intent"]["id"] if receipt else None,
            }
        ).encode(),
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 85
    view = OwnerCandidateExecutionIntents(Core(prepared[0].data_dir)).get(
        **owner(prepared), job_id=reserved["job"]["id"]
    )
    assert (
        view["intent"] is None if operation == "prepare" else view["intent"]["status"] == "prepared"
    )


def test_controlled_float_revision_in_abandon_receipt_is_not_integer(prepared):
    reserved = claim(prepared)
    receipt = prepare(prepared, reserved)
    abandon(prepared, receipt)
    with connect(prepared[0].db_path) as db:
        response = json.loads(
            db.execute("SELECT response_json FROM candidate_intent_abandonments").fetchone()[0]
        )
        response["intent"]["revision"] = 2.0
        raw = json.dumps(response, sort_keys=True, separators=(",", ":"))
        db.execute(
            "UPDATE candidate_intent_abandonments SET response_json=?,response_sha256=?",
            (raw, hashlib.sha256(raw.encode()).hexdigest()),
        )
    for action in (
        lambda: OwnerCandidateExecutionIntents(prepared[0]).get(
            **owner(prepared), job_id=reserved["job"]["id"]
        ),
        lambda: CandidateVerificationJobs(prepared[0]).get(
            **owner(prepared), job_id=reserved["job"]["id"]
        ),
        lambda: abandon(prepared, receipt),
        lambda: recover(prepared, reserved),
    ):
        with pytest.raises(AgentSyncError):
            action()


def test_controlled_deadline_crossing_after_capture_prevents_prepare(prepared, monkeypatch):
    reserved = claim(prepared)
    original = module.OwnerCandidateBindings._capture_in_transaction

    def raced(self, db, **kwargs):
        binding = original(self, db, **kwargs)
        monkeypatch.setattr(
            queue_module.time, "time", lambda: reserved["reservation"]["lease_expires_at"]
        )
        return binding

    monkeypatch.setattr(module.OwnerCandidateBindings, "_capture_in_transaction", raced)
    with pytest.raises(AgentSyncError) as exc:
        prepare(prepared, reserved)
    assert exc.value.code == "reservation_expired"
    assert (
        OwnerCandidateExecutionIntents(prepared[0]).get(
            **owner(prepared), job_id=reserved["job"]["id"]
        )["intent"]
        is None
    )

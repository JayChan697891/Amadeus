"""In-memory relation validation; no Git, service credentials or external execution."""

import hashlib
import json
import sqlite3

import pytest

from agentsync.errors import AgentSyncError
from agentsync.storage.database import MIGRATION_V13
from agentsync.verification.candidate_intents import validate_intent


def row(db, values):
    return db.execute(
        "SELECT " + ",".join("? AS " + name for name in values), tuple(values.values())
    ).fetchone()


@pytest.fixture
def records():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    pins = {
        "metadata_sha256": "a" * 64,
        "profile_kind": "json_cases_v1",
        "profile_sha256": "b" * 64,
        "image_id": "sha256:" + "c" * 64,
        "candidate_sha": "d" * 40,
        "tree_sha": "e" * 40,
        "input_sha256": "f" * 64,
        "source_sha256": "1" * 64,
    }
    job = row(db, {"id": "job", "project_id": "project", "status": "claimed", **pins})
    claim = row(
        db,
        {
            "id": "claim",
            "project_id": "project",
            "job_id": "job",
            "created_at": 10.0,
            "lease_expires_at": 50.0,
            **pins,
            "proof_sha256": "2" * 64,
        },
    )
    proof = {
        "schema": "agentsync.candidate-execution-intent.v1",
        "id": "00000000-0000-4000-8000-000000000001",
        "project_id": "project",
        "job_id": "job",
        "claim_id": "claim",
        "kind": "owner_candidate_execution_intent_v1",
        "claim_version": 2,
        "claim_proof_sha256": "2" * 64,
        **pins,
        "created_at": 11.0,
        "claim_lease_expires_at": 50.0,
    }
    intent = {key: value for key, value in proof.items() if key != "schema"}
    encoded = json.dumps(proof, sort_keys=True, separators=(",", ":"))
    intent.update(
        proof_json=encoded,
        proof_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        status="prepared",
        revision=1,
        reason_code="",
        updated_at=11.0,
    )
    # Keep parent relations explicit and unconstrained so corruption tests can
    # introduce invalid links; the execution table uses the current real DDL.
    for table, values in (
        ("candidate_verification_jobs", dict(job)),
        ("candidate_verification_claims", dict(claim)),
    ):
        db.execute("CREATE TABLE " + table + "(" + ",".join(values) + ")")
        db.execute(
            "INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in values) + ")",
            tuple(values.values()),
        )
    columns = ",".join(name for name in intent)
    db.execute("CREATE TABLE candidate_execution_intents(" + columns + ")")
    db.execute("CREATE TABLE candidate_intent_abandonments(job_id,claim_id,intent_id)")
    db.execute(
        "INSERT INTO candidate_execution_intents VALUES(" + ",".join("?" for _ in intent) + ")",
        tuple(intent.values()),
    )
    db.executescript(MIGRATION_V13)
    try:
        yield db, job, claim
    finally:
        db.close()


def test_matching_prepared_relation_is_read_without_changes(records):
    db, job, claim = records
    before = db.total_changes
    assert validate_intent(db, job, claim)["job_id"] == "job"
    assert db.total_changes == before


def test_claim_linked_intent_requires_matching_job(records):
    db, job, claim = records
    original = dict(db.execute("SELECT * FROM candidate_execution_intents").fetchone())
    proof = json.loads(original["proof_json"])
    proof["job_id"] = "other-job"
    encoded = json.dumps(proof, sort_keys=True, separators=(",", ":"))
    db.execute(
        "UPDATE candidate_execution_intents SET job_id=?,proof_json=?,proof_sha256=?",
        ("other-job", encoded, hashlib.sha256(encoded.encode()).hexdigest()),
    )
    with pytest.raises(AgentSyncError, match="Stored candidate queue data") as exc:
        validate_intent(db, job, claim)
    assert exc.value.code == "corrupt_candidate_queue"


@pytest.mark.parametrize(
    "claim_id,intent_id",
    [
        ("claim", "other-intent"),
        ("other-claim", "00000000-0000-4000-8000-000000000001"),
    ],
)
def test_prepared_relation_rejects_linked_abandonment(records, claim_id, intent_id):
    db, job, claim = records
    db.execute(
        "INSERT INTO candidate_intent_abandonments VALUES(?,?,?)",
        ("other-job", claim_id, intent_id),
    )
    with pytest.raises(AgentSyncError) as exc:
        validate_intent(db, job, claim)
    assert exc.value.code == "corrupt_candidate_queue"


def test_unrelated_records_are_not_attached_to_the_requested_job(records):
    db, _, _ = records
    job = row(db, {"id": "other-job", "project_id": "project"})
    claim = row(db, {"id": "other-claim", "project_id": "project", "job_id": "other-job"})
    assert validate_intent(db, job, claim) is None
    assert validate_intent(db, job, None) is None

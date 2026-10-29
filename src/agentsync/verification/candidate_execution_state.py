"""DB-only candidate execution relations; old reservation proofs stay immutable."""

from __future__ import annotations

import math
import re
import sqlite3
import uuid
from typing import Any, NoReturn

from agentsync.verification.candidate_jobs import _dump, _error, _hash, _load, _sha
from agentsync.verification.executor import ISOLATION_CHECKS

PINS = (
    "metadata_sha256",
    "profile_kind",
    "profile_sha256",
    "image_id",
    "candidate_sha",
    "tree_sha",
    "input_sha256",
    "source_sha256",
)
PROOF_FIELDS = {
    "schema",
    "id",
    "project_id",
    "job_id",
    "claim_id",
    "intent_id",
    "claim_proof_sha256",
    "intent_proof_sha256",
    "lease_expires_at",
    "created_at",
    "case_count",
    "cases_sha256",
    "verifier_sha256",
    *PINS,
}


def corrupt() -> NoReturn:
    _error("corrupt_candidate_execution", "Stored candidate execution is inconsistent.")


def passed_evidence(row: sqlite3.Row, proof: dict[str, Any], evidence: dict[str, Any]) -> bool:
    counts = [
        evidence.get(name)
        for name in (
            "expected_case_count",
            "completed_case_count",
            "checked_case_count",
            "passed_case_count",
        )
    ]
    checks = evidence.get("isolation", {}).get("checks", {})
    return bool(
        evidence.get("status") == "passed"
        and evidence.get("execution_id") == row["id"]
        and evidence.get("commit_sha") == proof["candidate_sha"]
        and all(
            evidence.get(key) == proof[key]
            for key in (
                "tree_sha",
                "input_sha256",
                "source_sha256",
                "profile_sha256",
                "cases_sha256",
            )
        )
        and evidence.get("image_sha256") == proof["image_id"]
        and evidence.get("profile_id") == proof["profile_kind"]
        and evidence.get("provenance") == "docker_black_box"
        and evidence.get("backend") == "local-linux-docker"
        and type(evidence.get("verifier_version")) is int
        and evidence["verifier_version"] == 1
        and evidence.get("verifier_source_sha256") == proof["verifier_sha256"]
        and evidence.get("container_id") == row["container_id"]
        and row["start_intent"] == row["create_reply_complete"] == 1
        and row["cancel_requested"] == row["cleanup_attempted"] == 0
        and evidence.get("execution_started") is True
        and evidence.get("cleanup_confirmed") is True
        and evidence.get("errors") == []
        and type(evidence.get("candidate_exit_code")) is int
        and evidence["candidate_exit_code"] == 0
        and counts == [proof["case_count"]] * 4
        and all(type(value) is int for value in counts)
        and type(checks) is dict
        and set(checks) == ISOLATION_CHECKS
        and all(value is True for value in checks.values())
    )


def validate_execution(
    db: sqlite3.Connection, job: sqlite3.Row, claim: sqlite3.Row | None, intent: sqlite3.Row | None
) -> sqlite3.Row | None:
    validate_project_links(db, job["project_id"])
    # OR queries find cross-links from either side, including foreign-project rows.
    rows = db.execute(
        "SELECT * FROM candidate_executions WHERE job_id=? OR claim_id=? OR intent_id=? LIMIT 2",
        (
            job["id"],
            None if claim is None else claim["id"],
            None if intent is None else intent["id"],
        ),
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1 or claim is None or intent is None:
        corrupt()
    row = rows[0]
    assert claim is not None and intent is not None
    try:
        proof = _load(row["proof_json"], 16384)
        if type(proof) is not dict or set(proof) != PROOF_FIELDS:
            corrupt()
        expected = {
            "schema": "agentsync.candidate-execution.v1",
            "id": row["id"],
            "project_id": job["project_id"],
            "job_id": job["id"],
            "claim_id": claim["id"],
            "intent_id": intent["id"],
            "claim_proof_sha256": claim["proof_sha256"],
            "intent_proof_sha256": intent["proof_sha256"],
            "lease_expires_at": claim["lease_expires_at"],
            "created_at": row["created_at"],
            **{key: job[key] for key in PINS},
            **{key: proof[key] for key in ("case_count", "cases_sha256", "verifier_sha256")},
        }
        if (
            proof != expected
            or _dump(expected) != row["proof_json"]
            or _hash(row["proof_json"]) != row["proof_sha256"]
            or str(uuid.UUID(row["id"])) != row["id"]
            or any(
                row[key] != expected[key]
                for key in ("project_id", "job_id", "claim_id", "intent_id")
            )
            or job["status"] != "claimed"
            or intent["status"] != "prepared"
            or not intent["created_at"] <= row["created_at"] < claim["lease_expires_at"]
            or row["updated_at"] < row["created_at"]
            or type(proof["case_count"]) is not int
            or not 1 <= proof["case_count"] <= 100
        ):
            corrupt()
        if (
            any(
                type(row[key]) not in {int, float} or not math.isfinite(row[key])
                for key in ("created_at", "updated_at")
            )
            or type(row["revision"]) is not int
            or not 1 <= row["revision"] <= 2**63 - 1
            or row["phase"]
            not in {"preparing", "create_intent", "created", "executing", "finished", "unresolved"}
            or row["assessment"] not in {"unverified", "passed", "failed", "unsupported", "error"}
            or any(
                type(row[key]) is not int or row[key] not in {0, 1}
                for key in (
                    "cancel_requested",
                    "create_intent",
                    "create_reply_complete",
                    "start_intent",
                    "cleanup_attempted",
                )
            )
        ):
            corrupt()
        for key in ("cases_sha256", "verifier_sha256"):
            _sha(proof[key])
        _sha(row["token_hash"])
        if row["create_intent"]:
            if (
                type(row["owner_nonce"]) is not str
                or not re.fullmatch("[a-f0-9]{32}", row["owner_nonce"])
                or row["container_name"] != "agentsync-verifier-" + row["owner_nonce"]
            ):
                corrupt()
        elif (
            any(row[key] is not None for key in ("owner_nonce", "container_name", "container_id"))
            or row["create_reply_complete"]
            or row["start_intent"]
        ):
            corrupt()
        if row["create_reply_complete"]:
            if type(row["container_id"]) is not str or not re.fullmatch(
                "[a-f0-9]{64}", row["container_id"]
            ):
                corrupt()
        elif row["container_id"] is not None or row["start_intent"]:
            corrupt()
        if row["phase"] in {"preparing", "create_intent", "created", "executing"}:
            expected_flags = {
                "preparing": (0, 0, 0),
                "create_intent": (1, 0, 0),
                "created": (1, 1, 0),
                "executing": (1, 1, 1),
            }[row["phase"]]
            if (
                tuple(
                    row[key] for key in ("create_intent", "create_reply_complete", "start_intent")
                )
                != expected_flags
                or row["assessment"] != "unverified"
            ):
                corrupt()
            if row["result_json"] != "{}":
                corrupt()
        if row["phase"] == "unresolved" and row["assessment"] != "unverified":
            corrupt()
        if row["result_json"] != "{}":
            evidence = _load(row["result_json"], 65536)
            if (
                _hash(row["result_json"]) != row["result_sha256"]
                or evidence.get("execution_id") != row["id"]
                or row["assessment"] == "passed"
                and not passed_evidence(row, proof, evidence)
                or row["phase"] == "finished"
                and evidence.get("status") != row["assessment"]
            ):
                corrupt()
        elif row["result_sha256"] is not None or row["phase"] == "finished":
            corrupt()
        if row["phase"] == "finished" and (
            row["assessment"] == "unverified" or row["cancel_requested"] or row["cleanup_attempted"]
        ):
            corrupt()
        if row["cleanup_attempted"]:
            cleanup = _load(row["cleanup_json"], 16384)
            if (
                row["phase"] != "unresolved"
                or row["assessment"] != "unverified"
                or _hash(row["cleanup_json"]) != row["cleanup_sha256"]
                or cleanup.get("execution_id") != row["id"]
                or cleanup.get("container_id") != row["container_id"]
                or set(cleanup)
                != {"schema", "execution_id", "container_id", "status", "observation"}
                or cleanup["schema"] != "agentsync.candidate-cleanup.v1"
                or cleanup["status"] not in {"intent", "observed"}
                or cleanup["status"] == "intent"
                and cleanup["observation"] is not None
                or cleanup["status"] == "observed"
                and type(cleanup["observation"]) is not dict
                or not row["create_reply_complete"]
            ):
                corrupt()
        elif row["cleanup_json"] != "{}" or row["cleanup_sha256"] is not None:
            corrupt()
        return row
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        corrupt()
    return None


def validate_project_links(db: sqlite3.Connection, project_id: str) -> None:
    orphan = db.execute(
        "SELECT 1 FROM candidate_executions e "
        "LEFT JOIN candidate_verification_jobs j ON j.id=e.job_id "
        "LEFT JOIN candidate_verification_claims c ON c.id=e.claim_id "
        "LEFT JOIN candidate_execution_intents i ON i.id=e.intent_id "
        "WHERE (e.project_id=? OR j.project_id=? OR c.project_id=? OR i.project_id=?) AND "
        "(j.id IS NULL OR c.id IS NULL OR i.id IS NULL OR e.project_id!=j.project_id "
        "OR e.project_id!=c.project_id OR e.project_id!=i.project_id "
        "OR e.job_id!=c.job_id OR e.job_id!=i.job_id OR e.claim_id!=i.claim_id) LIMIT 1",
        (project_id,) * 4,
    ).fetchone()
    if orphan:
        corrupt()


def projection(db: sqlite3.Connection, job: sqlite3.Row) -> dict[str, Any]:
    claim = db.execute(
        "SELECT * FROM candidate_verification_claims WHERE job_id=?", (job["id"],)
    ).fetchone()
    intent = db.execute(
        "SELECT * FROM candidate_execution_intents WHERE job_id=?", (job["id"],)
    ).fetchone()
    row = validate_execution(db, job, claim, intent)
    if row is None:
        return {}
    return {
        "execution_connected": True,
        "execution_assessment": row["assessment"],
        "execution_id": row["id"],
        "execution": {
            key: row[key]
            for key in (
                "id",
                "job_id",
                "claim_id",
                "intent_id",
                "revision",
                "phase",
                "assessment",
                "cancel_requested",
                "create_intent",
                "create_reply_complete",
                "start_intent",
                "container_id",
                "cleanup_attempted",
                "created_at",
                "updated_at",
            )
        }
        | {
            "permanently_fenced": True,
            "task_verification": "unverified",
            "result": _load(row["result_json"], 65536),
            "cleanup": _load(row["cleanup_json"], 16384),
        },
    }

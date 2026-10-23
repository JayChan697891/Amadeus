"""Owner-only reservations. No worker credentials, execution or task authority."""

from __future__ import annotations

import hmac
import math
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import (
    MAX_RESPONSE,
    CandidateVerificationJobs,
    _Cancel,
    _corrupt,
    _dump,
    _encode_input,
    _error,
    _hash,
    _load,
    _Lookup,
    _public,
    _shape,
    _text,
    _trusted_profile,
)
from agentsync.verification.docker import DockerProfile

if TYPE_CHECKING:
    from agentsync.core.service import Core

KIND = "owner_reservation_v1"
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
    "kind",
    "claim_version",
    *PINS,
    "created_at",
    "lease_expires_at",
}
FLAGS = {"execution_connected": False, "execution_assessment": "unverified"}


class _Claim(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 3)
    lease_seconds: int = Field(default=300, ge=1, le=3600)


def _finite(value: Any) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


def _summary(
    claim: sqlite3.Row, *, current: bool, job: sqlite3.Row | None = None, now: float | None = None
) -> dict[str, Any]:
    result = {
        key: claim[key]
        for key in (
            "id",
            "kind",
            "status",
            "reason_code",
            "created_at",
            "updated_at",
            "lease_expires_at",
            "proof_sha256",
        )
    }
    result.update(current_state=current, **FLAGS)
    if current:
        assert job is not None and now is not None
        regressed = now < max(job["updated_at"], claim["updated_at"], claim["created_at"])
        result.update(
            clock_regressed=regressed,
            lease_expired=None if regressed else now >= claim["lease_expires_at"],
        )
    return result


def _receipt(kind: str, job: sqlite3.Row, claim: sqlite3.Row) -> dict[str, Any]:
    value = {
        "schema": "agentsync.candidate-claim-receipt.v1"
        if kind == "claim"
        else "agentsync.candidate-recovery.v1",
        "receipt_kind": "historical_" + kind,
        "current_state": False,
        **FLAGS,
        "job": _public(job) | {"current_state": False},
        "reservation": _summary(claim, current=False),
    }
    if kind == "recovery":
        value["reason_code"] = "owner_interrupted"
    if len(_dump(value).encode("utf-8")) > MAX_RESPONSE:
        _error("response_too_large", "Candidate reservation response exceeds its bound.")
    return value


def _recovery_fingerprint(project: str, job: str, claim: str, version: int) -> str:
    return _hash(
        _dump(
            {
                "schema": "agentsync.candidate-claim-recovery-request.v1",
                "project_id": project,
                "job_id": job,
                "claim_id": claim,
                "expected_version": version,
            }
        )
    )


def validate_claim(db: sqlite3.Connection, job: sqlite3.Row) -> sqlite3.Row | None:
    """Pure relation validation on a metadata-validated job. Never recurse or Git."""
    from agentsync.verification.candidate_intents import validate_intent

    rows = db.execute(
        "SELECT * FROM candidate_verification_claims WHERE job_id=? LIMIT 2", (job["id"],)
    ).fetchall()
    recoveries = db.execute(
        "SELECT * FROM candidate_claim_recoveries WHERE job_id=? LIMIT 2", (job["id"],)
    ).fetchall()
    if job["status"] in {"queued", "cancelled"}:
        if rows or recoveries:
            _corrupt()
        validate_intent(db, job, None)
        return None
    if len(rows) != 1:
        _corrupt()
    claim = rows[0]
    try:
        if (
            claim["project_id"] != job["project_id"]
            or claim["kind"] != KIND
            or type(claim["claim_version"]) is not int
            or claim["claim_version"] != 2
            or str(uuid.UUID(claim["id"])) != claim["id"]
        ):
            _corrupt()
        proof = _load(claim["proof_json"], MAX_RESPONSE)
        _shape(proof, PROOF_FIELDS)
        expected = {
            "schema": "agentsync.candidate-claim.v1",
            **{key: claim[key] for key in PROOF_FIELDS - {"schema"}},
        }
        if (
            _dump(expected) != claim["proof_json"]
            or _hash(claim["proof_json"]) != claim["proof_sha256"]
            or any(claim[key] != job[key] for key in PINS)
        ):
            _corrupt()
        if (
            any(not _finite(claim[key]) for key in ("created_at", "updated_at", "lease_expires_at"))
            or not job["created_at"] <= claim["created_at"] <= claim["updated_at"]
            or claim["lease_expires_at"] <= claim["created_at"]
            or job["updated_at"] != claim["updated_at"]
        ):
            _corrupt()
        if job["status"] == "claimed":
            if (
                claim["status"] != "claimed"
                or claim["reason_code"] != ""
                or claim["updated_at"] != claim["created_at"]
                or recoveries
            ):
                _corrupt()
        elif job["status"] == "interrupted":
            if (
                claim["status"] != "interrupted"
                or claim["reason_code"] != "owner_interrupted"
                or len(recoveries) != 1
            ):
                _corrupt()
            recovery = recoveries[0]
            _text(recovery["request_id"])
            if (
                recovery["project_id"] != job["project_id"]
                or recovery["claim_id"] != claim["id"]
                or recovery["payload_hash"]
                != _recovery_fingerprint(job["project_id"], job["id"], claim["id"], 2)
            ):
                _corrupt()
            response = _load(recovery["response_json"], MAX_RESPONSE)
            if _hash(recovery["response_json"]) != recovery["response_sha256"] or _dump(
                response
            ) != _dump(_receipt("recovery", job, claim)):
                _corrupt()
        else:
            _corrupt()
        validate_intent(db, job, claim)
        return claim
    except (KeyError, IndexError, ValueError, TypeError, UnicodeError, OverflowError):
        _corrupt()


class OwnerCandidateClaims:
    def __init__(self, core: Core):
        self.core = core
        self.jobs = CandidateVerificationJobs(core)

    @staticmethod
    def _queued(row: sqlite3.Row, version: int, now: float) -> None:
        if row["version"] != version:
            _error("version_conflict", "Candidate reservation version changed.")
        if row["status"] != "queued":
            _error("invalid_state", "Only an unreserved queued candidate can be reserved.")
        if now < row["updated_at"]:
            _error("clock_regressed", "Clock rollback prevents candidate reservation.")

    def claim_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        profile: DockerProfile,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Claim,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
                "lease_seconds": lease_seconds,
            },
        )
        with self.jobs._transaction(p) as (db, now):
            initial = self.jobs._row(db, project_id, job_id)
            self._queued(initial, expected_version, now)
            policy = _trusted_profile(profile)
            if policy != {
                "kind": initial["profile_kind"],
                "sha256": initial["profile_sha256"],
                "image_id": initial["image_id"],
            }:
                _error(
                    "profile_mismatch", "Trusted profile differs from the queued candidate policy."
                )
        args = {
            "project_id": project_id,
            "admin_token": admin_token,
            "candidate_id": initial["candidate_id"],
            "expected_candidate_sha": initial["candidate_sha"],
        }
        exported = OwnerCandidateExporter(self.core).export(**args)
        with self.jobs._transaction(p, write=True, operation="candidate_verification_claim") as (
            db,
            now,
        ):
            job = self.jobs._row(db, project_id, job_id)
            self._queued(job, expected_version, now)
            if job["metadata_json"] != initial["metadata_json"] or any(
                job[key] != initial[key] for key in PINS
            ):
                _error(
                    "stale_candidate_input", "Pinned candidate metadata changed during reservation."
                )
            binding = OwnerCandidateBindings(self.core)._capture_in_transaction(db, **args)
            if (
                binding != exported.binding
                or _encode_input(exported, policy) != job["metadata_json"]
            ):
                _error(
                    "stale_candidate_input",
                    "Fresh candidate input differs from the queued observation.",
                )
            created = float(now)
            deadline = created + lease_seconds
            if not _finite(deadline) or deadline <= created:
                _error(
                    "invalid_reservation_deadline",
                    "Reservation deadline must be finite and later than creation.",
                )
            proof = {
                "schema": "agentsync.candidate-claim.v1",
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "job_id": job_id,
                "kind": KIND,
                "claim_version": 2,
                **{key: job[key] for key in PINS},
                "created_at": created,
                "lease_expires_at": deadline,
            }
            raw = _dump(proof)
            if len(raw.encode("utf-8")) > MAX_RESPONSE:
                _error("response_too_large", "Candidate claim proof exceeds its bound.")
            values = {key: value for key, value in proof.items() if key != "schema"} | {
                "proof_json": raw,
                "proof_sha256": _hash(raw),
                "status": "claimed",
                "reason_code": "",
                "updated_at": created,
            }
            db.execute(
                "INSERT INTO candidate_verification_claims("
                + ",".join(values)
                + ") VALUES("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            if (
                db.execute(
                    "UPDATE candidate_verification_jobs SET status='claimed',version=2,updated_at=? WHERE id=? AND project_id=? AND status='queued' AND version=1",
                    (created, job_id, project_id),
                ).rowcount
                != 1
            ):
                _error("version_conflict", "Candidate reservation lost a concurrent update.")
            job = self.jobs._row(db, project_id, job_id)
            claim = validate_claim(db, job)
            assert claim is not None
            response = _receipt("claim", job, claim)
            self.core._audit_event(
                db,
                project_id,
                "owner",
                project_id,
                "candidate_verification_claim",
                p,
                "success",
                "ok",
                _public(job),
            )
            return response

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Lookup, {"project_id": project_id, "admin_token": admin_token, "job_id": job_id}
        )
        with self.jobs._transaction(p) as (db, now):
            job = self.jobs._row(db, project_id, job_id)
            claim = validate_claim(db, job)
            response = {
                "current_state": True,
                **FLAGS,
                "job": _public(job),
                "reservation": None
                if claim is None
                else _summary(claim, current=True, job=job, now=now),
            }
            if len(_dump(response).encode("utf-8")) > MAX_RESPONSE:
                _error("response_too_large", "Candidate reservation view exceeds its bound.")
            return response

    def recover_interrupted(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        request_id: str,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Cancel,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
                "request_id": request_id,
            },
        )
        with self.jobs._transaction(p, write=True, operation="candidate_verification_recover") as (
            db,
            now,
        ):
            cached = db.execute(
                "SELECT * FROM candidate_claim_recoveries WHERE project_id=? AND request_id=?",
                (project_id, request_id),
            ).fetchone()
            if cached is not None:
                fingerprint = _recovery_fingerprint(
                    project_id, job_id, cached["claim_id"], expected_version
                )
                if not hmac.compare_digest(cached["payload_hash"], fingerprint):
                    _error(
                        "idempotency_conflict",
                        "Recovery request is bound to different reservation inputs.",
                    )
                self.jobs._row(db, project_id, job_id)
                return _load(cached["response_json"], MAX_RESPONSE)
            job = self.jobs._row(db, project_id, job_id)
            if job["version"] != expected_version:
                _error("version_conflict", "Candidate recovery version changed.")
            if job["status"] != "claimed":
                _error("invalid_state", "Only an owner reservation can be interrupted.")
            claim = validate_claim(db, job)
            assert claim is not None
            from agentsync.verification.candidate_intents import validate_intent

            intent = validate_intent(db, job, claim)
            if intent is not None and intent["status"] == "prepared":
                _error(
                    "execution_intent_active", "Prepared execution intent must be abandoned first."
                )
            timestamp = float(
                max(
                    now,
                    job["updated_at"],
                    claim["updated_at"],
                    claim["created_at"],
                    intent["updated_at"] if intent is not None else claim["updated_at"],
                )
            )
            db.execute(
                "UPDATE candidate_verification_claims SET status='interrupted',reason_code='owner_interrupted',updated_at=? WHERE id=? AND project_id=? AND status='claimed'",
                (timestamp, claim["id"], project_id),
            )
            if (
                db.execute(
                    "UPDATE candidate_verification_jobs SET status='interrupted',version=3,updated_at=? WHERE id=? AND project_id=? AND status='claimed' AND version=2",
                    (timestamp, job_id, project_id),
                ).rowcount
                != 1
            ):
                _error("version_conflict", "Candidate recovery lost a concurrent update.")
            changed_job = db.execute(
                "SELECT * FROM candidate_verification_jobs WHERE id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
            changed_claim = db.execute(
                "SELECT * FROM candidate_verification_claims WHERE id=? AND project_id=?",
                (claim["id"], project_id),
            ).fetchone()
            response = _receipt("recovery", changed_job, changed_claim)
            raw = _dump(response)
            fingerprint = _recovery_fingerprint(project_id, job_id, claim["id"], expected_version)
            db.execute(
                "INSERT INTO candidate_claim_recoveries VALUES(?,?,?,?,?,?,?)",
                (project_id, request_id, job_id, claim["id"], fingerprint, raw, _hash(raw)),
            )
            self.jobs._row(db, project_id, job_id)
            self.core._audit_event(
                db,
                project_id,
                "owner",
                project_id,
                "candidate_verification_recover",
                p,
                "success",
                "ok",
                _public(changed_job),
            )
            return response

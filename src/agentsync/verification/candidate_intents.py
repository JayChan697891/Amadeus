"""Non-executing owner intent ledger. Proofs confer no execution authority."""

from __future__ import annotations

import hmac
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.verification import candidate_jobs as queue_module
from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_claims import FLAGS, PINS, _finite, validate_claim
from agentsync.verification.candidate_jobs import (
    MAX_RESPONSE,
    CandidateVerificationJobs,
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
from agentsync.workspaces.git import GitWorkspaceStore

if TYPE_CHECKING:
    from agentsync.core.service import Core

KIND = "owner_candidate_execution_intent_v1"
PROOF_FIELDS = {
    "schema",
    "id",
    "project_id",
    "job_id",
    "claim_id",
    "kind",
    "claim_version",
    "claim_proof_sha256",
    *PINS,
    "created_at",
    "claim_lease_expires_at",
}


class _Prepare(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 3)


class _Abandon(_Lookup):
    intent_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, le=2**63 - 3)
    request_id: str = Field(min_length=1, max_length=200)


def _bounded(value: dict[str, Any]) -> dict[str, Any]:
    if len(_dump(value).encode("utf-8")) > MAX_RESPONSE:
        _error("response_too_large", "Candidate intent response exceeds its bound.")
    return value


def _summary(
    intent: sqlite3.Row,
    *,
    current: bool,
    job: sqlite3.Row | None = None,
    claim: sqlite3.Row | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    value = {key: intent[key] for key in PROOF_FIELDS - {"schema"}}
    value.update(
        {
            key: intent[key]
            for key in ("status", "revision", "reason_code", "updated_at", "proof_sha256")
        }
    )
    value.update(current_state=current, **FLAGS)
    if current:
        assert job is not None and claim is not None and now is not None
        regressed = now < max(
            job["updated_at"], claim["updated_at"], intent["updated_at"], intent["created_at"]
        )
        value.update(
            clock_regressed=regressed,
            lease_expired=None if regressed else now >= intent["claim_lease_expires_at"],
        )
    return value


def _receipt(kind: str, intent: sqlite3.Row) -> dict[str, Any]:
    value = {
        "schema": "agentsync.candidate-intent-receipt.v1",
        "receipt_kind": "historical_" + kind,
        "current_state": False,
        **FLAGS,
        "intent": _summary(intent, current=False),
    }
    if kind == "abandon":
        value["reason_code"] = "owner_abandoned"
    return _bounded(value)


def _fingerprint(project: str, job: str, intent: str, revision: int) -> str:
    return _hash(
        _dump(
            {
                "schema": "agentsync.candidate-intent-abandon-request.v1",
                "project_id": project,
                "job_id": job,
                "intent_id": intent,
                "expected_revision": revision,
            }
        )
    )


def validate_intent(
    db: sqlite3.Connection, job: sqlite3.Row, claim: sqlite3.Row | None
) -> sqlite3.Row | None:
    """Validate relations without recursion, mutation, clock or filesystem access."""
    rows = db.execute(
        "SELECT * FROM candidate_execution_intents WHERE job_id=? LIMIT 2", (job["id"],)
    ).fetchall()
    abandons = db.execute(
        "SELECT * FROM candidate_intent_abandonments WHERE job_id=? LIMIT 2", (job["id"],)
    ).fetchall()
    if claim is None:
        if rows or abandons:
            _corrupt()
        return None
    if not rows:
        if abandons:
            _corrupt()
        return None
    if len(rows) != 1:
        _corrupt()
    intent = rows[0]
    try:
        proof = _load(intent["proof_json"], MAX_RESPONSE)
        _shape(proof, PROOF_FIELDS)
        expected = {
            "schema": "agentsync.candidate-execution-intent.v1",
            **{key: intent[key] for key in PROOF_FIELDS - {"schema"}},
        }
        if (
            str(uuid.UUID(intent["id"])) != intent["id"]
            or intent["project_id"] != job["project_id"]
            or intent["claim_id"] != claim["id"]
            or intent["kind"] != KIND
            or type(intent["claim_version"]) is not int
            or intent["claim_version"] != 2
            or intent["claim_proof_sha256"] != claim["proof_sha256"]
            or any(intent[key] != job[key] or intent[key] != claim[key] for key in PINS)
            or intent["claim_lease_expires_at"] != claim["lease_expires_at"]
            or _dump(expected) != intent["proof_json"]
            or _hash(intent["proof_json"]) != intent["proof_sha256"]
        ):
            _corrupt()
        if (
            any(
                not _finite(intent[key])
                for key in ("created_at", "updated_at", "claim_lease_expires_at")
            )
            or not claim["created_at"] <= intent["created_at"] < claim["lease_expires_at"]
            or intent["updated_at"] < intent["created_at"]
            or type(intent["revision"]) is not int
        ):
            _corrupt()
        if intent["status"] == "prepared":
            if (
                intent["revision"] != 1
                or intent["reason_code"] != ""
                or intent["updated_at"] != intent["created_at"]
                or job["status"] != "claimed"
                or abandons
            ):
                _corrupt()
        elif intent["status"] == "abandoned":
            if (
                intent["revision"] != 2
                or intent["reason_code"] != "owner_abandoned"
                or len(abandons) != 1
            ):
                _corrupt()
            request = abandons[0]
            _text(request["request_id"])
            if (
                request["project_id"] != job["project_id"]
                or request["intent_id"] != intent["id"]
                or request["claim_id"] != claim["id"]
                or request["payload_hash"]
                != _fingerprint(job["project_id"], job["id"], intent["id"], 1)
                or _hash(request["response_json"]) != request["response_sha256"]
                or _dump(_load(request["response_json"], MAX_RESPONSE))
                != _dump(_receipt("abandon", intent))
            ):
                _corrupt()
            if job["status"] == "interrupted" and (
                job["updated_at"] < intent["updated_at"]
                or claim["updated_at"] < intent["updated_at"]
            ):
                _corrupt()
        else:
            _corrupt()
        return intent
    except (KeyError, IndexError, ValueError, TypeError, UnicodeError, OverflowError):
        _corrupt()


class OwnerCandidateExecutionIntents:
    def __init__(self, core: Core):
        self.core = core
        self.jobs = CandidateVerificationJobs(core)

    @staticmethod
    def _ready(job: sqlite3.Row, claim: sqlite3.Row | None, version: int, now: float) -> None:
        if job["version"] != version:
            _error("version_conflict", "Candidate intent job version changed.")
        if job["status"] != "claimed" or claim is None:
            _error("invalid_state", "Only a claimed candidate can prepare an intent.")
        if now < max(job["updated_at"], claim["updated_at"], claim["created_at"]):
            _error("clock_regressed", "Clock rollback prevents preparing an intent.")
        if now >= claim["lease_expires_at"]:
            _error("reservation_expired", "Candidate reservation expired.")

    def prepare_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        profile: DockerProfile,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Prepare,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
            },
        )
        with self.jobs._transaction(p) as (db, now):
            initial = self.jobs._row(db, project_id, job_id)
            initial_claim = validate_claim(db, initial)
            self._ready(initial, initial_claim, expected_version, now)
            assert initial_claim is not None
            if validate_intent(db, initial, initial_claim) is not None:
                _error("execution_intent_exists", "Candidate already has an execution intent.")
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
        with self.jobs._transaction(p, write=True, operation="candidate_intent_prepare") as (
            db,
            now,
        ):
            job = self.jobs._row(db, project_id, job_id)
            claim = validate_claim(db, job)
            self._ready(job, claim, expected_version, now)
            assert claim is not None
            if validate_intent(db, job, claim) is not None:
                _error("execution_intent_exists", "Candidate already has an execution intent.")
            if (
                claim["id"] != initial_claim["id"]
                or claim["proof_json"] != initial_claim["proof_json"]
                or claim["lease_expires_at"] != initial_claim["lease_expires_at"]
                or job["metadata_json"] != initial["metadata_json"]
                or any(job[key] != initial[key] for key in PINS)
            ):
                _error("stale_candidate_input", "Pinned candidate changed while preparing intent.")
            if _trusted_profile(profile) != policy:
                _error("profile_mismatch", "Trusted profile changed while preparing intent.")
            binding = OwnerCandidateBindings(self.core)._capture_in_transaction(db, **args)
            if (
                binding != exported.binding
                or _encode_input(exported, policy) != job["metadata_json"]
            ):
                _error(
                    "stale_candidate_input",
                    "Fresh candidate input differs from the queued observation.",
                )
            try:
                OwnerCandidateExporter._check(
                    GitWorkspaceStore(self.core.data_dir, create=False), binding
                )
            except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError):
                _error("candidate_input_invalid", "Existing candidate evidence is invalid.")
            now = queue_module.time.time()
            if not _finite(now):
                _error("invalid_clock", "Candidate intent clock must be finite.")
            self._ready(job, claim, expected_version, now)
            proof = {
                "schema": "agentsync.candidate-execution-intent.v1",
                "id": str(uuid.uuid4()),
                "project_id": project_id,
                "job_id": job_id,
                "claim_id": claim["id"],
                "kind": KIND,
                "claim_version": 2,
                "claim_proof_sha256": claim["proof_sha256"],
                **{key: job[key] for key in PINS},
                "created_at": float(now),
                "claim_lease_expires_at": claim["lease_expires_at"],
            }
            raw = _dump(proof)
            if len(raw.encode("utf-8")) > MAX_RESPONSE:
                _error("response_too_large", "Candidate intent proof exceeds its bound.")
            values = {key: value for key, value in proof.items() if key != "schema"} | {
                "proof_json": raw,
                "proof_sha256": _hash(raw),
                "status": "prepared",
                "revision": 1,
                "reason_code": "",
                "updated_at": float(now),
            }
            db.execute(
                "INSERT INTO candidate_execution_intents("
                + ",".join(values)
                + ") VALUES("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            intent = validate_intent(db, job, claim)
            assert intent is not None
            response = _receipt("prepare", intent)
            self.core._audit_event(
                db,
                project_id,
                "owner",
                project_id,
                "candidate_intent_prepare",
                p | {"expected_version": None},
                "success",
                "ok",
                {"id": intent["id"], "version": 1},
            )
            return response

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Lookup, {"project_id": project_id, "admin_token": admin_token, "job_id": job_id}
        )
        with self.jobs._transaction(p) as (db, now):
            job = self.jobs._row(db, project_id, job_id)
            claim = validate_claim(db, job)
            intent = validate_intent(db, job, claim)
            return _bounded(
                {
                    "current_state": True,
                    **FLAGS,
                    "job": _public(job),
                    "intent": None
                    if intent is None
                    else _summary(intent, current=True, job=job, claim=claim, now=now),
                }
            )

    def abandon_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        intent_id: str,
        expected_revision: int,
        request_id: str,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Abandon,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "intent_id": intent_id,
                "expected_revision": expected_revision,
                "request_id": request_id,
            },
        )
        fingerprint = _fingerprint(project_id, job_id, intent_id, expected_revision)
        with self.jobs._transaction(p, write=True, operation="candidate_intent_abandon") as (
            db,
            now,
        ):
            cached = db.execute(
                "SELECT * FROM candidate_intent_abandonments WHERE project_id=? AND request_id=?",
                (project_id, request_id),
            ).fetchone()
            if cached is not None:
                if not hmac.compare_digest(cached["payload_hash"], fingerprint):
                    _error(
                        "idempotency_conflict",
                        "Abandon request is bound to different intent inputs.",
                    )
                self.jobs._row(db, project_id, job_id)
                return _load(cached["response_json"], MAX_RESPONSE)
            job = self.jobs._row(db, project_id, job_id)
            claim = validate_claim(db, job)
            intent = validate_intent(db, job, claim)
            if intent is None or intent["id"] != intent_id:
                _error("not_found", "Candidate intent does not exist.")
            if intent["revision"] != expected_revision:
                _error("version_conflict", "Candidate intent revision changed.")
            if intent["status"] != "prepared":
                _error("invalid_state", "Only a prepared intent can be abandoned.")
            assert claim is not None
            timestamp = float(
                max(
                    now,
                    job["updated_at"],
                    claim["updated_at"],
                    claim["created_at"],
                    intent["updated_at"],
                    intent["created_at"],
                )
            )
            if (
                db.execute(
                    "UPDATE candidate_execution_intents SET status='abandoned',revision=2,reason_code='owner_abandoned',updated_at=? WHERE id=? AND project_id=? AND status='prepared' AND revision=1",
                    (timestamp, intent_id, project_id),
                ).rowcount
                != 1
            ):
                _error("version_conflict", "Candidate intent lost a concurrent update.")
            changed = db.execute(
                "SELECT * FROM candidate_execution_intents WHERE id=?", (intent_id,)
            ).fetchone()
            response = _receipt("abandon", changed)
            raw = _dump(response)
            db.execute(
                "INSERT INTO candidate_intent_abandonments VALUES(?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    request_id,
                    job_id,
                    claim["id"],
                    intent_id,
                    fingerprint,
                    raw,
                    _hash(raw),
                ),
            )
            self.jobs._row(db, project_id, job_id)
            self.core._audit_event(
                db,
                project_id,
                "owner",
                project_id,
                "candidate_intent_abandon",
                p | {"expected_version": expected_revision},
                "success",
                "ok",
                {"id": intent_id, "version": 2},
            )
            return response

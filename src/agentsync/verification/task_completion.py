"""Internal owner-mediated independent acceptance of an exact candidate execution.

No transport or execution entry point is added. Text reviews remain assertions.
The durable receipt describes its original completed version, never later state.
"""

from __future__ import annotations

import dataclasses
import hmac
import math
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.verification import candidate_jobs as clock
from agentsync.verification import docker
from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_claims import validate_claim
from agentsync.verification.candidate_execution_state import (
    PINS,
    passed_evidence,
    validate_execution,
)
from agentsync.verification.candidate_intents import validate_intent
from agentsync.verification.candidate_jobs import (
    CandidateVerificationJobs,
    _dump,
    _encode_input,
    _error,
    _hash,
    _load,
    _Lookup,
    _trusted_profile,
)
from agentsync.verification.docker import DockerProfile

if TYPE_CHECKING:
    from agentsync.core.service import Core


class _Complete(_Lookup):
    session_id: str = Field(min_length=1, max_length=200)
    session_token: str = Field(min_length=1, max_length=4096)
    task_id: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=1, le=2**63 - 2)
    execution_id: str = Field(min_length=1, max_length=200)
    expected_execution_revision: int = Field(ge=1, le=2**63 - 2)
    request_id: str = Field(min_length=1, max_length=200)


def _corrupt() -> None:
    _error("corrupt_task_verification", "Stored task verification is inconsistent.")


def _execution(db: sqlite3.Connection, job: sqlite3.Row) -> sqlite3.Row:
    claim = validate_claim(db, job)
    intent = validate_intent(db, job, claim)
    execution = validate_execution(db, job, claim, intent)
    if execution is None or execution["phase"] != "finished" or execution["assessment"] != "passed":
        _error("verification_required", "A finished passed candidate execution is required.")
    if not passed_evidence(
        execution, _load(execution["proof_json"], 16384), _load(execution["result_json"], 65536)
    ):
        _corrupt()
    return execution


def _proof(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    """Validate historical relations without recapturing the now-advanced pair."""
    try:
        proof = _load(row["proof_json"], 16384)
        job = CandidateVerificationJobs._row(db, row["project_id"], row["job_id"])
        execution = _execution(db, job)
        review = db.execute(
            "SELECT * FROM reviews WHERE task_id=? AND project_id=? AND version=?",
            (row["task_id"], row["project_id"], row["completed_version"]),
        ).fetchone()
        reviewer = db.execute(
            "SELECT agent_id FROM sessions WHERE id=? AND project_id=?",
            (row["reviewer_session_id"], row["project_id"]),
        ).fetchone()
        creators = _load(job["metadata_json"], 4 * 1024 * 1024)["binding"]["creator_session_ids"]
        for identity in creators:
            author = db.execute(
                "SELECT agent_id FROM sessions WHERE id=? AND project_id=?",
                (identity, row["project_id"]),
            ).fetchone()
            if author is None or author["agent_id"] == row["reviewer_agent_id"]:
                _corrupt()
        side = "left" if row["task_id"] == job["left_task_id"] else "right"
        expected = {
            "schema": "agentsync.task-verification.v1",
            **{
                key: row[key]
                for key in (
                    "id",
                    "project_id",
                    "task_id",
                    "completed_version",
                    "job_id",
                    "execution_id",
                    "reviewer_agent_id",
                    "reviewer_session_id",
                    "created_at",
                )
            },
            "review_version": job[side + "_task_version"],
            "left_task_id": job["left_task_id"],
            "right_task_id": job["right_task_id"],
            "left_task_version": job["left_task_version"],
            "right_task_version": job["right_task_version"],
            "binding_sha256": job["binding_sha256"],
            **{key: job[key] for key in PINS},
            "execution_revision": execution["revision"],
            "execution_proof_sha256": execution["proof_sha256"],
            "result_sha256": execution["result_sha256"],
        }
        if (
            proof != expected
            or _dump(expected) != row["proof_json"]
            or _hash(row["proof_json"]) != row["proof_sha256"]
            or str(uuid.UUID(row["id"])) != row["id"]
            or row["execution_id"] != execution["id"]
            or row["task_id"] not in {job["left_task_id"], job["right_task_id"]}
            or row["completed_version"] != proof["review_version"] + 1
            or review is None
            or reviewer is None
            or reviewer["agent_id"] != row["reviewer_agent_id"]
            or review["accept"] != 1
            or review["reviewer_agent_id"] != row["reviewer_agent_id"]
            or review["reviewer_session_id"] != row["reviewer_session_id"]
            or review["evidence"] != "candidate-verification:" + row["id"]
            or review["created_at"] != row["created_at"]
            or row["created_at"] < execution["updated_at"]
        ):
            _corrupt()
        return proof
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        _corrupt()
    raise AssertionError("unreachable")


def task_projection(db: sqlite3.Connection, task: sqlite3.Row) -> dict[str, Any]:
    rows = db.execute(
        "SELECT * FROM task_verifications WHERE task_id=? AND completed_version=?",
        (task["id"], task["version"]),
    ).fetchall()
    if not rows:
        return {"task_verification": "unverified", "verification": None}
    if len(rows) != 1 or rows[0]["project_id"] != task["project_id"]:
        _corrupt()
    proof = _proof(db, rows[0])
    if task["status"] != "completed":
        _corrupt()
    return {"task_verification": "verified", "verification": proof}


def historical_task_response(response: dict[str, Any]) -> dict[str, Any]:
    """Normalize pre-v14 caches using only that receipt, never the current task."""
    if "status" in response and "version" in response and "title" in response:
        response.setdefault("task_verification", "unverified")
        response.setdefault("verification", None)
    return response


class OwnerVerifiedTaskCompletion:
    def __init__(self, core: Core):
        self.core, self.jobs = core, CandidateVerificationJobs(core)

    def _reviewer(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, job: sqlite3.Row
    ) -> sqlite3.Row:
        # Owner auth is performed by the enclosing transaction, before this call.
        reviewer = self.core._authenticate(db, p, now)
        self.core._authorize_session(db, "review_task", reviewer)
        metadata = _load(job["metadata_json"], 4 * 1024 * 1024)
        authors = set(metadata["binding"]["creator_session_ids"])
        for task_id in (job["left_task_id"], job["right_task_id"]):
            task = self.core._task(db, p | {"task_id": task_id})
            if task["owner_session_id"]:
                authors.add(task["owner_session_id"])
        for identity in authors:
            author = db.execute(
                "SELECT agent_id FROM sessions WHERE id=? AND project_id=?",
                (identity, p["project_id"]),
            ).fetchone()
            if author is None:
                _corrupt()
            if author["agent_id"] == reviewer["agent_id"]:
                _error(
                    "separate_reviewer_required", "An independent agent must verify the task.", 403
                )
        return reviewer

    def _authority(self, db: sqlite3.Connection, p: dict[str, Any], earliest: float) -> float:
        now = clock.time.time()
        if type(now) not in {int, float} or not math.isfinite(now) or now < earliest:
            _error("clock_regressed", "Completion requires finite non-regressed time.")
        self.core._authenticate_owner(db, p)
        reviewer = self.core._authenticate(db, p, now)
        self.core._authorize_session(db, "review_task", reviewer)
        return now

    @staticmethod
    def _receipt(proof: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": proof["task_id"],
            "version": proof["completed_version"],
            "status": "completed",
            "task_verification": "verified",
            "verification": proof,
            "current_state": False,
            "receipt_kind": "historical_verified_completion",
        }

    def complete_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        session_id: str,
        session_token: str,
        task_id: str,
        expected_version: int,
        job_id: str,
        execution_id: str,
        expected_execution_revision: int,
        request_id: str,
        profile: DockerProfile,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Complete,
            dict(
                project_id=project_id,
                admin_token=admin_token,
                session_id=session_id,
                session_token=session_token,
                task_id=task_id,
                expected_version=expected_version,
                job_id=job_id,
                execution_id=execution_id,
                expected_execution_revision=expected_execution_revision,
                request_id=request_id,
            ),
        )
        with self.jobs._transaction(p, write=True, operation="task_verified_complete") as (db, now):
            self._authority(db, p, now)
            job = self.jobs._row(db, project_id, job_id)
            reviewer = self._reviewer(db, p, now, job)
            policy = _trusted_profile(profile)
            if policy != {
                "kind": job["profile_kind"],
                "sha256": job["profile_sha256"],
                "image_id": job["image_id"],
            }:
                _error("profile_mismatch", "Current trusted profile differs from the execution.")
            fingerprint = _hash(
                _dump(
                    {
                        key: value
                        for key, value in p.items()
                        if key not in {"admin_token", "session_token", "request_id"}
                    }
                    | {"profile": policy}
                )
            )
            old = db.execute(
                "SELECT * FROM task_verification_requests WHERE project_id=? AND request_id=?",
                (project_id, request_id),
            ).fetchone()
            if old is not None:
                if not hmac.compare_digest(old["payload_hash"], fingerprint):
                    _error("idempotency_conflict", "Request ID already binds another completion.")
                row = db.execute(
                    "SELECT * FROM task_verifications WHERE id=?", (old["verification_id"],)
                ).fetchone()
                if row is None or row["project_id"] != project_id:
                    _corrupt()
                receipt = self._receipt(_proof(db, row))
                if (
                    _dump(receipt) != old["response_json"]
                    or _hash(old["response_json"]) != old["response_sha256"]
                ):
                    _corrupt()
                self._authority(db, p, now)
                return receipt
            task = self.core._task(db, p)
            self.core._version(task, p)
            if task["status"] != "review" or task_id not in {
                job["left_task_id"],
                job["right_task_id"],
            }:
                _error("invalid_state", "Completion requires the exact submitted candidate task.")
            execution = _execution(db, job)
            if (
                execution["id"] != execution_id
                or execution["revision"] != expected_execution_revision
            ):
                _error("version_conflict", "Candidate execution changed.")
            proof = _load(execution["proof_json"], 16384)
            cases = [
                {
                    "input": docker._json(case.input_json),
                    "expected": docker._json(case.expected_json),
                }
                for case in profile.cases
            ]
            if proof["case_count"] != len(profile.cases) or proof["cases_sha256"] != _hash(
                _dump(cases)
            ):
                _error("profile_mismatch", "Execution cases differ from current trusted policy.")
            if proof["verifier_sha256"] != _hash(Path(docker.__file__).read_bytes()):
                _error("stale_verifier", "Execution used a different verifier implementation.")
            binding = OwnerCandidateBindings(self.core)._capture_in_transaction(
                db,
                project_id=project_id,
                admin_token=admin_token,
                candidate_id=job["candidate_id"],
                expected_candidate_sha=job["candidate_sha"],
            )
            if _dump(dataclasses.asdict(binding)) != _dump(
                _load(job["metadata_json"], 4 * 1024 * 1024)["binding"]
            ):
                _error("stale_candidate_input", "Both candidate task versions must match exactly.")
            exported = OwnerCandidateExporter(self.core).export(
                project_id=project_id,
                admin_token=admin_token,
                candidate_id=job["candidate_id"],
                expected_candidate_sha=job["candidate_sha"],
            )
            if (
                exported.binding != binding
                or _encode_input(exported, policy) != job["metadata_json"]
            ):
                _error(
                    "stale_candidate_input",
                    "Fresh physical candidate export differs from execution.",
                )
            # Recheck current authority/time immediately before the atomic mutation.
            final_now = clock.time.time()
            if (
                type(final_now) not in {int, float}
                or not math.isfinite(final_now)
                or final_now < max(now, task["updated_at"], execution["updated_at"])
            ):
                _error("clock_regressed", "Completion requires finite non-regressed time.")
            self.core._authenticate_owner(db, p)
            self._reviewer(db, p, final_now, job)
            verification_id = str(uuid.uuid4())
            self.core._review_task(
                db,
                p | {"evidence": "candidate-verification:" + verification_id, "accept": True},
                final_now,
                reviewer,
            )
            values = dict(
                id=verification_id,
                project_id=project_id,
                task_id=task_id,
                completed_version=expected_version + 1,
                job_id=job_id,
                execution_id=execution_id,
                reviewer_agent_id=reviewer["agent_id"],
                reviewer_session_id=session_id,
                created_at=final_now,
            )
            completed_proof = {
                "schema": "agentsync.task-verification.v1",
                **values,
                "review_version": expected_version,
                **{
                    key: job[key]
                    for key in (
                        *PINS,
                        "left_task_id",
                        "right_task_id",
                        "left_task_version",
                        "right_task_version",
                        "binding_sha256",
                    )
                },
                "execution_revision": execution["revision"],
                "execution_proof_sha256": execution["proof_sha256"],
                "result_sha256": execution["result_sha256"],
            }
            raw = _dump(completed_proof)
            values.update(proof_json=raw, proof_sha256=_hash(raw))
            db.execute(
                "INSERT INTO task_verifications("
                + ",".join(values)
                + ") VALUES("
                + ",".join("?" for _ in values)
                + ")",
                tuple(values.values()),
            )
            row = db.execute(
                "SELECT * FROM task_verifications WHERE id=?", (verification_id,)
            ).fetchone()
            assert row is not None
            response = self._receipt(_proof(db, row))
            raw = _dump(response)
            db.execute(
                "INSERT INTO task_verification_requests VALUES(?,?,?,?,?,?)",
                (project_id, request_id, fingerprint, verification_id, raw, _hash(raw)),
            )
            self.core._audit_event(
                db,
                project_id,
                "owner",
                project_id,
                "task_verified_complete",
                p,
                "success",
                "ok",
                {"id": task_id, "version": expected_version + 1},
            )
            self.core._audit_event(
                db,
                project_id,
                "agent",
                reviewer["agent_id"],
                "task_verified_complete",
                p,
                "success",
                "ok",
                {"id": task_id, "version": expected_version + 1},
            )
            self._authority(db, p, final_now)
            return response

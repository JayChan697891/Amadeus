"""One owner candidate/container attempt, permanently fenced; never task acceptance.

Cancellation is cooperative at lifecycle/commit checks. A synchronous Docker wait
can continue until its existing bounded timeout; cancellation is not an immediate
kill acknowledgement. Crashes and uncertain commits never authorize another run.
"""

from __future__ import annotations

import dataclasses
import hmac
import re
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.verification import candidate_jobs as queue_module
from agentsync.verification import docker as backend
from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_claims import _finite, validate_claim
from agentsync.verification.candidate_execution_state import PINS, passed_evidence, projection
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
from agentsync.verification.docker import (
    DockerProfile,
    VerificationResult,
    verify_python_json_lines,
)
from agentsync.verification.executor import OwnerVerificationExecutor
from agentsync.verification.reconciliation import _observation
from agentsync.workspaces.git import GitWorkspaceStore

if TYPE_CHECKING:
    from agentsync.core.service import Core


class _Execute(_Lookup):
    intent_id: str = Field(min_length=1, max_length=200)
    expected_job_version: int = Field(ge=1, le=2**63 - 3)
    expected_intent_revision: int = Field(ge=1, le=2**63 - 3)


class _Action(_Lookup):
    execution_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=1, le=2**63 - 3)


@dataclasses.dataclass(frozen=True)
class _Run:
    payload: dict[str, Any] = dataclasses.field(repr=False)
    execution_id: str
    token: str = dataclasses.field(repr=False)
    profile: DockerProfile


class _Lifecycle:
    def __init__(self, executor: OwnerCandidateExecutor, run: _Run):
        self.executor, self.run = executor, run

    def before_create(self, owner: str, container_name: str) -> None:
        if (
            not re.fullmatch("[a-f0-9]{32}", owner)
            or container_name != "agentsync-verifier-" + owner
        ):
            _error("lifecycle_error", "Invalid trusted container identity.")
        self.executor._advance(
            self.run,
            "preparing",
            {
                "phase": "create_intent",
                "create_intent": 1,
                "owner_nonce": owner,
                "container_name": container_name,
            },
            45,
        )

    def created(self, container_id: str) -> None:
        if not backend.CONTAINER_ID.fullmatch(container_id):
            _error("lifecycle_error", "Full acknowledged container identity required.")
        self.executor._advance(
            self.run,
            "create_intent",
            {"phase": "created", "create_reply_complete": 1, "container_id": container_id},
        )

    def before_start(self) -> None:
        self.executor._advance(self.run, "created", {"phase": "executing", "start_intent": 1}, 30)


class OwnerCandidateExecutor:
    def __init__(self, core: Core):
        self.core, self.jobs = core, CandidateVerificationJobs(core)

    def _audit(
        self, db: sqlite3.Connection, p: dict[str, Any], operation: str, row: sqlite3.Row
    ) -> None:
        self.core._audit_event(
            db,
            p["project_id"],
            "owner",
            p["project_id"],
            operation,
            p | {"expected_version": row["revision"] - 1},
            "success",
            "ok",
            {"id": row["id"], "version": row["revision"]},
        )

    def _row(
        self, db: sqlite3.Connection, p: dict[str, Any]
    ) -> tuple[sqlite3.Row, sqlite3.Row | None]:
        job = self.jobs._row(db, p["project_id"], p["job_id"])
        row = db.execute(
            "SELECT * FROM candidate_executions WHERE project_id=? AND job_id=?",
            (p["project_id"], p["job_id"]),
        ).fetchone()
        return job, row

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Lookup, dict(project_id=project_id, admin_token=admin_token, job_id=job_id)
        )
        with self.jobs._transaction(p) as (db, now):
            job, row = self._row(db, p)
            if row is None:
                _error("not_found", "Candidate has no execution.", 404)
            proof = _load(row["proof_json"], 16384)
            return projection(db, job) | {
                "current_state": True,
                "lease_expired": now >= proof["lease_expires_at"],
                "clock_regressed": now < row["updated_at"],
            }

    def _ready(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, profile: DockerProfile
    ) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row]:
        job, execution = self._row(db, p)
        if execution is not None:
            _error(
                "candidate_execution_exists",
                "Candidate execution permanently consumes this reservation.",
            )
        claim = validate_claim(db, job)
        intent = validate_intent(db, job, claim)
        if claim is None or intent is None or intent["id"] != p["intent_id"]:
            _error("not_found", "Prepared candidate intent does not exist.")
        if (
            job["version"] != p["expected_job_version"]
            or intent["revision"] != p["expected_intent_revision"]
        ):
            _error("version_conflict", "Candidate execution inputs changed.")
        if job["status"] != "claimed" or intent["status"] != "prepared":
            _error("invalid_state", "Execution requires the original prepared reservation.")
        if _trusted_profile(profile) != {
            "kind": job["profile_kind"],
            "sha256": job["profile_sha256"],
            "image_id": job["image_id"],
        }:
            _error(
                "profile_mismatch", "Execution profile differs from the pinned candidate policy."
            )
        if now < max(job["updated_at"], claim["updated_at"], intent["updated_at"]):
            _error("clock_regressed", "Clock rollback prevents candidate execution.")
        if claim["lease_expires_at"] - now < profile.timeout_seconds + 60:
            _error(
                "reservation_expired", "Insufficient reservation time for execution and cleanup."
            )
        return job, claim, intent

    def _active(
        self, db: sqlite3.Connection, run: _Run, now: float, *, stopped: bool = False
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        job, row = self._row(db, run.payload)
        if (
            row is None
            or row["id"] != run.execution_id
            or not hmac.compare_digest(row["token_hash"], _hash(run.token))
        ):
            _error("execution_denied", "Execution no longer matches its private process attempt.")
        proof = _load(row["proof_json"], 16384)
        if (
            now < row["updated_at"]
            or now >= proof["lease_expires_at"]
            or row["phase"] in {"finished", "unresolved"}
            or row["cleanup_attempted"]
        ):
            _error("execution_unresolved", "Execution time or state no longer permits progress.")
        if row["cancel_requested"] and not stopped:
            _error("execution_cancelled", "Owner cancellation prevents execution progress.")
        binding = OwnerCandidateBindings(self.core)._capture_in_transaction(
            db,
            project_id=run.payload["project_id"],
            admin_token=run.payload["admin_token"],
            candidate_id=job["candidate_id"],
            expected_candidate_sha=job["candidate_sha"],
        )
        metadata = _load(job["metadata_json"], 4 * 1024 * 1024)
        if _dump(dataclasses.asdict(binding)) != _dump(metadata["binding"]):
            _error("stale_candidate_input", "Candidate task or binding changed during execution.")
        return job, row

    def _advance(self, run: _Run, phase: str, values: dict[str, Any], allowance: float = 0) -> None:
        with self.jobs._transaction(
            run.payload, write=True, operation="candidate_execution_progress"
        ) as (db, now):
            if phase == "create_intent":
                # An acknowledged ID is an observation, not permission to start.
                # Preserve it even if cancellation/expiry/task changes raced create.
                _, row = self._row(db, run.payload)
                if (
                    row is None
                    or row["id"] != run.execution_id
                    or not hmac.compare_digest(row["token_hash"], _hash(run.token))
                    or row["cleanup_attempted"]
                ):
                    _error("execution_denied", "Acknowledgement belongs to another execution.")
            else:
                _, row = self._active(db, run, now)
            proof = _load(row["proof_json"], 16384)
            if row["phase"] != phase or (
                phase != "create_intent"
                and proof["lease_expires_at"] - now < run.profile.timeout_seconds + allowance
            ):
                _error("lifecycle_error", "Execution phase or cleanup time is insufficient.")
            db.execute(
                "UPDATE candidate_executions SET "
                + ",".join(key + "=?" for key in values)
                + ",revision=revision+1,updated_at=? WHERE id=?",
                (*values.values(), max(now, row["updated_at"]), run.execution_id),
            )
            job, changed = self._row(db, run.payload)
            assert changed is not None
            self._audit(db, run.payload, "candidate_execution_progress", changed)

    def execute_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        intent_id: str,
        expected_job_version: int,
        expected_intent_revision: int,
        profile: DockerProfile,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Execute,
            dict(
                project_id=project_id,
                admin_token=admin_token,
                job_id=job_id,
                intent_id=intent_id,
                expected_job_version=expected_job_version,
                expected_intent_revision=expected_intent_revision,
            ),
        )
        with self.jobs._transaction(p) as (db, now):
            initial = self._ready(db, p, now, profile)
        profile = dataclasses.replace(profile)
        args = dict(
            project_id=project_id,
            admin_token=admin_token,
            candidate_id=initial[0]["candidate_id"],
            expected_candidate_sha=initial[0]["candidate_sha"],
        )
        exported = OwnerCandidateExporter(self.core).export(**args)
        token, execution_id = secrets.token_urlsafe(32), str(uuid.uuid4())
        with self.jobs._transaction(p, write=True, operation="candidate_execution_admit") as (
            db,
            now,
        ):
            job, claim, intent = self._ready(db, p, now, profile)
            if (
                any(
                    current["proof_json"] != old["proof_json"]
                    for current, old in zip((claim, intent), initial[1:], strict=True)
                )
                or job["metadata_json"] != initial[0]["metadata_json"]
                or any(job[key] != initial[0][key] for key in PINS)
            ):
                _error("stale_candidate_input", "Candidate inputs changed during fresh export.")
            binding = OwnerCandidateBindings(self.core)._capture_in_transaction(db, **args)
            if (
                binding != exported.binding
                or _encode_input(exported, _trusted_profile(profile)) != job["metadata_json"]
            ):
                _error(
                    "stale_candidate_input", "Fresh candidate export differs from pinned metadata."
                )
            OwnerCandidateExporter._check(
                GitWorkspaceStore(self.core.data_dir, create=False), binding
            )
            now = queue_module.time.time()
            if not _finite(now):
                _error("invalid_clock", "Finite execution time required.")
            job, claim, intent = self._ready(db, p, now, profile)
            cases = [
                {
                    "input": backend._json(case.input_json),
                    "expected": backend._json(case.expected_json),
                }
                for case in profile.cases
            ]
            proof = dict(
                schema="agentsync.candidate-execution.v1",
                id=execution_id,
                project_id=project_id,
                job_id=job_id,
                claim_id=claim["id"],
                intent_id=intent_id,
                claim_proof_sha256=claim["proof_sha256"],
                intent_proof_sha256=intent["proof_sha256"],
                lease_expires_at=claim["lease_expires_at"],
                created_at=float(now),
                case_count=len(profile.cases),
                cases_sha256=_hash(_dump(cases)),
                verifier_sha256=_hash(Path(backend.__file__).read_bytes()),
                **{key: job[key] for key in PINS},
            )
            raw = _dump(proof)
            db.execute(
                "INSERT INTO candidate_executions(id,project_id,job_id,claim_id,intent_id,proof_json,proof_sha256,token_hash,revision,phase,assessment,cancel_requested,create_intent,create_reply_complete,start_intent,result_json,cleanup_attempted,cleanup_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,'preparing','unverified',0,0,0,0,'{}',0,'{}',?,?)",
                (
                    execution_id,
                    project_id,
                    job_id,
                    claim["id"],
                    intent_id,
                    raw,
                    _hash(raw),
                    _hash(token),
                    now,
                    now,
                ),
            )
            _, row = self._row(db, p)
            assert row is not None
            self._audit(db, p, "candidate_execution_admit", row)
        run = _Run(p, execution_id, token, profile)
        result = None
        try:
            result = verify_python_json_lines(
                exported.snapshot.source,
                profile=profile,
                input_sha256=exported.snapshot.input_sha256,
                commit_sha=exported.snapshot.commit_sha,
                tree_sha=exported.snapshot.tree_sha,
                _lifecycle=_Lifecycle(self, run),
            )
            safe = OwnerVerificationExecutor._safe_result(result) | {"execution_id": execution_id}
            with self.jobs._transaction(p, write=True, operation="candidate_execution_finish") as (
                db,
                now,
            ):
                _, row = self._active(db, run, now, stopped=True)
                proof = _load(row["proof_json"], 16384)
                if result.status == "passed" and not passed_evidence(row, proof, safe):
                    _error(
                        "invalid_backend_result",
                        "Candidate verifier evidence does not match this execution.",
                    )
                unresolved = (
                    row["cancel_requested"]
                    or safe.get("cleanup_confirmed") is not True
                    or row["create_intent"]
                    and not row["create_reply_complete"]
                    or any("timeout" in str(error) for error in safe.get("errors", []))
                )
                phase, assessment = (
                    ("unresolved", "unverified") if unresolved else ("finished", result.status)
                )
                raw = _dump(safe)
                db.execute(
                    "UPDATE candidate_executions SET phase=?,assessment=?,result_json=?,result_sha256=?,revision=revision+1,updated_at=? WHERE id=?",
                    (phase, assessment, raw, _hash(raw), now, execution_id),
                )
                _, changed = self._row(db, p)
                assert changed is not None
                self._audit(db, p, "candidate_execution_finish", changed)
        except Exception:
            self._quarantine(run, result)
        return self.get(project_id=project_id, admin_token=admin_token, job_id=job_id)

    def _quarantine(self, run: _Run, result: VerificationResult | None) -> None:
        try:
            with self.jobs._transaction(
                run.payload, write=True, operation="candidate_execution_unresolved"
            ) as (db, now):
                _, row = self._row(db, run.payload)
                if (
                    row is None
                    or row["id"] != run.execution_id
                    or not hmac.compare_digest(row["token_hash"], _hash(run.token))
                    or row["phase"] == "finished"
                ):
                    return
                raw = "{}"
                if result is not None:
                    try:
                        raw = _dump(
                            OwnerVerificationExecutor._safe_result(result)
                            | {"execution_id": run.execution_id, "observation_only": True}
                        )
                    except Exception:
                        pass
                db.execute(
                    "UPDATE candidate_executions SET phase='unresolved',assessment='unverified',result_json=?,result_sha256=?,revision=revision+1,updated_at=? WHERE id=?",
                    (
                        raw,
                        None if raw == "{}" else _hash(raw),
                        max(now, row["updated_at"]),
                        run.execution_id,
                    ),
                )
                _, changed = self._row(db, run.payload)
                assert changed is not None
                self._audit(db, run.payload, "candidate_execution_unresolved", changed)
        except Exception:
            # A crash or failed quarantine audit leaves its durable original fence.
            pass

    def _action(self, db: sqlite3.Connection, p: dict[str, Any]) -> tuple[sqlite3.Row, sqlite3.Row]:
        job, row = self._row(db, p)
        if row is None or row["id"] != p["execution_id"]:
            _error("not_found", "Candidate execution does not exist.")
        if row["revision"] != p["expected_revision"]:
            _error("version_conflict", "Candidate execution revision changed.")
        return job, row

    def cancel(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        execution_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Action,
            dict(
                project_id=project_id,
                admin_token=admin_token,
                job_id=job_id,
                execution_id=execution_id,
                expected_revision=expected_revision,
            ),
        )
        with self.jobs._transaction(p, write=True, operation="candidate_execution_cancel") as (
            db,
            now,
        ):
            _, row = self._action(db, p)
            if row["phase"] in {"finished", "unresolved"} or row["cancel_requested"]:
                _error("invalid_state", "Candidate execution cannot accept another cancel request.")
            db.execute(
                "UPDATE candidate_executions SET cancel_requested=1,revision=revision+1,updated_at=? WHERE id=?",
                (max(now, row["updated_at"]), execution_id),
            )
            _, changed = self._row(db, p)
            assert changed is not None
            self._audit(db, p, "candidate_execution_cancel", changed)
        return self.get(project_id=project_id, admin_token=admin_token, job_id=job_id)

    def cleanup_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        execution_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        p = self.core._validated_payload(
            _Action,
            dict(
                project_id=project_id,
                admin_token=admin_token,
                job_id=job_id,
                execution_id=execution_id,
                expected_revision=expected_revision,
            ),
        )
        with self.jobs._transaction(
            p, write=True, operation="candidate_execution_cleanup_intent"
        ) as (db, now):
            _, row = self._action(db, p)
            proof = _load(row["proof_json"], 16384)
            if row["cleanup_attempted"] or row["phase"] == "finished":
                _error(
                    "cleanup_ineligible",
                    "Cleanup is one-shot and cannot release a finished execution.",
                )
            if now < max(row["updated_at"], proof["lease_expires_at"]):
                _error(
                    "lease_active", "Cleanup requires an expired, non-regressed execution lease."
                )
            if not row["create_reply_complete"] or not row["container_id"]:
                _error(
                    "cleanup_identity_unavailable",
                    "Cleanup requires an acknowledged full container identity.",
                )
            identity = {key: row[key] for key in ("container_id", "owner_nonce", "container_name")}
            identity["image_id"] = proof["image_id"]
            receipt = {
                "schema": "agentsync.candidate-cleanup.v1",
                "execution_id": execution_id,
                "container_id": row["container_id"],
                "status": "intent",
                "observation": None,
            }
            raw = _dump(receipt)
            db.execute(
                "UPDATE candidate_executions SET phase='unresolved',assessment='unverified',cleanup_attempted=1,cleanup_json=?,cleanup_sha256=?,revision=revision+1,updated_at=? WHERE id=?",
                (raw, _hash(raw), now, execution_id),
            )
            _, changed = self._row(db, p)
            assert changed is not None
            revision = changed["revision"]
            self._audit(db, p, "candidate_execution_cleanup_intent", changed)
        observed = _observation(identity)
        with self.jobs._transaction(
            p, write=True, operation="candidate_execution_cleanup_record"
        ) as (db, now):
            _, recorded = self._row(db, p)
            if (
                recorded is None
                or recorded["id"] != execution_id
                or recorded["revision"] != revision
            ):
                _error(
                    "version_conflict", "Cleanup observation lost its original execution revision."
                )
            receipt.update(status="observed", observation=observed)
            raw = _dump(receipt)
            if len(raw.encode()) > 16384:
                _error("invalid_backend_result", "Cleanup observation exceeds bounds.")
            db.execute(
                "UPDATE candidate_executions SET cleanup_json=?,cleanup_sha256=?,revision=revision+1,updated_at=? WHERE id=?",
                (raw, _hash(raw), max(now, recorded["updated_at"]), execution_id),
            )
            _, changed = self._row(db, p)
            assert changed is not None
            self._audit(db, p, "candidate_execution_cleanup_record", changed)
        return self.get(project_id=project_id, admin_token=admin_token, job_id=job_id)

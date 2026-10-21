"""Owner-authorized job ledger only: no executable worker or verified outcomes.

Internal attempt methods are trusted in-process capabilities. They are not
registered in Core/HTTP/MCP/CLI dispatch and never accept submitted test results.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import sqlite3
import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentsync.errors import AgentSyncError
from agentsync.models import AdminAuth, CommitSHA, StrictModel
from agentsync.storage.database import connect
from agentsync.verification.docker import DockerProfile

if TYPE_CHECKING:
    from agentsync.core.service import Core

from pydantic import Field


class _Enqueue(AdminAuth):
    snapshot_id: str = Field(min_length=1, max_length=200)
    expected_commit: CommitSHA
    request_id: str = Field(min_length=1, max_length=200)


class _Lookup(AdminAuth):
    job_id: str = Field(min_length=1, max_length=200)


class _Cancel(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 3)
    request_id: str = Field(min_length=1, max_length=200)


class _Page(AdminAuth):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class _Claim(StrictModel):
    project_id: str = Field(min_length=1, max_length=200)
    job_id: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=1, le=2**63 - 3)
    lease_seconds: int = Field(default=300, ge=1, le=3600)


class _Attempt(_Claim):
    attempt_id: str = Field(min_length=1, max_length=200)
    attempt_number: int = Field(ge=1, le=2**63 - 3)
    lease_token: str = Field(min_length=1, max_length=200)


def _error(code: str, message: str, status: int = 409) -> None:
    raise AgentSyncError(code, message, status)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "id",
            "project_id",
            "snapshot_id",
            "commit_sha",
            "profile_kind",
            "profile_sha256",
            "status",
            "version",
            "attempt_number",
            "current_attempt_id",
            "created_at",
            "updated_at",
        )
    } | {"execution_connected": False, "execution_assessment": "unverified"}


class VerificationJobs:
    def __init__(self, core: Core):
        self.core = core

    @staticmethod
    def _job(db: sqlite3.Connection, p: dict[str, Any]) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM verification_jobs WHERE id=? AND project_id=?",
            (p["job_id"], p["project_id"]),
        ).fetchone()
        if row is None:
            _error("not_found", "Verification job not found.", 404)
        assert row is not None
        return row

    @staticmethod
    def _version(row: sqlite3.Row, p: dict[str, Any], now: float) -> None:
        if now < row["updated_at"]:
            _error("clock_regressed", "Clock moved backwards; explicit recovery is required.")
        if row["version"] != p["expected_version"]:
            _error("version_conflict", "Verification job version changed.")

    def _transaction(
        self,
        operation: str,
        p: dict[str, Any],
        function: Callable[[sqlite3.Connection, float], dict[str, Any]],
        *,
        owner: bool,
        mutation: bool = True,
    ) -> dict[str, Any]:
        db = connect(self.core.db_path)
        actor = None
        try:
            db.execute("BEGIN IMMEDIATE" if mutation else "BEGIN")
            now = time.time()
            if not math.isfinite(now):
                _error("invalid_clock", "A finite service clock is required.")
            if owner:
                self.core._authenticate_owner(db, p)
                actor = (p["project_id"], "owner", p["project_id"])
            response = function(db, now)
            if mutation:
                actor = actor or (
                    p["project_id"],
                    "verification_worker",
                    response["current_attempt_id"],
                )
                self.core._audit_event(db, *actor, operation, p, "success", "ok", response)
            db.commit()
            return response
        except AgentSyncError as exc:
            db.rollback()
            if owner:
                self.core._audit_denial(actor, operation, p, exc.code)
            raise
        except (sqlite3.Error, UnicodeError):
            db.rollback()
            raise AgentSyncError(
                "storage_error", "Verification ledger operation failed.", 503
            ) from None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _payload(self, schema: type[StrictModel], p: dict[str, Any]) -> dict[str, Any]:
        return self.core._validated_payload(schema, p)

    def _request(
        self, db: sqlite3.Connection, operation: str, p: dict[str, Any], binding: dict[str, Any]
    ) -> sqlite3.Row | None:
        cached = db.execute(
            "SELECT * FROM verification_requests WHERE project_id=? AND operation=? AND request_id=?",
            (p["project_id"], operation, p["request_id"]),
        ).fetchone()
        if cached is not None:
            if not hmac.compare_digest(cached["payload_hash"], _hash(_canonical(binding))):
                _error(
                    "idempotency_conflict", "Request ID is bound to different verification inputs."
                )
            return self._job(db, {**p, "job_id": cached["job_id"]})
        return None

    @staticmethod
    def _remember(
        db: sqlite3.Connection,
        operation: str,
        p: dict[str, Any],
        binding: dict[str, Any],
        job_id: str,
    ) -> None:
        db.execute(
            "INSERT INTO verification_requests VALUES(?,?,?,?,?)",
            (p["project_id"], operation, p["request_id"], _hash(_canonical(binding)), job_id),
        )

    def enqueue(
        self,
        *,
        project_id: str,
        admin_token: str,
        snapshot_id: str,
        expected_commit: str,
        profile: DockerProfile,
        request_id: str,
    ) -> dict[str, Any]:
        p = self._payload(
            _Enqueue,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "snapshot_id": snapshot_id,
                "expected_commit": expected_commit,
                "request_id": request_id,
            },
        )
        p["expected_commit"] = p["expected_commit"].lower()

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            if type(profile) is not DockerProfile:
                _error("invalid_profile", "A trusted immutable DockerProfile is required.", 400)
            binding = {
                "snapshot_id": p["snapshot_id"],
                "commit_sha": p["expected_commit"],
                "profile_kind": profile.profile_id,
                "profile_sha256": profile.sha256,
            }
            cached = self._request(db, "verification_enqueue", p, binding)
            if cached is not None:
                return _public(cached)
            snapshot = db.execute(
                "SELECT receipt FROM repository_snapshots WHERE id=? AND project_id=?",
                (p["snapshot_id"], p["project_id"]),
            ).fetchone()
            if snapshot is None:
                _error("not_found", "Repository snapshot not found.", 404)
            receipt = json.loads(snapshot["receipt"])
            if receipt.get("base_sha") != p["expected_commit"]:
                _error("stale_snapshot", "Commit does not match the captured snapshot.")
            job_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO verification_jobs VALUES(?,?,?,?,?,?,'queued',1,0,NULL,?,?)",
                (
                    job_id,
                    p["project_id"],
                    p["snapshot_id"],
                    p["expected_commit"],
                    profile.profile_id,
                    profile.sha256,
                    now,
                    now,
                ),
            )
            self._remember(db, "verification_enqueue", p, binding, job_id)
            return _public(self._job(db, {**p, "job_id": job_id}))

        return self._transaction("verification_enqueue", p, write, owner=True)

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self._payload(
            _Lookup, {"project_id": project_id, "admin_token": admin_token, "job_id": job_id}
        )
        return self._transaction(
            "verification_get",
            p,
            lambda db, _: _public(self._job(db, p)),
            owner=True,
            mutation=False,
        )

    def list(
        self, *, project_id: str, admin_token: str, limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        p = self._payload(
            _Page,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "limit": limit,
                "offset": offset,
            },
        )

        def read(db: sqlite3.Connection, _: float) -> dict[str, Any]:
            rows = db.execute(
                "SELECT * FROM verification_jobs WHERE project_id=? ORDER BY created_at,id LIMIT ? OFFSET ?",
                (project_id, limit + 1, offset),
            ).fetchall()
            return {
                "jobs": [_public(row) for row in rows[:limit]],
                "has_more": len(rows) > limit,
                "execution_connected": False,
                "execution_assessment": "unverified",
            }

        return self._transaction("verification_list", p, read, owner=True, mutation=False)

    def cancel(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        request_id: str,
    ) -> dict[str, Any]:
        p = self._payload(
            _Cancel,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
                "request_id": request_id,
            },
        )
        binding = {"job_id": job_id, "expected_version": expected_version}

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            cached = self._request(db, "verification_cancel", p, binding)
            if cached is not None:
                return _public(cached)
            job = self._job(db, p)
            self._version(job, p, now)
            if job["status"] not in {"queued", "running"}:
                _error("invalid_transition", "Job cannot be cancelled from its current state.")
            status = "cancelled" if job["status"] == "queued" else "cancel_requested"
            db.execute(
                "UPDATE verification_jobs SET status=?,version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (status, now, job_id, project_id, expected_version),
            )
            if status == "cancel_requested":
                db.execute(
                    "UPDATE verification_attempts SET status='cancel_requested',reason_code='owner_cancelled',updated_at=? WHERE id=? AND project_id=?",
                    (now, job["current_attempt_id"], project_id),
                )
            self._remember(db, "verification_cancel", p, binding, job_id)
            return _public(self._job(db, p))

        return self._transaction("verification_cancel", p, write, owner=True)

    def claim(
        self, *, project_id: str, job_id: str, expected_version: int, lease_seconds: int = 300
    ) -> dict[str, Any]:
        """Trusted in-process lease capability; does not start execution."""
        p = self._payload(
            _Claim,
            {
                "project_id": project_id,
                "job_id": job_id,
                "expected_version": expected_version,
                "lease_seconds": lease_seconds,
            },
        )
        token = secrets.token_urlsafe(32)

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self._job(db, p)
            self._version(job, p, now)
            if job["status"] != "queued":
                _error("invalid_transition", "Only queued jobs can be claimed.")
            attempt_id = str(uuid.uuid4())
            count = db.execute(
                "UPDATE verification_jobs SET status='running',version=version+1,attempt_number=attempt_number+1,current_attempt_id=?,updated_at=? WHERE id=? AND project_id=? AND version=? AND status='queued'",
                (attempt_id, now, job_id, project_id, expected_version),
            ).rowcount
            if count != 1:
                _error("version_conflict", "Verification claim lost a concurrent update.")
            db.execute(
                "INSERT INTO verification_attempts VALUES(?,?,?,?,?,?,'running','',?,?)",
                (
                    attempt_id,
                    project_id,
                    job_id,
                    job["attempt_number"] + 1,
                    _hash(token),
                    now + lease_seconds,
                    now,
                    now,
                ),
            )
            return _public(self._job(db, p)) | {
                "lease_token": token,
                "lease_expires_at": now + lease_seconds,
            }

        return self._transaction("verification_claim", p, write, owner=False)

    def _attempt_change(self, operation: str, p: dict[str, Any]) -> dict[str, Any]:
        p = self._payload(_Attempt, p)

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self._job(db, p)
            self._version(job, p, now)
            attempt = db.execute(
                "SELECT * FROM verification_attempts WHERE id=? AND project_id=? AND job_id=?",
                (p["attempt_id"], p["project_id"], p["job_id"]),
            ).fetchone()
            if (
                attempt is None
                or job["current_attempt_id"] != p["attempt_id"]
                or job["attempt_number"] != p["attempt_number"]
                or not hmac.compare_digest(attempt["token_hash"], _hash(p["lease_token"]))
            ):
                _error("lease_denied", "Attempt lease does not belong to this holder.", 403)
            if now < attempt["updated_at"]:
                _error("clock_regressed", "Clock moved backwards; explicit recovery is required.")
            if attempt["lease_expires_at"] <= now:
                _error("lease_expired", "Verification lease expired.")
            if operation == "verification_renew":
                if job["status"] != "running" or attempt["status"] != "running":
                    _error("invalid_transition", "Attempt is not renewable.")
                db.execute(
                    "UPDATE verification_attempts SET lease_expires_at=?,updated_at=? WHERE id=? AND project_id=?",
                    (now + p["lease_seconds"], now, attempt["id"], p["project_id"]),
                )
            else:
                required = (
                    "cancel_requested" if operation == "verification_ack_cancel" else "running"
                )
                if job["status"] != required or attempt["status"] != required:
                    _error("invalid_transition", "Attempt transition is not permitted.")
                status = "cancelled" if operation == "verification_ack_cancel" else "interrupted"
                reason = "owner_cancelled" if status == "cancelled" else "service_interrupted"
                db.execute(
                    "UPDATE verification_attempts SET status=?,reason_code=?,token_hash='',updated_at=? WHERE id=? AND project_id=?",
                    (status, reason, now, attempt["id"], p["project_id"]),
                )
                db.execute(
                    "UPDATE verification_jobs SET status=? WHERE id=? AND project_id=?",
                    (status, p["job_id"], p["project_id"]),
                )
            db.execute(
                "UPDATE verification_jobs SET version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (now, p["job_id"], p["project_id"], p["expected_version"]),
            )
            response = _public(self._job(db, p))
            if operation == "verification_renew":
                response["lease_expires_at"] = now + p["lease_seconds"]
            return response

        return self._transaction(operation, p, write, owner=False)

    def renew(self, **payload: Any) -> dict[str, Any]:
        return self._attempt_change("verification_renew", payload)

    def acknowledge_cancel(self, **payload: Any) -> dict[str, Any]:
        return self._attempt_change("verification_ack_cancel", payload)

    def interrupt(self, **payload: Any) -> dict[str, Any]:
        return self._attempt_change("verification_interrupt", payload)

    def recover_interrupted(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        request_id: str,
    ) -> dict[str, Any]:
        """Explicit owner recovery of a non-executing ledger, including expired leases.

        Future Docker wiring must add cleanup reconciliation before enabling this
        transition for executable attempts. No success or retry is inferred here.
        """
        p = self._payload(
            _Cancel,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
                "request_id": request_id,
            },
        )
        binding = {"job_id": job_id, "expected_version": expected_version}

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            cached = self._request(db, "verification_interrupt", p, binding)
            if cached is not None:
                return _public(cached)
            job = self._job(db, p)
            if job["version"] != expected_version:
                _error("version_conflict", "Verification job version changed.")
            if job["status"] not in {"running", "cancel_requested"}:
                _error("invalid_transition", "Only active ledger attempts need recovery.")
            attempt = db.execute(
                "SELECT * FROM verification_attempts WHERE id=? AND project_id=? AND job_id=?",
                (job["current_attempt_id"], project_id, job_id),
            ).fetchone()
            if attempt is None:
                _error("invalid_transition", "Current attempt is missing.")
            reason = (
                "lease_expired" if now >= attempt["lease_expires_at"] else "service_interrupted"
            )
            # Explicit owner interruption can recover clock rollback; retain the
            # last observed timestamp instead of claiming the clock is monotonic.
            timestamp = max(now, job["updated_at"], attempt["updated_at"])
            db.execute(
                "UPDATE verification_attempts SET status='interrupted',reason_code=?,token_hash='',updated_at=? WHERE id=? AND project_id=?",
                (reason, timestamp, job["current_attempt_id"], project_id),
            )
            db.execute(
                "UPDATE verification_jobs SET status='interrupted',version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (timestamp, job_id, project_id, expected_version),
            )
            self._remember(db, "verification_interrupt", p, binding, job_id)
            return _public(self._job(db, p))

        return self._transaction("verification_interrupt", p, write, owner=True)

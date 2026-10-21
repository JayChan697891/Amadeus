"""Trusted single snapshot execution; no remote dispatch, retry, apply or task review."""

from __future__ import annotations

import hashlib
import hmac
import json
import platform
import re
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from agentsync.errors import AgentSyncError
from agentsync.verification import docker as docker_backend
from agentsync.verification.docker import (
    CONTAINER_ID,
    DockerProfile,
    VerificationResult,
    verify_python_json_lines,
)
from agentsync.verification.jobs import (
    VerificationJobs,
    _Cancel,
    _canonical,
    _error,
    _hash,
    _Lookup,
    execution_summary,
)
from agentsync.verification.snapshot import CandidateSnapshot, export_candidate

if TYPE_CHECKING:
    from agentsync.core.service import Core

LEASE_SECONDS = 300
ISOLATION_CHECKS = frozenset(
    {
        "owner",
        "image",
        "user",
        "environment",
        "entrypoint",
        "command",
        "workdir",
        "healthcheck",
        "network",
        "readonly",
        "privileged",
        "capabilities",
        "security",
        "namespaces",
        "mounts",
        "resources",
        "tmpfs",
        "groups",
        "logs",
    }
)


class _Execute(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 3)


@dataclass
class _Capability:
    project_id: str
    job_id: str
    attempt_id: str
    token: str
    version: int
    execution_id: str
    profile: DockerProfile


class _Lifecycle:
    def __init__(self, executor: OwnerVerificationExecutor, capability: _Capability):
        self.executor, self.capability = executor, capability

    def before_create(self, owner: str, container_name: str) -> None:
        if (
            not re.fullmatch(r"[0-9a-f]{32}", owner)
            or container_name != "agentsync-verifier-" + owner
        ):
            _error("lifecycle_error", "Invalid trusted container identity.")
        self.executor._advance(
            self.capability,
            "execution_create_intent",
            "preparing",
            {
                "phase": "create_intent",
                "owner_nonce": owner,
                "container_name": container_name,
                "create_intent": 1,
            },
        )

    def created(self, container_id: str) -> None:
        if not CONTAINER_ID.fullmatch(container_id):
            _error("lifecycle_error", "Invalid full container identity.")
        self.executor._advance(
            self.capability,
            "execution_created",
            "create_intent",
            {
                "phase": "created",
                "container_id": container_id,
                "create_reply_complete": 1,
            },
        )

    def before_start(self) -> None:
        self.executor._advance(
            self.capability,
            "execution_start",
            "created",
            {"phase": "executing", "start_intent": 1},
            minimum_remaining=self.capability.profile.timeout_seconds + 30,
        )


class OwnerVerificationExecutor:
    def __init__(self, core: Core):
        self.core, self.jobs = core, VerificationJobs(core)

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        value = self.jobs.get(project_id=project_id, admin_token=admin_token, job_id=job_id)
        if not value["execution_connected"]:
            _error("not_found", "Job has no execution.", 404)
        return self._projection(value)

    @staticmethod
    def _projection(value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "id": value["execution_id"], "job_id": value["id"]}

    def _claim(
        self, payload: dict[str, Any], profile: DockerProfile
    ) -> tuple[_Capability, dict[str, Any]]:
        p = self.jobs._payload(_Execute, payload)
        token = secrets.token_urlsafe(32)
        captured: dict[str, Any] = {}

        def claim(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self.jobs._job(db, p)
            self.jobs._version(job, p, now)
            if (
                type(profile) is not DockerProfile
                or profile.sha256 != job["profile_sha256"]
                or profile.profile_id != job["profile_kind"]
            ):
                _error("profile_mismatch", "Trusted profile does not match the queued job.")
            if (
                job["status"] != "queued"
                or db.execute(
                    "SELECT 1 FROM verification_executions WHERE job_id=? AND project_id=?",
                    (job["id"], p["project_id"]),
                ).fetchone()
            ):
                _error("invalid_transition", "Only an unattached queued job can execute.")
            snapshot = db.execute(
                "SELECT receipt FROM repository_snapshots WHERE id=? AND project_id=?",
                (job["snapshot_id"], p["project_id"]),
            ).fetchone()
            if snapshot is None:
                _error("not_found", "Repository snapshot not found.", 404)
            receipt = json.loads(snapshot["receipt"])
            if not isinstance(receipt, dict) or receipt.get("base_sha") != job["commit_sha"]:
                _error("stale_snapshot", "Snapshot no longer matches the pinned commit.")
            attempt_id, execution_id = str(uuid.uuid4()), str(uuid.uuid4())
            count = db.execute(
                "UPDATE verification_jobs SET status='running',version=version+1,attempt_number=attempt_number+1,current_attempt_id=?,updated_at=? WHERE id=? AND project_id=? AND status='queued' AND version=?",
                (attempt_id, now, job["id"], p["project_id"], p["expected_version"]),
            ).rowcount
            if count != 1:
                _error("version_conflict", "Execution claim lost a concurrent update.")
            db.execute(
                "INSERT INTO verification_attempts VALUES(?,?,?,?,?,?,'running','',?,?)",
                (
                    attempt_id,
                    p["project_id"],
                    job["id"],
                    job["attempt_number"] + 1,
                    _hash(token),
                    now + LEASE_SECONDS,
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO verification_executions(id,project_id,job_id,attempt_id,attempt_number,claim_version,revision,phase,assessment,create_intent,create_reply_complete,cleanup_confirmed,execution_started,profile_sha256,image_id,result_json,error_code,created_at,updated_at) VALUES(?,?,?,?,?,?,1,'preparing','unverified',0,0,0,0,?,?,'{}','',?,?)",
                (
                    execution_id,
                    p["project_id"],
                    job["id"],
                    attempt_id,
                    job["attempt_number"] + 1,
                    job["version"] + 1,
                    profile.sha256,
                    profile.image_id,
                    now,
                    now,
                ),
            )
            captured.update(
                receipt=receipt,
                commit_sha=job["commit_sha"],
                attempt_id=attempt_id,
                execution_id=execution_id,
            )
            return execution_summary(db, self.jobs._job(db, p))

        response = self.jobs._transaction("execution_claim", p, claim, owner=True)
        return _Capability(
            p["project_id"],
            p["job_id"],
            captured["attempt_id"],
            token,
            response["version"],
            captured["execution_id"],
            profile,
        ), captured

    def _fence(
        self, db: sqlite3.Connection, cap: _Capability, now: float, *, allow_cancel: bool = False
    ) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row, bool]:
        job = self.jobs._job(db, {"project_id": cap.project_id, "job_id": cap.job_id})
        attempt = db.execute(
            "SELECT * FROM verification_attempts WHERE id=? AND project_id=? AND job_id=?",
            (cap.attempt_id, cap.project_id, cap.job_id),
        ).fetchone()
        execution = db.execute(
            "SELECT * FROM verification_executions WHERE id=? AND project_id=? AND job_id=? AND attempt_id=?",
            (cap.execution_id, cap.project_id, cap.job_id, cap.attempt_id),
        ).fetchone()
        if (
            attempt is None
            or execution is None
            or job["current_attempt_id"] != cap.attempt_id
            or attempt["attempt_number"] != job["attempt_number"]
            or not hmac.compare_digest(attempt["token_hash"], _hash(cap.token))
        ):
            _error("lease_denied", "Execution capability no longer owns this attempt.", 403)
        if now < max(job["updated_at"], attempt["updated_at"], execution["updated_at"]):
            _error("clock_regressed", "Clock rollback prevents execution progress.")
        if now >= attempt["lease_expires_at"]:
            _error("lease_expired", "Execution lease expired.")
        cancelled = execution["cancel_version"] is not None
        cancel_only = (
            cancelled
            and execution["cancel_version"] == cap.version + 1
            and job["version"] == cap.version + 1
        )
        if job["version"] != cap.version and not (allow_cancel and cancel_only):
            _error("version_conflict", "Execution capability was superseded.")
        if cancelled and allow_cancel and not cancel_only:
            _error("version_conflict", "Cancellation does not match the claimed revision.")
        if cancelled and not allow_cancel:
            _error("execution_cancelled", "Execution cancellation was requested.")
        if job["status"] not in {"running", "cancel_requested"} or attempt["status"] not in {
            "running",
            "cancel_requested",
        }:
            _error("invalid_transition", "Execution is not active.")
        return job, attempt, execution, cancelled

    def _advance(
        self,
        cap: _Capability,
        operation: str,
        expected_phase: str,
        values: dict[str, Any],
        *,
        minimum_remaining: float = 0,
    ) -> None:
        p = {"project_id": cap.project_id, "job_id": cap.job_id, "expected_version": cap.version}

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job, attempt, execution, _ = self._fence(db, cap, now)
            if (
                execution["phase"] != expected_phase
                or attempt["lease_expires_at"] - now < minimum_remaining
            ):
                _error("lifecycle_error", "Execution phase or remaining lease is insufficient.")
            if not set(values) <= {
                "phase",
                "owner_nonce",
                "container_name",
                "create_intent",
                "container_id",
                "create_reply_complete",
                "tree_sha",
                "source_sha256",
                "input_sha256",
                "start_intent",
            }:
                _error("lifecycle_error", "Unsupported internal execution update.")
            assignments = ",".join(key + "=?" for key in values)
            db.execute(
                f"UPDATE verification_executions SET {assignments},revision=revision+1,updated_at=? WHERE id=? AND project_id=?",
                (*values.values(), now, cap.execution_id, cap.project_id),
            )
            db.execute(
                "UPDATE verification_jobs SET version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (now, cap.job_id, cap.project_id, job["version"]),
            )
            db.execute(
                "UPDATE verification_attempts SET updated_at=? WHERE id=? AND project_id=?",
                (now, cap.attempt_id, cap.project_id),
            )
            return execution_summary(db, self.jobs._job(db, p))

        response = self.jobs._transaction(operation, p, write, owner=False)
        cap.version = response["version"]

    def cancel(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        request_id: str,
    ) -> dict[str, Any]:
        p = self.jobs._payload(
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
            cached = self.jobs._request(db, "execution_cancel", p, binding)
            if cached is not None:
                return execution_summary(db, cached)
            job = self.jobs._job(db, p)
            self.jobs._version(job, p, now)
            execution = db.execute(
                "SELECT * FROM verification_executions WHERE job_id=? AND project_id=?",
                (job_id, project_id),
            ).fetchone()
            if execution is None:
                _error("not_found", "Job has no execution.", 404)
            if (
                job["status"] != "running"
                or execution["phase"] in {"finished", "cleanup_pending"}
                or execution["cancel_version"] is not None
            ):
                _error("invalid_transition", "Execution cannot be cancelled from this state.")
            db.execute(
                "UPDATE verification_jobs SET status='cancel_requested',version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (now, job_id, project_id, expected_version),
            )
            db.execute(
                "UPDATE verification_attempts SET status='cancel_requested',reason_code='owner_cancelled',updated_at=? WHERE id=? AND project_id=?",
                (now, execution["attempt_id"], project_id),
            )
            db.execute(
                "UPDATE verification_executions SET cancel_version=?,revision=revision+1,updated_at=? WHERE id=? AND project_id=?",
                (expected_version + 1, now, execution["id"], project_id),
            )
            self.jobs._remember(db, "execution_cancel", p, binding, job_id)
            return execution_summary(db, self.jobs._job(db, p))

        return self._projection(self.jobs._transaction("execution_cancel", p, write, owner=True))

    @staticmethod
    def _safe_result(result: VerificationResult) -> dict[str, Any]:
        if type(result) is not VerificationResult:
            _error("invalid_backend_result", "Trusted verifier returned an invalid result.")
        if result.status not in {"passed", "failed", "unsupported", "error"}:
            _error("invalid_backend_result", "Trusted verifier returned an unknown outcome.")
        allowed = {
            "provenance",
            "backend",
            "verifier_version",
            "verifier_source_sha256",
            "execution_started",
            "profile_id",
            "profile_sha256",
            "cases_sha256",
            "image_sha256",
            "input_sha256",
            "source_sha256",
            "commit_sha",
            "tree_sha",
            "platform",
            "kernel",
            "expected_case_count",
            "completed_case_count",
            "checked_case_count",
            "passed_case_count",
            "candidate_exit_code",
            "cleanup_confirmed",
            "errors",
            "started_at",
            "finished_at",
            "elapsed_seconds",
            "docker_server_version",
            "cgroup_version",
            "container_id",
            "isolation",
            "container_state",
            "stdout_sha256",
            "stdout_bytes",
            "stderr_bytes",
            "effective_isolation_checks",
            "effective_isolation_summary",
        }
        safe = {key: value for key, value in result.evidence.items() if key in allowed}
        # Backend fields are trusted fixed-schema metadata, not submitted output.
        encoded = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode()) > 64 * 1024:
            _error("invalid_backend_result", "Trusted verifier result exceeds evidence bounds.")
        return json.loads(encoded) | {"status": result.status}

    def _finish(
        self, cap: _Capability, result: VerificationResult, exported: CandidateSnapshot | None
    ) -> dict[str, Any]:
        safe = self._safe_result(result)
        p = {"project_id": cap.project_id, "job_id": cap.job_id, "expected_version": cap.version}

        def finish(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job, _, execution, cancelled = self._fence(db, cap, now, allow_cancel=True)
            pending = bool(
                execution["create_intent"]
                and (
                    not execution["create_reply_complete"]
                    or safe.get("cleanup_confirmed") is not True
                    or safe.get("provenance") != "docker_black_box"
                )
            )
            assessment = "unverified" if pending else "cancelled" if cancelled else result.status
            if assessment not in {
                "unverified",
                "cancelled",
                "passed",
                "failed",
                "unsupported",
                "error",
            }:
                _error("invalid_backend_result", "Unsupported trusted verifier outcome.")
            if assessment == "passed":
                binding = exported is not None and all(
                    (
                        safe.get("commit_sha") == job["commit_sha"] == exported.commit_sha,
                        safe.get("tree_sha") == execution["tree_sha"] == exported.tree_sha,
                        safe.get("input_sha256")
                        == execution["input_sha256"]
                        == exported.input_sha256,
                        safe.get("source_sha256")
                        == execution["source_sha256"]
                        == hashlib.sha256(exported.source).hexdigest(),
                        safe.get("profile_sha256")
                        == execution["profile_sha256"]
                        == job["profile_sha256"]
                        == cap.profile.sha256,
                        job["profile_kind"] == cap.profile.profile_id,
                        safe.get("image_sha256") == execution["image_id"] == cap.profile.image_id,
                    )
                )
                counts = [
                    safe.get(key)
                    for key in (
                        "expected_case_count",
                        "completed_case_count",
                        "checked_case_count",
                        "passed_case_count",
                    )
                ]
                checks = safe.get("isolation", {}).get("checks", {})
                if not (
                    binding
                    and safe.get("provenance") == "docker_black_box"
                    and safe.get("backend") == "local-linux-docker"
                    and safe.get("profile_id") == cap.profile.profile_id
                    and type(safe.get("verifier_version")) is int
                    and safe.get("verifier_version") == 1
                    and safe.get("verifier_source_sha256")
                    == hashlib.sha256(Path(docker_backend.__file__).read_bytes()).hexdigest()
                    and safe.get("execution_started") is True
                    and safe.get("cleanup_confirmed") is True
                    and execution["create_reply_complete"] == 1
                    and execution["phase"] == "executing"
                    and counts == [len(cap.profile.cases)] * 4
                    and all(type(v) is int for v in counts)
                    and type(safe.get("candidate_exit_code")) is int
                    and safe.get("candidate_exit_code") == 0
                    and safe.get("errors") == []
                    and safe.get("container_id") == execution["container_id"]
                    and isinstance(checks, dict)
                    and set(checks) == ISOLATION_CHECKS
                    and all(value is True for value in checks.values())
                ):
                    _error(
                        "invalid_backend_result",
                        "Verifier evidence does not match the active execution.",
                    )
            phase = "cleanup_pending" if pending else "finished"
            status = "cleanup_pending" if pending else "cancelled" if cancelled else "finished"
            reason = (
                "cleanup_uncertain"
                if pending
                else "owner_cancelled"
                if cancelled
                else "executor_finished"
            )
            encoded = _canonical(safe)
            errors = safe.get("errors") or []
            error = (
                errors[0]
                if errors
                and isinstance(errors[0], str)
                and re.fullmatch(r"[a-z_]{1,64}", errors[0])
                else ""
            )
            db.execute(
                "UPDATE verification_executions SET phase=?,assessment=?,cleanup_confirmed=?,execution_started=?,result_json=?,result_sha256=?,error_code=?,revision=revision+1,updated_at=? WHERE id=? AND project_id=?",
                (
                    phase,
                    assessment,
                    int(
                        not pending
                        and (
                            not execution["create_intent"] or safe.get("cleanup_confirmed") is True
                        )
                    ),
                    int(safe.get("execution_started") is True),
                    encoded,
                    _hash(encoded),
                    error,
                    now,
                    cap.execution_id,
                    cap.project_id,
                ),
            )
            db.execute(
                "UPDATE verification_jobs SET status=?,version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (status, now, cap.job_id, cap.project_id, job["version"]),
            )
            db.execute(
                "UPDATE verification_attempts SET status=?,reason_code=?,token_hash='',updated_at=? WHERE id=? AND project_id=?",
                (status, reason, now, cap.attempt_id, cap.project_id),
            )
            return execution_summary(db, self.jobs._job(db, p))

        return self._projection(self.jobs._transaction("execution_finish", p, finish, owner=False))

    @staticmethod
    def _failure(code: str, status: str = "error") -> VerificationResult:
        return VerificationResult(
            status,
            {
                "provenance": "executor_preflight",
                "execution_started": False,
                "cleanup_confirmed": True,
                "errors": [code],
            },
        )

    def _pending(self, cap: _Capability, result: VerificationResult | None = None) -> None:
        """May quarantine only this still-owned attempt; never reacquires success authority."""
        p = {"project_id": cap.project_id, "job_id": cap.job_id}
        observation = None
        if result is not None:
            try:
                observation = _canonical(self._safe_result(result) | {"observation_only": True})
            except Exception:
                pass

        def write(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self.jobs._job(db, p)
            attempt = db.execute(
                "SELECT * FROM verification_attempts WHERE id=? AND project_id=? AND job_id=?",
                (cap.attempt_id, cap.project_id, cap.job_id),
            ).fetchone()
            execution = db.execute(
                "SELECT * FROM verification_executions WHERE id=? AND project_id=? AND job_id=? AND attempt_id=?",
                (cap.execution_id, cap.project_id, cap.job_id, cap.attempt_id),
            ).fetchone()
            if (
                attempt is None
                or execution is None
                or job["current_attempt_id"] != cap.attempt_id
                or not hmac.compare_digest(attempt["token_hash"], _hash(cap.token))
                or execution["phase"] == "finished"
            ):
                _error("lease_denied", "Cannot quarantine a different or finished attempt.", 403)
            timestamp = max(now, job["updated_at"], execution["updated_at"], attempt["updated_at"])
            db.execute(
                "UPDATE verification_executions SET phase='cleanup_pending',assessment='unverified',cleanup_confirmed=0,error_code='execution_unresolved',revision=revision+1,updated_at=? WHERE id=? AND project_id=?",
                (timestamp, cap.execution_id, cap.project_id),
            )
            if observation is not None:
                observed = json.loads(observation)
                db.execute(
                    "UPDATE verification_executions SET result_json=?,result_sha256=?,execution_started=? WHERE id=? AND project_id=?",
                    (
                        observation,
                        _hash(observation),
                        int(observed.get("execution_started") is True),
                        cap.execution_id,
                        cap.project_id,
                    ),
                )
            db.execute(
                "UPDATE verification_jobs SET status='cleanup_pending',version=version+1,updated_at=? WHERE id=? AND project_id=? AND version=?",
                (timestamp, cap.job_id, cap.project_id, job["version"]),
            )
            db.execute(
                "UPDATE verification_attempts SET status='cleanup_pending',reason_code='cleanup_uncertain',token_hash='',updated_at=? WHERE id=? AND project_id=?",
                (timestamp, cap.attempt_id, cap.project_id),
            )
            return execution_summary(db, self.jobs._job(db, p))

        self.jobs._transaction("execution_pending", p, write, owner=False)

    def execute_once(
        self,
        *,
        project_id: str,
        admin_token: str,
        job_id: str,
        expected_version: int,
        profile: DockerProfile,
    ) -> dict[str, Any]:
        cap, binding = self._claim(
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "job_id": job_id,
                "expected_version": expected_version,
            },
            profile,
        )
        exported = None
        try:
            if platform.system() != "Linux":
                result = self._failure("unsupported_platform", "unsupported")
            else:
                exported = export_candidate(
                    self.core._workspace_store(), binding["receipt"], binding["commit_sha"]
                )
                if exported.commit_sha != binding["commit_sha"]:
                    _error("snapshot_mismatch", "Exported commit does not match the queued job.")
                self._advance(
                    cap,
                    "execution_bind",
                    "preparing",
                    {
                        "tree_sha": exported.tree_sha,
                        "source_sha256": hashlib.sha256(exported.source).hexdigest(),
                        "input_sha256": exported.input_sha256,
                    },
                )
                result = verify_python_json_lines(
                    exported.source,
                    profile=profile,
                    input_sha256=exported.input_sha256,
                    commit_sha=exported.commit_sha,
                    tree_sha=exported.tree_sha,
                    _lifecycle=_Lifecycle(self, cap),
                )
        except AgentSyncError:
            result = self._failure("execution_preflight_failed")
        except Exception:
            result = self._failure("execution_infrastructure_error")
        try:
            return self._finish(cap, result, exported)
        except Exception:
            # No reloading of the latest version can restore completion authority.
            # A stale/crashed attempt stays unresolved; get projects expiry safely.
            try:
                self._pending(cap, result)
            except Exception:
                pass
            return self.get(project_id=project_id, admin_token=admin_token, job_id=job_id)

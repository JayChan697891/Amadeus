"""One-shot exact-container cleanup observations, never success or job recovery."""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import tempfile
import time
import uuid
from typing import TYPE_CHECKING, Any

from agentsync.verification import docker as docker_backend
from agentsync.verification.jobs import (
    VerificationJobs,
    _Cancel,
    _canonical,
    _error,
    _Lookup,
    execution_summary,
)

if TYPE_CHECKING:
    from agentsync.core.service import Core

_NONCE = re.compile(r"[a-f0-9]{32}")
_DAEMON = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,199}")


class _Replay(Exception):
    def __init__(self, response: dict[str, Any]):
        self.response = response


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _summary(db: sqlite3.Connection, job: sqlite3.Row) -> dict[str, Any]:
    result = execution_summary(db, job) | {"job_id": job["id"]}
    row = db.execute(
        "SELECT * FROM verification_reconciliations WHERE project_id=? AND job_id=?",
        (job["project_id"], job["id"]),
    ).fetchone()
    result["reconciliation"] = (
        None
        if row is None
        else {
            key: row[key]
            for key in (
                "id",
                "status",
                "outcome",
                "error_code",
                "observation_sha256",
                "created_at",
                "updated_at",
            )
        }
    )
    return result


def _observation(identity: dict[str, Any]) -> dict[str, Any]:
    """Private system seam; no candidate bytes, caller commands or broad deletion."""
    result: dict[str, Any] = {
        "protocol": "exact_container_cleanup_v1",
        "outcome": "unresolved",
        "error_code": "cleanup_unresolved",
        "identity_matched": False,
        "remove_acknowledged": False,
        "absence_observed": False,
        "daemon_consistent": False,
    }
    begin = time.monotonic()
    try:
        if not math.isfinite(begin):
            raise docker_backend._Failure("invalid_clock")
        cli = docker_backend._trusted_cli()
        with tempfile.TemporaryDirectory(prefix="agentsync-reconcile-config-") as config_dir:
            env = {"PATH": "/usr/bin:/bin", "HOME": config_dir, "LC_ALL": "C"}
            base = [cli, "--host", "unix:///var/run/docker.sock", "--config", config_dir]

            def daemon() -> str:
                info = docker_backend._inspect_json(
                    docker_backend._run(
                        [*base, "info", "--format", "{{json .}}"], env, 5, 256 * 1024
                    )
                )
                value = info.get("ID") if isinstance(info, dict) else None
                if not isinstance(info, dict) or info.get("OSType") != "linux":
                    raise docker_backend._Failure("daemon_identity_invalid")
                if not isinstance(value, str) or not _DAEMON.fullmatch(value):
                    raise docker_backend._Failure("daemon_identity_invalid")
                return value

            before = daemon()
            result["daemon_identity_sha256"] = _digest(before)
            inspected = docker_backend._inspect_json(
                docker_backend._run(
                    [*base, "inspect", identity["container_id"]], env, 5, 256 * 1024
                )
            )
            if not isinstance(inspected, list) or len(inspected) != 1:
                raise docker_backend._Failure("container_identity_mismatch")
            item = inspected[0]
            if not (
                isinstance(item, dict)
                and item.get("Id") == identity["container_id"]
                and item.get("Name") == "/" + identity["container_name"]
                and item.get("Image") == identity["image_id"]
                and isinstance(item.get("Config"), dict)
                and isinstance(item["Config"].get("Labels"), dict)
                and item["Config"]["Labels"].get(docker_backend.LABEL) == identity["owner_nonce"]
            ):
                raise docker_backend._Failure("container_identity_mismatch")
            result["identity_matched"] = True
            if daemon() != before:
                raise docker_backend._Failure("daemon_identity_changed")
            removed = docker_backend._run(
                [*base, "rm", "--force", identity["container_id"]], env, 5, 4096
            )
            if not (
                removed.returncode == 0
                and removed.stdout.decode("ascii", errors="strict").strip()
                == identity["container_id"]
            ):
                raise docker_backend._Failure("container_remove_unconfirmed")
            result["remove_acknowledged"] = True
            listed = docker_backend._run(
                [
                    *base,
                    "container",
                    "ls",
                    "--all",
                    "--no-trunc",
                    "--filter",
                    "id=" + identity["container_id"],
                    "--format",
                    "{{.ID}}",
                ],
                env,
                5,
                4096,
            )
            if listed.returncode != 0 or listed.stdout.strip():
                raise docker_backend._Failure("container_absence_unconfirmed")
            result["absence_observed"] = True
            if daemon() != before:
                raise docker_backend._Failure("daemon_identity_changed")
            end = time.monotonic()
            if not math.isfinite(end) or end < begin:
                raise docker_backend._Failure("clock_regressed")
            result["daemon_consistent"] = True
            result["outcome"] = "removed_and_absent"
            result["error_code"] = ""
    except docker_backend._Failure as exc:
        result["error_code"] = exc.code
    except Exception:
        result["error_code"] = "cleanup_infrastructure_error"
    return result


class OwnerExecutionReconciler:
    """Trusted internal owner library. A cleanup receipt never releases a job."""

    def __init__(self, core: Core):
        self.core = core
        self.jobs = VerificationJobs(core)

    def get(self, *, project_id: str, admin_token: str, job_id: str) -> dict[str, Any]:
        p = self.jobs._payload(
            _Lookup, {"project_id": project_id, "admin_token": admin_token, "job_id": job_id}
        )
        return self.jobs._transaction(
            "execution_reconciliation_get",
            p,
            lambda db, now: _summary(db, self.jobs._job(db, p)),
            owner=True,
            mutation=False,
        )

    def reconcile_once(
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
        binding = _digest(
            _canonical({key: value for key, value in p.items() if key != "admin_token"})
        )
        captured: dict[str, Any] = {}

        def claim(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self.jobs._job(db, p)
            previous = db.execute(
                "SELECT * FROM verification_reconciliations WHERE project_id=? AND request_id=?",
                (project_id, request_id),
            ).fetchone()
            if previous is not None:
                if previous["job_id"] != job_id or previous["payload_hash"] != binding:
                    _error("idempotency_conflict", "Request identity has another binding.")
                raise _Replay(_summary(db, job))
            if db.execute(
                "SELECT 1 FROM verification_reconciliations WHERE project_id=? AND job_id=?",
                (project_id, job_id),
            ).fetchone():
                _error("reconciliation_already_attempted", "Cleanup was already attempted.")
            self.jobs._version(job, p, now)
            execution = db.execute(
                "SELECT * FROM verification_executions WHERE project_id=? AND job_id=?",
                (project_id, job_id),
            ).fetchone()
            attempt = db.execute(
                "SELECT * FROM verification_attempts WHERE project_id=? AND job_id=? AND id=?",
                (project_id, job_id, job["current_attempt_id"]),
            ).fetchone()
            if (
                execution is None
                or attempt is None
                or not (
                    execution["attempt_id"] == attempt["id"]
                    and execution["attempt_number"]
                    == attempt["attempt_number"]
                    == job["attempt_number"]
                    and job["status"] in {"running", "cancel_requested", "cleanup_pending"}
                    and attempt["status"] in {"running", "cancel_requested", "cleanup_pending"}
                    and execution["phase"] != "finished"
                )
            ):
                _error("reconciliation_ineligible", "Execution has no eligible current attempt.")
            timestamps = (
                job["updated_at"],
                attempt["updated_at"],
                execution["updated_at"],
                attempt["lease_expires_at"],
            )
            if not all(math.isfinite(value) for value in timestamps):
                _error("invalid_clock", "Finite execution timestamps are required.")
            if now < max(timestamps[:3]):
                _error("clock_regressed", "Clock rollback prevents cleanup progress.")
            if now < attempt["lease_expires_at"]:
                _error("lease_active", "Execution lease has not expired.")
            if not (
                execution["create_intent"] == 1
                and execution["create_reply_complete"] == 1
                and isinstance(execution["container_id"], str)
                and docker_backend.CONTAINER_ID.fullmatch(execution["container_id"])
                and isinstance(execution["owner_nonce"], str)
                and _NONCE.fullmatch(execution["owner_nonce"])
                and execution["container_name"] == "agentsync-verifier-" + execution["owner_nonce"]
                and isinstance(execution["image_id"], str)
                and re.fullmatch(r"sha256:[a-f0-9]{64}", execution["image_id"])
            ):
                _error(
                    "reconciliation_identity_unavailable",
                    "A complete acknowledged identity is required.",
                )
            op_id = uuid.uuid4().hex
            db.execute(
                "UPDATE verification_jobs SET status='cleanup_pending',version=version+1,updated_at=? WHERE id=? AND project_id=?",
                (now, job_id, project_id),
            )
            db.execute(
                "UPDATE verification_attempts SET status='cleanup_pending',token_hash='',reason_code='cleanup_uncertain',updated_at=? WHERE id=? AND project_id=?",
                (now, attempt["id"], project_id),
            )
            db.execute(
                "UPDATE verification_executions SET phase='cleanup_pending',assessment='unverified',cleanup_confirmed=0,revision=revision+1,updated_at=? WHERE id=? AND project_id=?",
                (now, execution["id"], project_id),
            )
            db.execute(
                "INSERT INTO verification_reconciliations VALUES(?,?,?,?,?,?,?,?,?,'intent','unresolved','reconciliation_incomplete','{}',NULL,?,?)",
                (
                    op_id,
                    project_id,
                    job_id,
                    attempt["id"],
                    execution["id"],
                    request_id,
                    binding,
                    job["version"] + 1,
                    execution["revision"] + 1,
                    now,
                    now,
                ),
            )
            captured.update(dict(execution))
            captured.update(
                operation_id=op_id,
                job_version=job["version"] + 1,
                execution_revision=execution["revision"] + 1,
            )
            return _summary(db, self.jobs._job(db, p))

        try:
            self.jobs._transaction("execution_reconciliation_intent", p, claim, owner=True)
        except _Replay as replay:
            return replay.response
        observed = _observation(captured)
        encoded = _canonical(observed)

        def record(db: sqlite3.Connection, now: float) -> dict[str, Any]:
            job = self.jobs._job(db, p)
            receipt = db.execute(
                "SELECT * FROM verification_reconciliations WHERE id=? AND project_id=?",
                (captured["operation_id"], project_id),
            ).fetchone()
            execution = db.execute(
                "SELECT * FROM verification_executions WHERE id=? AND project_id=? AND job_id=?",
                (captured["id"], project_id, job_id),
            ).fetchone()
            attempt = db.execute(
                "SELECT * FROM verification_attempts WHERE id=? AND project_id=? AND job_id=?",
                (captured["attempt_id"], project_id, job_id),
            ).fetchone()
            if (
                receipt is None
                or execution is None
                or attempt is None
                or not (
                    receipt["status"] == "intent"
                    and job["version"] == captured["job_version"]
                    and job["current_attempt_id"] == captured["attempt_id"]
                    and execution["revision"] == captured["execution_revision"]
                    and execution["phase"] == "cleanup_pending"
                    and execution["assessment"] == "unverified"
                    and attempt["token_hash"] == ""
                    and attempt["status"] == "cleanup_pending"
                    and job["status"] == "cleanup_pending"
                    and receipt["execution_id"] == execution["id"] == captured["id"]
                    and receipt["attempt_id"]
                    == execution["attempt_id"]
                    == attempt["id"]
                    == captured["attempt_id"]
                    and receipt["claimed_job_version"] == captured["job_version"]
                    and receipt["claimed_execution_revision"] == captured["execution_revision"]
                    and receipt["payload_hash"] == binding
                    and receipt["request_id"] == request_id
                    and job["attempt_number"]
                    == attempt["attempt_number"]
                    == execution["attempt_number"]
                    == captured["attempt_number"]
                    and all(
                        execution[key] == captured[key]
                        for key in (
                            "container_id",
                            "container_name",
                            "owner_nonce",
                            "image_id",
                            "profile_sha256",
                            "create_intent",
                            "create_reply_complete",
                        )
                    )
                    and execution["cleanup_confirmed"] == 0
                )
            ):
                _error("version_conflict", "Cleanup intent no longer owns its record.")
            timestamps = (
                receipt["updated_at"],
                job["updated_at"],
                execution["updated_at"],
                attempt["updated_at"],
                attempt["lease_expires_at"],
            )
            if not all(math.isfinite(value) for value in timestamps):
                _error("invalid_clock", "Finite execution timestamps are required.")
            if now < max(timestamps[:4]):
                _error("clock_regressed", "Clock rollback prevents saving cleanup observations.")
            db.execute(
                "UPDATE verification_reconciliations SET status='recorded',outcome=?,error_code=?,observation_json=?,observation_sha256=?,updated_at=? WHERE id=? AND project_id=?",
                (
                    observed["outcome"],
                    observed["error_code"],
                    encoded,
                    _digest(encoded),
                    now,
                    captured["operation_id"],
                    project_id,
                ),
            )
            return _summary(db, job)

        return self.jobs._transaction("execution_reconciliation_record", p, record, owner=True)

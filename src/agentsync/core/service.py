"""Transport-independent transactional task coordination."""

import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentsync.config import resolve_data_dir
from agentsync.core.collaboration import CollaborationMixin, active_assignment, reservation
from agentsync.core.resources import ResourcesMixin
from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS
from agentsync.resources.paths import pin_root
from agentsync.storage.database import connect, migrate


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def identifier() -> str:
    return str(uuid.uuid4())


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Core(CollaborationMixin, ResourcesMixin):
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = resolve_data_dir(data_dir)
        self.db_path = self.data_dir / "agentsync.db"
        migrate(self.db_path)

    def execute(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        schema = OPERATIONS.get(operation)
        if schema is None:
            raise AgentSyncError("unknown_operation", "Unknown operation.", 404)
        try:
            p = schema.model_validate(payload).model_dump()
        except ValidationError as exc:
            # Pydantic's standard error strings include input values (credentials).
            fields = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
            raise AgentSyncError(
                "validation_error", "Invalid request fields: " + ", ".join(fields)
            ) from None
        db = connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            session = None
            if operation not in {"create_project", "register_agent"}:
                session = self._authenticate(db, p, now)
            request_id = p.get("request_id")
            fingerprint = digest(canonical(p))
            if request_id:
                old = db.execute(
                    "SELECT * FROM idempotency WHERE project_id=? AND session_id=? AND operation=? AND request_id=?",
                    (p["project_id"], p["session_id"], operation, request_id),
                ).fetchone()
                if old:
                    if not hmac.compare_digest(old["payload_hash"], fingerprint):
                        raise AgentSyncError(
                            "idempotency_conflict",
                            "Request ID already used with another payload.",
                            409,
                        )
                    response = json.loads(old["response"])
                    if operation in {"claim_task", "renew_lease"}:
                        token = (
                            self._claim_token(p) if operation == "claim_task" else p["lease_token"]
                        )
                        task = self._task(db, p)
                        self._lease(task, p, token, now)
                        if task["version"] != response["version"]:
                            raise AgentSyncError(
                                "stale_request",
                                "The lease request has been superseded by a newer task version.",
                                409,
                            )
                        response["lease_token"] = token
                    if operation in {"acquire_file_lock", "renew_file_lock"}:
                        response = self._resource_replay(db, operation, p, response, now)
                    db.commit()
                    return response
            response = getattr(self, "_" + operation)(db, p, now, session)
            if request_id:
                safe_response = {k: v for k, v in response.items() if k != "lease_token"}
                db.execute(
                    "INSERT INTO idempotency VALUES(?,?,?,?,?,?)",
                    (
                        p["project_id"],
                        p["session_id"],
                        operation,
                        request_id,
                        fingerprint,
                        canonical(safe_response),
                    ),
                )
            db.commit()
            return response
        except UnicodeEncodeError:
            db.rollback()
            raise AgentSyncError(
                "validation_error", "Request strings must contain valid Unicode characters."
            ) from None
        except sqlite3.Error:
            db.rollback()
            raise AgentSyncError("storage_error", "Database operation failed.", 503) from None
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _authenticate(db: sqlite3.Connection, p: dict[str, Any], now: float) -> sqlite3.Row:
        session = db.execute(
            "SELECT * FROM sessions WHERE id=? AND project_id=?", (p["session_id"], p["project_id"])
        ).fetchone()
        if session is None or not hmac.compare_digest(
            session["token_hash"], digest(p["session_token"])
        ):
            raise AgentSyncError("unauthorized", "Invalid session credentials.", 401)
        if session["expires_at"] <= now:
            raise AgentSyncError("session_expired", "Session has expired.", 401)
        return session

    @staticmethod
    def _task(db: sqlite3.Connection, p: dict[str, Any]) -> sqlite3.Row:
        task = db.execute(
            "SELECT * FROM tasks WHERE id=? AND project_id=?", (p["task_id"], p["project_id"])
        ).fetchone()
        if task is None:
            raise AgentSyncError("not_found", "Task not found.", 404)
        return task

    @staticmethod
    def _version(task: sqlite3.Row, p: dict[str, Any]) -> None:
        if task["version"] != p["expected_version"]:
            raise AgentSyncError("version_conflict", "Task version has changed.", 409)

    @staticmethod
    def _lease(task: sqlite3.Row, p: dict[str, Any], token: str, now: float) -> None:
        if (
            task["owner_session_id"] != p["session_id"]
            or not task["lease_hash"]
            or not hmac.compare_digest(task["lease_hash"], digest(token))
        ):
            raise AgentSyncError("lease_denied", "Lease does not belong to this session.", 403)
        if task["lease_expires_at"] <= now:
            raise AgentSyncError("lease_expired", "Lease has expired.", 409)

    @staticmethod
    def _public_task(db: sqlite3.Connection, task: sqlite3.Row) -> dict[str, Any]:
        public = {
            k: json.loads(task[k]) if k == "dependencies" else task[k]
            for k in (
                "id",
                "project_id",
                "title",
                "description",
                "priority",
                "status",
                "version",
                "owner_session_id",
                "result",
                "dependencies",
                "created_at",
                "updated_at",
                "lease_expires_at",
            )
        }
        review = db.execute(
            "SELECT task_id,project_id,reviewer_agent_id,reviewer_session_id,evidence,accept,created_at,version "
            "FROM reviews WHERE task_id=? AND project_id=? ORDER BY version DESC LIMIT 1",
            (task["id"], task["project_id"]),
        ).fetchone()
        assignment = active_assignment(db, task)
        public["assigned_agent_id"] = assignment["assigned_agent_id"] if assignment else None
        public["assignment_expires_at"] = (
            assignment["reservation_expires_at"] if assignment else None
        )
        public["latest_review"] = dict(review) if review is not None else None
        if public["latest_review"] is not None:
            public["latest_review"]["accept"] = bool(public["latest_review"]["accept"])
        return public

    @staticmethod
    def _claim_token(p: dict[str, Any]) -> str:
        message = canonical(
            ["agentsync-lease-v1", p["project_id"], p["session_id"], p["task_id"], p["request_id"]]
        )
        return hmac.new(p["session_token"].encode(), message.encode(), hashlib.sha256).hexdigest()

    def _create_project(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        root = Path(p["root_path"])
        try:
            valid_root = "\x00" not in p["root_path"] and root.is_absolute() and root.is_dir()
        except (OSError, ValueError):
            valid_root = False
        if not valid_root:
            raise AgentSyncError(
                "invalid_root", "Project root must be an existing absolute directory."
            )
        project_id, token = identifier(), secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?)",
            (project_id, p["name"], str(root.resolve()), digest(token), now),
        )
        pin_root(db, project_id, root.resolve())
        return {"project_id": project_id, "admin_token": token}

    def _register_agent(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        project = db.execute("SELECT * FROM projects WHERE id=?", (p["project_id"],)).fetchone()
        if project is None or not hmac.compare_digest(
            project["admin_hash"], digest(p["admin_token"])
        ):
            raise AgentSyncError("unauthorized", "Invalid project credentials.", 401)
        agent_id, session_id, token = identifier(), identifier(), secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO agents VALUES(?,?,?,?,?)",
            (agent_id, p["project_id"], p["name"], canonical(p["capabilities"]), now),
        )
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
            (session_id, p["project_id"], agent_id, digest(token), now, now, now + 3600),
        )
        return {
            "agent_id": agent_id,
            "session_id": session_id,
            "session_token": token,
            "expires_at": now + 3600,
        }

    def _heartbeat(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        db.execute(
            "UPDATE sessions SET heartbeat_at=?, expires_at=? WHERE id=?",
            (now, now + 3600, p["session_id"]),
        )
        return {"expires_at": now + 3600}

    def _create_task(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        if len(set(p["dependencies"])) != len(p["dependencies"]):
            raise AgentSyncError("invalid_dependencies", "Dependencies must be unique.")
        for dependency in p["dependencies"]:
            if not db.execute(
                "SELECT 1 FROM tasks WHERE id=? AND project_id=?", (dependency, p["project_id"])
            ).fetchone():
                raise AgentSyncError(
                    "invalid_dependencies", "Dependency does not exist in this project."
                )
        task_id = identifier()
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                p["project_id"],
                p["title"],
                p["description"],
                p["priority"],
                "pending",
                1,
                None,
                "",
                canonical(p["dependencies"]),
                now,
                now,
                None,
                None,
                None,
            ),
        )
        return self._public_task(db, self._task(db, {**p, "task_id": task_id}))

    def _list_tasks(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        rows = db.execute(
            "SELECT * FROM tasks WHERE project_id=? ORDER BY priority DESC, created_at, id",
            (p["project_id"],),
        ).fetchall()
        return {"tasks": [self._public_task(db, row) for row in rows]}

    def _get_project_state(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        project = dict(
            db.execute(
                "SELECT id,name,root_path,created_at FROM projects WHERE id=?", (p["project_id"],)
            ).fetchone()
        )
        agents = []
        for row in db.execute(
            "SELECT * FROM agents WHERE project_id=? ORDER BY created_at,id", (p["project_id"],)
        ):
            agent = dict(row)
            agent["capabilities"] = json.loads(agent["capabilities"])
            agents.append(agent)
        sessions = [
            dict(row)
            for row in db.execute(
                "SELECT id, project_id, agent_id, created_at, heartbeat_at, expires_at FROM sessions WHERE project_id=? ORDER BY created_at,id",
                (p["project_id"],),
            )
        ]
        for s in sessions:
            s["online"] = s["expires_at"] > now and now - s["heartbeat_at"] <= 120
        return {
            "project": project,
            "agents": agents,
            "sessions": sessions,
            **self._list_tasks(db, p, now, session),
        }

    def _claim_task(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        task = self._task(db, p)
        self._version(task, p)
        if task["status"] != "pending":
            raise AgentSyncError("invalid_transition", "Only pending tasks can be claimed.", 409)
        assigned = reservation(db, task, now)
        assert session is not None
        if assigned is not None and assigned != session["agent_id"]:
            raise AgentSyncError("assignment_denied", "Task is reserved for another agent.", 403)
        for dependency in json.loads(task["dependencies"]):
            row = db.execute(
                "SELECT status FROM tasks WHERE id=? AND project_id=?",
                (dependency, p["project_id"]),
            ).fetchone()
            if not row or row["status"] != "completed":
                raise AgentSyncError(
                    "dependencies_incomplete", "Task dependencies are not completed.", 409
                )
        token = self._claim_token(p)
        db.execute(
            "UPDATE tasks SET status='claimed',version=version+1,owner_session_id=?,lease_hash=?,lease_expires_at=?,updated_at=? WHERE id=? AND version=?",
            (
                p["session_id"],
                digest(token),
                now + p["lease_seconds"],
                now,
                p["task_id"],
                p["expected_version"],
            ),
        )
        return {**self._public_task(db, self._task(db, p)), "lease_token": token}

    def _renew_lease(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        task = self._task(db, p)
        self._version(task, p)
        self._lease(task, p, p["lease_token"], now)
        if task["status"] not in {"claimed", "running", "blocked"}:
            raise AgentSyncError("invalid_transition", "Task has no renewable lease.", 409)
        db.execute(
            "UPDATE tasks SET version=version+1,lease_expires_at=?,updated_at=? WHERE id=? AND version=?",
            (now + p["lease_seconds"], now, p["task_id"], p["expected_version"]),
        )
        return {**self._public_task(db, self._task(db, p)), "lease_token": p["lease_token"]}

    def _update_task(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        task = self._task(db, p)
        self._version(task, p)
        self._lease(task, p, p["lease_token"], now)
        allowed = {
            "claimed": {"running", "review", "blocked", "failed", "cancelled"},
            "running": {"review", "blocked", "failed", "cancelled"},
            "blocked": {"running", "review", "failed", "cancelled"},
        }
        if p["status"] not in allowed.get(task["status"], set()):
            raise AgentSyncError("invalid_transition", "Task state transition is not allowed.", 409)
        terminal_lease = p["status"] in {"review", "failed", "cancelled"}
        db.execute(
            "UPDATE tasks SET status=?,result=?,version=version+1,updated_at=?,lease_hash=?,lease_expires_at=? WHERE id=? AND version=?",
            (
                p["status"],
                p["result"],
                now,
                None if terminal_lease else task["lease_hash"],
                None if terminal_lease else task["lease_expires_at"],
                p["task_id"],
                p["expected_version"],
            ),
        )
        return self._public_task(db, self._task(db, p))

    def _review_task(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        task = self._task(db, p)
        self._version(task, p)
        if task["status"] != "review":
            raise AgentSyncError("invalid_transition", "Only submitted tasks can be reviewed.", 409)
        owner = db.execute(
            "SELECT agent_id FROM sessions WHERE id=?", (task["owner_session_id"],)
        ).fetchone()
        assert session is not None
        if owner is None or owner["agent_id"] == session["agent_id"]:
            raise AgentSyncError(
                "separate_reviewer_required", "A different agent must review the task.", 403
            )
        if not p["evidence"].strip():
            raise AgentSyncError("validation_error", "Review evidence is required.")
        db.execute(
            "UPDATE tasks SET status=?,version=version+1,updated_at=?,review_evidence=?,owner_session_id=?,lease_hash=NULL,lease_expires_at=NULL WHERE id=? AND version=?",
            (
                "completed" if p["accept"] else "pending",
                now,
                p["evidence"],
                task["owner_session_id"] if p["accept"] else None,
                p["task_id"],
                p["expected_version"],
            ),
        )
        db.execute(
            "INSERT INTO reviews(task_id,project_id,reviewer_agent_id,reviewer_session_id,evidence,accept,created_at,version) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                p["task_id"],
                p["project_id"],
                session["agent_id"],
                p["session_id"],
                p["evidence"],
                int(p["accept"]),
                now,
                p["expected_version"] + 1,
            ),
        )
        return self._public_task(db, self._task(db, p))

    def _reclaim_expired(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        rows = db.execute(
            "SELECT id FROM tasks WHERE project_id=? AND status IN ('claimed','running','blocked') AND lease_expires_at<=?",
            (p["project_id"], now),
        ).fetchall()
        ids = [row["id"] for row in rows]
        db.execute(
            "UPDATE tasks SET status='pending',version=version+1,owner_session_id=NULL,lease_hash=NULL,lease_expires_at=NULL,updated_at=? WHERE project_id=? AND status IN ('claimed','running','blocked') AND lease_expires_at<=?",
            (now, p["project_id"], now),
        )
        return {"reclaimed_task_ids": ids}

"""Versioned shared context and explicit, lease-safe ownership handoffs."""

import json
import sqlite3
import time
import uuid
from typing import Any

from agentsync.errors import AgentSyncError


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_text(value: Any) -> None:
    """Keep NULs out of SQLite FTS and all nested M3 metadata."""
    if isinstance(value, str) and "\x00" in value:
        raise AgentSyncError("validation_error", "Text must not contain NUL characters.")
    if isinstance(value, dict):
        for item in value.values():
            validate_text(item)
    elif isinstance(value, list):
        for item in value:
            validate_text(item)


def revision(
    db: sqlite3.Connection, project_id: str, context_id: str, version: int | None = None
) -> dict[str, Any]:
    row = db.execute(
        "SELECT * FROM context_revisions WHERE project_id=? AND context_id=? "
        "AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1",
        (project_id, context_id, version, version),
    ).fetchone()
    if row is None:
        raise AgentSyncError("not_found", "Context revision not found.", 404)
    return {"id": row["context_id"], **dict(row)}


def handoff(db: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
    row = db.execute(
        "SELECT * FROM handoffs WHERE id=? AND project_id=?", (p["handoff_id"], p["project_id"])
    ).fetchone()
    if row is None:
        raise AgentSyncError("not_found", "Handoff not found.", 404)
    result = dict(row)
    for field in ("package", "contexts"):
        result[field] = json.loads(result[field])
    result["assignment_expires_at"] = result["reservation_expires_at"]
    return result


def active_assignment(
    db: sqlite3.Connection, task: sqlite3.Row, now: float | None = None
) -> sqlite3.Row | None:
    return db.execute(
        "SELECT assigned_agent_id,reservation_expires_at FROM handoffs "
        "WHERE project_id=? AND task_id=? AND task_version=? "
        "AND status IN ('accepted','rejected','withdrawn') AND reservation_expires_at>?",
        (task["project_id"], task["id"], task["version"], time.time() if now is None else now),
    ).fetchone()


def reservation(db: sqlite3.Connection, task: sqlite3.Row, now: float | None = None) -> str | None:
    row = active_assignment(db, task, now)
    return row["assigned_agent_id"] if row else None


class CollaborationMixin:
    """Operations run under Core.execute's authentication and write transaction."""

    @staticmethod
    def _task(db: sqlite3.Connection, p: dict[str, Any]) -> sqlite3.Row:
        raise NotImplementedError

    @staticmethod
    def _version(task: sqlite3.Row, p: dict[str, Any]) -> None:
        raise NotImplementedError

    @staticmethod
    def _lease(task: sqlite3.Row, p: dict[str, Any], token: str, now: float) -> None:
        raise NotImplementedError

    def _publish_context(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        validate_text(p)
        if not p["title"].strip() or not p["content"].strip():
            raise AgentSyncError("validation_error", "Context title and content are required.")
        if p["context_id"] is None:
            if p["expected_version"] != 0:
                raise AgentSyncError("version_conflict", "New context requires version zero.", 409)
            context_id, version, created_at = str(uuid.uuid4()), 1, now
        else:
            old = revision(db, p["project_id"], p["context_id"])
            if old["version"] != p["expected_version"]:
                raise AgentSyncError("version_conflict", "Context version has changed.", 409)
            context_id, version, created_at = (
                old["context_id"],
                old["version"] + 1,
                old["created_at"],
            )
        assert session is not None
        values = (
            context_id,
            p["project_id"],
            version,
            p["kind"],
            p["title"],
            p["content"],
            p["summary"],
            p["source"],
            session["agent_id"],
            p["session_id"],
            created_at,
            now,
        )
        db.execute("INSERT INTO context_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", values)
        db.execute(
            "DELETE FROM context_search WHERE context_id=? AND project_id=?",
            (context_id, p["project_id"]),
        )
        db.execute(
            "INSERT INTO context_search(context_id,project_id,kind,title,content,summary,source) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                context_id,
                p["project_id"],
                p["kind"],
                p["title"],
                p["content"],
                p["summary"],
                p["source"],
            ),
        )
        return revision(db, p["project_id"], context_id)

    def _get_context(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        validate_text(p)
        return revision(db, p["project_id"], p["context_id"], p["version"])

    def _search_context(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        validate_text(p)
        query = p["query"]
        if not query.strip():
            raise AgentSyncError("validation_error", "Search query must not be blank.")
        params: list[Any] = [p["project_id"], p["kind"], p["kind"]]
        where = "project_id=? AND (? IS NULL OR kind=?)"
        if len(query) >= 3:
            # Quoted FTS phrase is always literal, including quotes and operators.
            where += " AND context_search MATCH ?"
            params.append('"' + query.replace('"', '""') + '"')
        else:
            pattern = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
            where += " AND (title LIKE ? ESCAPE '!' OR content LIKE ? ESCAPE '!' "
            where += "OR summary LIKE ? ESCAPE '!' OR source LIKE ? ESCAPE '!')"
            params.extend([pattern] * 4)
        params.extend([p["limit"] + 1, p["offset"]])
        rows = db.execute(
            "SELECT context_id FROM context_search WHERE "
            + where
            + " ORDER BY context_id LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return {
            "entries": [
                revision(db, p["project_id"], row["context_id"]) for row in rows[: p["limit"]]
            ],
            "has_more": len(rows) > p["limit"],
        }

    def _submit_handoff(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        validate_text(p)
        task = self._task(db, p)
        self._version(task, p)
        self._lease(task, p, p["lease_token"], now)
        if task["status"] not in {"claimed", "running", "blocked"}:
            raise AgentSyncError("invalid_transition", "Task cannot be handed off.", 409)
        assert session is not None
        if p["target_agent_id"] == session["agent_id"]:
            raise AgentSyncError("invalid_recipient", "Recipient must be a different agent.")
        if not db.execute(
            "SELECT 1 FROM agents WHERE id=? AND project_id=?",
            (p["target_agent_id"], p["project_id"]),
        ).fetchone():
            raise AgentSyncError("invalid_recipient", "Recipient is not enrolled in this project.")
        if not p["package"]["summary"].strip():
            raise AgentSyncError("validation_error", "Handoff summary is required.")
        contexts = [
            revision(db, p["project_id"], ref["context_id"], ref["version"])
            for ref in p["package"]["context_refs"]
        ]
        handoff_id = str(uuid.uuid4())
        db.execute(
            "UPDATE tasks SET status='handoff',version=version+1,owner_session_id=NULL,"
            "lease_hash=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND project_id=?",
            (now, task["id"], p["project_id"]),
        )
        db.execute(
            "INSERT INTO handoffs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                handoff_id,
                p["project_id"],
                task["id"],
                session["agent_id"],
                p["session_id"],
                p["target_agent_id"],
                encoded(p["package"]),
                encoded(contexts),
                "pending",
                "",
                now,
                None,
                task["version"] + 1,
                None,
                None,
            ),
        )
        return handoff(db, {**p, "handoff_id": handoff_id})

    def _get_handoff(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        validate_text(p)
        return handoff(db, p)

    def _resolve_handoff(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        return self._decide_handoff(db, p, now, session, withdraw=False)

    def _withdraw_handoff(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        return self._decide_handoff(db, p, now, session, withdraw=True)

    def _owner_recover_handoff(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        """Recover abandoned coordination metadata, without restarting an execution.

        execute_owner authenticates the project owner and holds BEGIN IMMEDIATE.
        A pending handoff has already relinquished its sender's task lease. This
        operation neither proves that an external process stopped nor clears any
        host receipt, execution intent, worktree or launch-approval fence.
        """
        validate_text(p)
        if not p["reason"].strip():
            raise AgentSyncError("validation_error", "A recovery reason is required.")
        old = handoff(db, p)
        if old["task_id"] != p["task_id"]:
            raise AgentSyncError("handoff_denied", "Handoff belongs to another task.", 409)
        task = self._task(db, p)
        self._version(task, p)
        if (
            old["status"] != "pending"
            or task["status"] != "handoff"
            or old["task_version"] != task["version"]
        ):
            raise AgentSyncError("invalid_transition", "Handoff is no longer pending.", 409)
        if db.execute(
            "SELECT 1 FROM mock_workflow_tasks m JOIN mock_workflows w ON w.id=m.run_id "
            "WHERE m.task_id=? AND w.project_id=?",
            (task["id"], p["project_id"]),
        ).fetchone():
            raise AgentSyncError(
                "workflow_managed_task", "The task belongs to a durable Mock workflow.", 409
            )
        if db.execute(
            "SELECT 1 FROM sessions WHERE project_id=? AND agent_id IN (?,?) "
            "AND expires_at>? LIMIT 1",
            (p["project_id"], old["sender_agent_id"], old["recipient_agent_id"], now),
        ).fetchone():
            raise AgentSyncError(
                "handoff_participant_active", "A handoff participant still has a live session.", 409
            )
        db.execute(
            "UPDATE tasks SET status='pending',version=version+1,owner_session_id=NULL,"
            "lease_hash=NULL,lease_expires_at=NULL,updated_at=? WHERE id=? AND project_id=?",
            (now, task["id"], p["project_id"]),
        )
        db.execute(
            "UPDATE handoffs SET status='recovered',reason=?,resolved_at=?,task_version=?,"
            "assigned_agent_id=NULL,reservation_expires_at=NULL WHERE id=? AND project_id=?",
            (p["reason"], now, task["version"] + 1, old["id"], p["project_id"]),
        )
        return {
            **handoff(db, p),
            "version": task["version"] + 1,
            "recovery_scope": "handoff_metadata_only",
            "execution_restarted": False,
        }

    def _owner_list_handoffs(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        """Let the owner find the exact abandoned handoff without old credentials."""
        validate_text(p)
        rows = db.execute(
            "SELECT id,project_id,task_id,status,task_version,sender_agent_id,"
            "recipient_agent_id,created_at,resolved_at,assigned_agent_id,reservation_expires_at "
            "FROM handoffs WHERE project_id=? "
            "AND (? IS NULL OR task_id=?) AND (? IS NULL OR status=?) "
            "ORDER BY created_at,id LIMIT ? OFFSET ?",
            (
                p["project_id"],
                p["task_id"],
                p["task_id"],
                p["status"],
                p["status"],
                p["limit"] + 1,
                p["offset"],
            ),
        ).fetchall()
        return {
            "handoffs": [dict(row) for row in rows[: p["limit"]]],
            "has_more": len(rows) > p["limit"],
        }

    def _decide_handoff(
        self,
        db: sqlite3.Connection,
        p: dict[str, Any],
        now: float,
        session: sqlite3.Row | None,
        *,
        withdraw: bool,
    ) -> dict[str, Any]:
        validate_text(p)
        old = handoff(db, p)
        assert session is not None
        identity = old["sender_agent_id"] if withdraw else old["recipient_agent_id"]
        if session["agent_id"] != identity:
            raise AgentSyncError(
                "handoff_denied", "Agent identity cannot decide this handoff.", 403
            )
        task = self._task(db, {**p, "task_id": old["task_id"]})
        self._version(task, p)
        if (
            old["status"] != "pending"
            or task["status"] != "handoff"
            or task["version"] != old["task_version"]
        ):
            raise AgentSyncError("invalid_transition", "Handoff is no longer pending.", 409)
        accept = not withdraw and p["accept"]
        if (withdraw or not accept) and not p["reason"].strip():
            raise AgentSyncError("validation_error", "A decision reason is required.")
        status = "withdrawn" if withdraw else "accepted" if accept else "rejected"
        assigned = old["recipient_agent_id"] if accept else old["sender_agent_id"]
        if accept:
            session_expiry = session["expires_at"]
        else:
            session_expiry = db.execute(
                "SELECT MAX(expires_at) FROM sessions WHERE project_id=? AND agent_id=? "
                "AND expires_at>?",
                (p["project_id"], assigned, now),
            ).fetchone()[0]
        deadline = min(now + 300, session_expiry if session_expiry is not None else now)
        db.execute(
            "UPDATE tasks SET status='pending',version=version+1,updated_at=? "
            "WHERE id=? AND project_id=?",
            (now, task["id"], p["project_id"]),
        )
        db.execute(
            "UPDATE handoffs SET status=?,reason=?,resolved_at=?,task_version=?,"
            "assigned_agent_id=?,reservation_expires_at=? WHERE id=? AND project_id=?",
            (
                status,
                p["reason"],
                now,
                task["version"] + 1,
                assigned,
                deadline,
                old["id"],
                p["project_id"],
            ),
        )
        return handoff(db, p)

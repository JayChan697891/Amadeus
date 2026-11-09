"""Fail-closed roles, separate owner authority, approval metadata and safe audit."""

import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS, OWNER_OPERATIONS, StrictModel
from agentsync.storage.database import connect

VIEWER_OPERATIONS = frozenset(
    {
        "heartbeat",
        "list_tasks",
        "get_project_state",
        "get_context",
        "search_context",
        "get_handoff",
        "inspect_path",
        "verify_file_version",
        "list_file_locks",
        "inspect_worktree",
        "get_approval",
        "list_approvals",
    }
)
WORKER_OPERATIONS = frozenset(
    {
        "create_task",
        "claim_task",
        "renew_lease",
        "update_task",
        "reclaim_expired",
        "publish_context",
        "submit_handoff",
        "resolve_handoff",
        "withdraw_handoff",
        "acquire_file_lock",
        "renew_file_lock",
        "release_file_lock",
        "capture_repository",
        "create_worktree",
        "compare_worktrees",
        "prepare_merge_candidate",
        "request_approval",
    }
)
REVIEWER_OPERATIONS = frozenset({"review_task", "list_audit"})
BOOTSTRAP_OPERATIONS = frozenset({"create_project", "register_agent"})
AGENT_WRITES = WORKER_OPERATIONS | {"review_task", "heartbeat"} | BOOTSTRAP_OPERATIONS
OWNER_WRITES = frozenset(
    {"set_agent_roles", "decide_approval", "revoke_approval", "import_usage_checkpoint"}
)
VERIFICATION_AUDIT_OPERATIONS = frozenset(
    {
        "task_verified_complete",
        "verification_enqueue",
        "candidate_verification_enqueue",
        "candidate_verification_cancel",
        "candidate_verification_claim",
        "candidate_verification_recover",
        "candidate_intent_prepare",
        "candidate_intent_abandon",
        "candidate_execution_admit",
        "candidate_execution_progress",
        "candidate_execution_finish",
        "candidate_execution_unresolved",
        "candidate_execution_cancel",
        "candidate_execution_cleanup_intent",
        "candidate_execution_cleanup_record",
        "candidate_delivery_approve",
        "candidate_delivery_admit",
        "verification_cancel",
        "verification_claim",
        "verification_renew",
        "verification_ack_cancel",
        "verification_interrupt",
        "execution_claim",
        "execution_bind",
        "execution_create_intent",
        "execution_created",
        "execution_start",
        "execution_finish",
        "execution_cancel",
        "execution_pending",
        "execution_reconciliation_intent",
        "execution_reconciliation_record",
    }
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class PermissionsMixin:
    db_path: Path

    @staticmethod
    def _validated_payload(schema: type[StrictModel], payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return schema.model_validate(payload).model_dump()
        except ValidationError as exc:
            # Unknown extra-field names are attacker-controlled too, not just values.
            fields = sorted(
                {
                    str(error["loc"][0])
                    if error["loc"] and error["loc"][0] in schema.model_fields
                    else "extra_field"
                    for error in exc.errors()
                }
            )
            raise AgentSyncError(
                "validation_error", "Invalid request fields: " + ", ".join(fields)
            ) from None

    @staticmethod
    def _authorize_session(db: sqlite3.Connection, operation: str, session: sqlite3.Row) -> None:
        row = db.execute(
            "SELECT roles FROM agent_memberships WHERE agent_id=? AND project_id=?",
            (session["agent_id"], session["project_id"]),
        ).fetchone()
        roles = set(json.loads(row["roles"])) if row is not None else set()
        allowed = (
            (operation in VIEWER_OPERATIONS and bool(roles & {"viewer", "worker", "reviewer"}))
            or (operation in WORKER_OPERATIONS and "worker" in roles)
            or (operation in REVIEWER_OPERATIONS and "reviewer" in roles)
        )
        if not allowed:
            raise AgentSyncError(
                "forbidden", "Current membership does not permit this operation.", 403
            )

    @staticmethod
    def _authenticate_owner(db: sqlite3.Connection, p: dict[str, Any]) -> None:
        row = db.execute(
            "SELECT admin_hash FROM projects WHERE id=?", (p["project_id"],)
        ).fetchone()
        if row is None or not hmac.compare_digest(row["admin_hash"], _digest(p["admin_token"])):
            raise AgentSyncError("unauthorized", "Invalid project credentials.", 401)

    @staticmethod
    def _audit_event(
        db: sqlite3.Connection,
        project_id: str,
        actor_kind: str,
        actor_id: str,
        operation: str,
        p: dict[str, Any],
        outcome: str,
        code: str,
        response: dict[str, Any] | None = None,
    ) -> None:
        safe_operation = (
            operation
            if operation in OPERATIONS
            or operation in OWNER_OPERATIONS
            or operation in VERIFICATION_AUDIT_OPERATIONS
            else "unknown"
        )
        safe_code = code if re.fullmatch(r"[a-z_]{1,64}", code) else "operation_failed"
        target = None
        if response is not None:
            for field in (
                "id",
                "agent_id",
                "worktree_id",
                "snapshot_id",
                "candidate_id",
                "context_id",
                "handoff_id",
                "task_id",
            ):
                value = response.get(field)
                if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F-]{32,64}", value):
                    target = value
                    break
        request_id = p.get("request_id")
        pre = p.get("expected_version")
        post = response.get("version") if response is not None else None
        db.execute(
            "INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                project_id,
                actor_kind,
                actor_id,
                safe_operation,
                target,
                outcome,
                safe_code,
                pre if type(pre) is int else None,
                post if type(post) is int else None,
                hashlib.sha256(request_id.encode(errors="backslashreplace")).hexdigest()
                if isinstance(request_id, str)
                else None,
                time.time(),
            ),
        )

    def _audit_denial(
        self, actor: tuple[str, str, str] | None, operation: str, p: dict[str, Any], code: str
    ) -> None:
        if actor is None:
            return
        # The denied transaction has already rolled back. An unverified request
        # never gets here with actor metadata; failure to log cannot authorize it.
        try:
            db = connect(self.db_path)
        except sqlite3.Error:
            return
        try:
            db.execute("PRAGMA busy_timeout=1000")
            db.execute("BEGIN IMMEDIATE")
            self._audit_event(db, *actor, operation, p, "denied", code)
            db.commit()
        except sqlite3.Error:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def _member(db: sqlite3.Connection, p: dict[str, Any]) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM agent_memberships WHERE project_id=? AND agent_id=?",
            (p["project_id"], p["agent_id"]),
        ).fetchone()
        if row is None:
            raise AgentSyncError("not_found", "Member not found.", 404)
        return row

    @staticmethod
    def _public_member(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "agent_id": row["agent_id"],
            "project_id": row["project_id"],
            "roles": json.loads(row["roles"]),
            "version": row["version"],
        }

    def _owner_set_agent_roles(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        row = self._member(db, p)
        if row["version"] != p["expected_version"]:
            raise AgentSyncError("version_conflict", "Membership version has changed.", 409)
        db.execute(
            "UPDATE agent_memberships SET roles=?,version=version+1,updated_at=? WHERE project_id=? AND agent_id=?",
            (_canonical(sorted(p["roles"])), now, p["project_id"], p["agent_id"]),
        )
        return self._public_member(self._member(db, p))

    def _owner_list_members(
        self, db: sqlite3.Connection, p: dict[str, Any], _: float
    ) -> dict[str, Any]:
        rows = db.execute(
            "SELECT * FROM agent_memberships WHERE project_id=? ORDER BY agent_id LIMIT ? OFFSET ?",
            (p["project_id"], p["limit"] + 1, p["offset"]),
        ).fetchall()
        return {
            "members": [self._public_member(row) for row in rows[: p["limit"]]],
            "has_more": len(rows) > p["limit"],
        }

    @staticmethod
    def _approval(
        db: sqlite3.Connection, p: dict[str, Any], agent_id: str | None = None
    ) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM approvals WHERE id=? AND project_id=?",
            (p["approval_id"], p["project_id"]),
        ).fetchone()
        if row is None or (agent_id is not None and row["requester_agent_id"] != agent_id):
            raise AgentSyncError("not_found", "Approval not found.", 404)
        return row

    @staticmethod
    def _public_approval(row: sqlite3.Row, now: float) -> dict[str, Any]:
        response = {
            key: row[key]
            for key in (
                "id",
                "project_id",
                "requester_agent_id",
                "action",
                "subject_id",
                "subject_sha",
                "subject_version",
                "version",
                "status",
                "created_at",
                "updated_at",
                "expires_at",
            )
        }
        if row["status"] in {"pending", "approved"} and row["expires_at"] <= now:
            response["status"] = "expired"
        return response

    def _request_approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row
    ) -> dict[str, Any]:
        candidate = db.execute(
            "SELECT receipt FROM merge_candidates WHERE id=? AND project_id=?",
            (p["subject_id"], p["project_id"]),
        ).fetchone()
        if candidate is None:
            raise AgentSyncError("not_found", "Merge candidate not found.", 404)
        receipt = json.loads(candidate["receipt"])
        if (
            receipt["candidate_sha"] != p["subject_sha"].lower()
            or receipt["status"] != "awaiting_human_approval"
        ):
            raise AgentSyncError(
                "stale_snapshot", "Merge candidate does not match the pinned resource.", 409
            )
        approval_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                approval_id,
                p["project_id"],
                session["agent_id"],
                p["action"],
                p["subject_id"],
                p["subject_sha"].lower(),
                1,
                1,
                "pending",
                now,
                now,
                now + p["expires_in"],
                p["reason"],
            ),
        )
        return self._public_approval(self._approval(db, {**p, "approval_id": approval_id}), now)

    def _get_approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row
    ) -> dict[str, Any]:
        return self._public_approval(self._approval(db, p, session["agent_id"]), now)

    def _list_approvals(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row
    ) -> dict[str, Any]:
        rows = db.execute(
            "SELECT * FROM approvals WHERE project_id=? AND requester_agent_id=? ORDER BY created_at,id LIMIT ? OFFSET ?",
            (p["project_id"], session["agent_id"], p["limit"] + 1, p["offset"]),
        ).fetchall()
        return {
            "approvals": [self._public_approval(row, now) for row in rows[: p["limit"]]],
            "has_more": len(rows) > p["limit"],
        }

    def _owner_decide_approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        return self._change_approval(
            db, p, now, "approved" if p["accept"] else "denied", {"pending"}
        )

    def _owner_revoke_approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        return self._change_approval(db, p, now, "revoked", {"pending", "approved"})

    def _change_approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, status: str, allowed: set[str]
    ) -> dict[str, Any]:
        row = self._approval(db, p)
        if row["version"] != p["expected_version"]:
            raise AgentSyncError("version_conflict", "Approval version has changed.", 409)
        if row["expires_at"] <= now:
            raise AgentSyncError("approval_expired", "Approval has expired.", 409)
        if row["status"] not in allowed:
            raise AgentSyncError("approval_state", "Approval cannot make this transition.", 409)
        db.execute(
            "UPDATE approvals SET status=?,version=version+1,updated_at=? WHERE id=? AND project_id=?",
            (status, now, p["approval_id"], p["project_id"]),
        )
        return self._public_approval(self._approval(db, p), now)

    def _approval_replay(
        self,
        db: sqlite3.Connection,
        p: dict[str, Any],
        response: dict[str, Any],
        now: float,
        session: sqlite3.Row,
    ) -> dict[str, Any]:
        return self._public_approval(
            self._approval(db, {**p, "approval_id": response["id"]}, session["agent_id"]), now
        )

    def _owner_replay(
        self,
        db: sqlite3.Connection,
        operation: str,
        p: dict[str, Any],
        response: dict[str, Any],
        now: float,
    ) -> dict[str, Any]:
        if operation == "import_usage_checkpoint":
            return response
        if operation == "set_agent_roles":
            current = self._public_member(self._member(db, p))
            if current["version"] != response["version"] or current["roles"] != response["roles"]:
                raise AgentSyncError(
                    "stale_request", "Membership request has been superseded.", 409
                )
            return current
        current = self._public_approval(self._approval(db, p), now)
        if current["status"] == "expired":
            raise AgentSyncError("approval_expired", "Approval has expired.", 409)
        if current["version"] != response["version"] or current["status"] != response["status"]:
            raise AgentSyncError("stale_request", "Approval request has been superseded.", 409)
        return current

    @staticmethod
    def _audit_list(db: sqlite3.Connection, p: dict[str, Any]) -> dict[str, Any]:
        rows = db.execute(
            "SELECT * FROM audit_events WHERE project_id=? ORDER BY time,event_id LIMIT ? OFFSET ?",
            (p["project_id"], p["limit"] + 1, p["offset"]),
        ).fetchall()
        return {
            "events": [dict(row) for row in rows[: p["limit"]]],
            "has_more": len(rows) > p["limit"],
        }

    def _list_audit(
        self, db: sqlite3.Connection, p: dict[str, Any], _: float, __: sqlite3.Row
    ) -> dict[str, Any]:
        return self._audit_list(db, p)

    def _owner_list_audit(
        self, db: sqlite3.Connection, p: dict[str, Any], _: float
    ) -> dict[str, Any]:
        return self._audit_list(db, p)

    def execute_owner(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        schema = OWNER_OPERATIONS.get(operation)
        if schema is None:
            raise AgentSyncError("unknown_operation", "Unknown owner operation.", 404)
        p = self._validated_payload(schema, payload)
        db = connect(self.db_path)
        actor = None
        try:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            self._authenticate_owner(db, p)
            actor = (p["project_id"], "owner", p["project_id"])
            request_id = p.get("request_id")
            fingerprint = _digest(
                _canonical({key: value for key, value in p.items() if key != "admin_token"})
            )
            if request_id:
                cached = db.execute(
                    "SELECT * FROM owner_idempotency WHERE project_id=? AND operation=? AND request_id=?",
                    (p["project_id"], operation, request_id),
                ).fetchone()
                if cached is not None:
                    if not hmac.compare_digest(cached["payload_hash"], fingerprint):
                        raise AgentSyncError(
                            "idempotency_conflict",
                            "Request ID already used with another payload.",
                            409,
                        )
                    response = self._owner_replay(
                        db, operation, p, json.loads(cached["response"]), now
                    )
                    db.commit()
                    return response
            response = getattr(self, "_owner_" + operation)(db, p, now)
            if request_id:
                db.execute(
                    "INSERT INTO owner_idempotency VALUES(?,?,?,?,?)",
                    (p["project_id"], operation, request_id, fingerprint, _canonical(response)),
                )
            if operation in OWNER_WRITES:
                self._audit_event(db, *actor, operation, p, "success", "ok", response)
            db.commit()
            return response
        except AgentSyncError as exc:
            db.rollback()
            self._audit_denial(actor, operation, p, exc.code)
            raise
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

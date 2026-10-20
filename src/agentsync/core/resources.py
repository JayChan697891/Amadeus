"""Cooperative resource locks, scoped by physical paths and shared transactions."""

import hashlib
import hmac
import json
import sqlite3
import uuid
from typing import Any

from agentsync.errors import AgentSyncError
from agentsync.resources.paths import inspect_resource, resolve_resource


def lock_token(p: dict[str, Any]) -> str:
    message = json.dumps(
        ["agentsync-resource-lease-v1", p["project_id"], p["session_id"], p["request_id"]],
        separators=(",", ":"),
    )
    return hmac.new(p["session_token"].encode(), message.encode(), hashlib.sha256).hexdigest()


def public_lock(row: sqlite3.Row, now: float) -> dict[str, Any]:
    public = {
        key: row[key]
        for key in (
            "id",
            "project_id",
            "path",
            "kind",
            "owner_agent_id",
            "owner_session_id",
            "version",
            "status",
            "created_at",
            "updated_at",
            "expires_at",
        )
    }
    if public["status"] == "active" and public["expires_at"] <= now:
        public["status"] = "expired"
    return public


def overlaps(key: str, kind: str, other_key: str, other_kind: str) -> bool:
    return (
        key == other_key
        or (kind == "directory" and other_key.startswith(key.rstrip("/") + "/"))
        or (other_kind == "directory" and key.startswith(other_key.rstrip("/") + "/"))
    )


class ResourcesMixin:
    @staticmethod
    def _resource_lock(db: sqlite3.Connection, p: dict[str, Any]) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM file_locks WHERE id=? AND project_id=?", (p["lock_id"], p["project_id"])
        ).fetchone()
        if row is None:
            raise AgentSyncError("not_found", "Resource lock not found.", 404)
        return row

    @staticmethod
    def _lock_lease(
        db: sqlite3.Connection, row: sqlite3.Row, p: dict[str, Any], token: str, now: float
    ) -> None:
        if row["owner_session_id"] != p["session_id"] or not hmac.compare_digest(
            row["lease_hash"], hashlib.sha256(token.encode()).hexdigest()
        ):
            raise AgentSyncError("lock_denied", "Lock does not belong to this session.", 403)
        if row["status"] != "active" or row["expires_at"] <= now:
            raise AgentSyncError("lock_expired", "Resource lock is no longer active.", 409)
        resource = resolve_resource(db, p["project_id"], row["path"])
        if resource.key != row["resource_key"]:
            raise AgentSyncError("path_boundary", "Resource identity has changed.")
        if resource.exists and resource.kind != row["kind"]:
            raise AgentSyncError("invalid_kind", "Resource kind no longer matches the lock.")

    def _resource_replay(
        self,
        db: sqlite3.Connection,
        operation: str,
        p: dict[str, Any],
        response: dict[str, Any],
        now: float,
    ) -> dict[str, Any]:
        token = lock_token(p) if operation == "acquire_file_lock" else p["lease_token"]
        row = self._resource_lock(db, {**p, "lock_id": response["id"]})
        self._lock_lease(db, row, p, token, now)
        if row["version"] != response["version"]:
            raise AgentSyncError("stale_request", "Resource lock request has been superseded.", 409)
        return {**response, "lease_token": token}

    def _inspect_path(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        return inspect_resource(db, p["project_id"], p["path"])

    def _verify_file_version(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        inspected = inspect_resource(db, p["project_id"], p["path"])
        expected = p["expected_sha256"]
        matches = (
            inspected["kind"] == "missing"
            if expected is None
            else (
                inspected["kind"] == "file"
                and hmac.compare_digest(inspected["sha256"], expected.lower())
            )
        )
        return {**inspected, "matches": matches}

    def _acquire_file_lock(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        resource = resolve_resource(db, p["project_id"], p["path"])
        if (resource.exists and resource.kind != p["kind"]) or (
            resource.relative == "." and p["kind"] != "directory"
        ):
            raise AgentSyncError("invalid_kind", "Lock kind does not match the resource.")
        for other in db.execute(
            "SELECT resource_key,kind FROM file_locks WHERE status='active' AND expires_at>?",
            (now,),
        ):
            if overlaps(resource.key, p["kind"], other["resource_key"], other["kind"]):
                raise AgentSyncError("lock_busy", "Resource is already locked.", 409)
        assert session is not None
        token, lock_id = lock_token(p), str(uuid.uuid4())
        db.execute(
            "INSERT INTO file_locks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                lock_id,
                p["project_id"],
                resource.relative,
                resource.key,
                p["kind"],
                session["agent_id"],
                p["session_id"],
                1,
                "active",
                now,
                now,
                now + p["lease_seconds"],
                hashlib.sha256(token.encode()).hexdigest(),
            ),
        )
        row = self._resource_lock(db, {**p, "lock_id": lock_id})
        return {**public_lock(row, now), "lease_token": token}

    def _renew_file_lock(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        row = self._resource_lock(db, p)
        self._lock_lease(db, row, p, p["lease_token"], now)
        if row["version"] != p["expected_version"]:
            raise AgentSyncError("version_conflict", "Resource lock version has changed.", 409)
        db.execute(
            "UPDATE file_locks SET version=version+1,updated_at=?,expires_at=? WHERE id=?",
            (now, now + p["lease_seconds"], row["id"]),
        )
        return {**public_lock(self._resource_lock(db, p), now), "lease_token": p["lease_token"]}

    def _release_file_lock(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        row = self._resource_lock(db, p)
        self._lock_lease(db, row, p, p["lease_token"], now)
        if row["version"] != p["expected_version"]:
            raise AgentSyncError("version_conflict", "Resource lock version has changed.", 409)
        db.execute(
            "UPDATE file_locks SET version=version+1,status='released',updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        return public_lock(self._resource_lock(db, p), now)

    def _list_file_locks(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, session: sqlite3.Row | None
    ) -> dict[str, Any]:
        resolve_resource(db, p["project_id"], ".")
        rows = db.execute(
            "SELECT * FROM file_locks WHERE project_id=? "
            "AND (? OR (status='active' AND expires_at>?)) "
            "ORDER BY created_at,id LIMIT ? OFFSET ?",
            (p["project_id"], p["include_expired"], now, p["limit"] + 1, p["offset"]),
        ).fetchall()
        return {
            "locks": [public_lock(row, now) for row in rows[: p["limit"]]],
            "has_more": len(rows) > p["limit"],
        }

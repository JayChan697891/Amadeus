"""Authenticated immutable records for isolated Git workspaces.

Git is called only after all involved project-scoped records have been resolved.
Filesystem receipts survive a rolled-back database transaction and carry no auth.
"""

import json
import sqlite3
import uuid
from typing import Any

from agentsync.errors import AgentSyncError
from agentsync.resources.paths import resolve_resource


class WorkspacesMixin:
    def _workspace_store(self) -> Any:
        from agentsync.workspaces.git import GitWorkspaceStore

        return GitWorkspaceStore(self.data_dir)  # type: ignore[attr-defined]

    @staticmethod
    def _workspace_identity(operation: str, p: dict[str, Any]) -> str:
        # Request ids are never interpolated into paths; auth secrets are not included.
        key = json.dumps([p["project_id"], p["session_id"], operation, p["request_id"]])
        return str(uuid.uuid5(uuid.NAMESPACE_URL, "agentsync-managed-git:" + key))

    @staticmethod
    def _workspace_record(
        db: sqlite3.Connection, table: str, project_id: str, record_id: str
    ) -> dict[str, Any]:
        if table not in {"repository_snapshots", "managed_worktrees", "merge_candidates"}:
            raise ValueError("Unknown workspace record table")
        row = db.execute(
            f"SELECT receipt FROM {table} WHERE id=? AND project_id=?", (record_id, project_id)
        ).fetchone()
        if row is None:
            raise AgentSyncError("not_found", "Workspace record not found.", 404)
        return json.loads(row["receipt"])

    @staticmethod
    def _snapshot_public(receipt: dict[str, Any]) -> dict[str, Any]:
        return {
            "snapshot_id": receipt["id"],
            **{
                key: receipt[key]
                for key in ("base_sha", "source_dirty", "source_status", "committed_only")
            },
        }

    @staticmethod
    def _worktree_public(receipt: dict[str, Any]) -> dict[str, Any]:
        return {
            "worktree_id": receipt["id"],
            **{
                key: receipt[key]
                for key in (
                    "snapshot_id",
                    "task_id",
                    "base_sha",
                    "head_sha",
                    "path",
                    "status",
                    "version",
                )
            },
        }

    @staticmethod
    def _worktree_current(actual: dict[str, Any]) -> dict[str, Any]:
        return {key: actual[key] for key in ("head_sha", "dirty", "status_entries")}

    @staticmethod
    def _candidate_public(receipt: dict[str, Any]) -> dict[str, Any]:
        return {
            key: receipt[key]
            for key in (
                "candidate_id",
                "candidate_sha",
                "base_sha",
                "left_sha",
                "right_sha",
                "changed_paths",
                "status",
            )
        }

    def _capture_repository(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, _: Any
    ) -> dict[str, Any]:
        root = resolve_resource(db, p["project_id"], ".").absolute
        managed = (self.data_dir / "managed-git").resolve()  # type: ignore[attr-defined]
        if managed.is_relative_to(root) or root.is_relative_to(managed):
            raise AgentSyncError(
                "workspace_boundary", "Source and managed repository storage must be disjoint.", 409
            )
        identity = self._workspace_identity("capture_repository", p)
        receipt = self._workspace_store().capture_repository(root, identity)
        db.execute(
            "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
            (
                identity,
                p["project_id"],
                p["session_id"],
                now,
                json.dumps(receipt),
            ),
        )
        return self._snapshot_public(receipt)

    def _create_worktree(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, _: Any
    ) -> dict[str, Any]:
        # Resolve task as well as snapshot before constructing a backend or calling Git.
        self._task(db, p)  # type: ignore[attr-defined]
        snapshot = self._workspace_record(
            db, "repository_snapshots", p["project_id"], p["snapshot_id"]
        )
        identity = self._workspace_identity("create_worktree", p)
        store = self._workspace_store()
        receipt = store.create_worktree(snapshot, identity, task_id=p["task_id"])
        receipt["task_id"] = p["task_id"]
        actual = store.inspect_worktree(receipt)
        db.execute(
            "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
            (
                identity,
                p["project_id"],
                p["snapshot_id"],
                p["task_id"],
                p["session_id"],
                now,
                json.dumps(receipt),
            ),
        )
        return {**self._worktree_public(receipt), **self._worktree_current(actual)}

    def _inspect_worktree(
        self, db: sqlite3.Connection, p: dict[str, Any], _: float, __: Any
    ) -> dict[str, Any]:
        receipt = self._workspace_record(db, "managed_worktrees", p["project_id"], p["worktree_id"])
        actual = self._workspace_store().inspect_worktree(receipt)
        return {**self._worktree_public(receipt), **self._worktree_current(actual)}

    def _workspace_pair(
        self, db: sqlite3.Connection, p: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        left = self._workspace_record(db, "managed_worktrees", p["project_id"], p["left_id"])
        right = self._workspace_record(db, "managed_worktrees", p["project_id"], p["right_id"])
        if left["snapshot_id"] != right["snapshot_id"]:
            raise AgentSyncError(
                "snapshot_mismatch", "Worktrees must share one project snapshot.", 409
            )
        return left, right

    def _compare_worktrees(
        self, db: sqlite3.Connection, p: dict[str, Any], _: float, __: Any
    ) -> dict[str, Any]:
        left, right = self._workspace_pair(db, p)
        return self._workspace_store().compare_worktrees(
            left,
            right,
            p["expected_left_head"].lower(),
            p["expected_right_head"].lower(),
            str(uuid.uuid4()),
        )

    def _prepare_merge_candidate(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, _: Any
    ) -> dict[str, Any]:
        left, right = self._workspace_pair(db, p)
        identity = self._workspace_identity("prepare_merge_candidate", p)
        receipt = self._workspace_store().prepare_merge_candidate(
            left, right, p["expected_left_head"].lower(), p["expected_right_head"].lower(), identity
        )
        db.execute(
            "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
            (
                identity,
                p["project_id"],
                p["left_id"],
                p["right_id"],
                p["session_id"],
                now,
                json.dumps(receipt),
            ),
        )
        return self._candidate_public(receipt)

    def _workspace_replay(
        self, db: sqlite3.Connection, operation: str, p: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        if operation == "capture_repository":
            receipt = self._workspace_record(
                db, "repository_snapshots", p["project_id"], response["snapshot_id"]
            )
            self._workspace_store().verify_snapshot(receipt)
            return self._snapshot_public(receipt)
        if operation == "create_worktree":
            receipt = self._workspace_record(
                db, "managed_worktrees", p["project_id"], response["worktree_id"]
            )
            actual = self._workspace_store().inspect_worktree(receipt)
            if actual["head_sha"] != response["head_sha"]:
                raise AgentSyncError(
                    "stale_snapshot", "Worktree HEAD changed after the original request.", 409
                )
            return {**self._worktree_public(receipt), **self._worktree_current(actual)}
        left, right = self._workspace_pair(db, p)
        receipt = self._workspace_record(
            db, "merge_candidates", p["project_id"], response["candidate_id"]
        )
        actual = self._workspace_store().prepare_merge_candidate(
            left,
            right,
            p["expected_left_head"].lower(),
            p["expected_right_head"].lower(),
            self._workspace_identity(operation, p),
        )
        if actual["candidate_sha"] != receipt["candidate_sha"]:
            raise AgentSyncError(
                "stale_snapshot", "Merge candidate changed after the original request.", 409
            )
        return self._candidate_public(actual)

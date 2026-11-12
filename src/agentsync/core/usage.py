"""Project-owner persistence for unverified adapter usage observations."""

import sqlite3
from dataclasses import asdict
from typing import Any

from agentsync.errors import AgentSyncError
from agentsync.usage import UsageLedger

_MAX_IMPORT_BYTES = 48 * 1024
_MAX_STORED_BYTES = 512 * 1024


def _project_ledger(db: sqlite3.Connection, project_id: str) -> UsageLedger:
    row = db.execute(
        "SELECT checkpoint FROM project_usage WHERE project_id=?", (project_id,)
    ).fetchone()
    if row is None:
        return UsageLedger(project_id)
    try:
        return UsageLedger.from_json(project_id, row["checkpoint"])
    except AgentSyncError:
        raise AgentSyncError("storage_error", "Stored usage history is invalid.", 503) from None


class UsageMixin:
    """Use the same authenticated owner transaction as other owner operations."""

    @staticmethod
    def _owner_import_usage_checkpoint(
        db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        project_id, checkpoint = p["project_id"], p["checkpoint"]
        if len(checkpoint.encode("utf-8")) > _MAX_IMPORT_BYTES:
            raise AgentSyncError("validation_error", "Usage checkpoint exceeds the import limit.")
        incoming = UsageLedger.from_json(project_id, checkpoint)
        merged, added = _project_ledger(db, project_id).merged_with(incoming)
        if added:
            document = merged.to_json()
            if len(document.encode("utf-8")) > _MAX_STORED_BYTES:
                raise AgentSyncError(
                    "history_capacity_exceeded", "Usage history is exhausted.", 409
                )
            db.execute(
                "INSERT INTO project_usage(project_id,checkpoint,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET "
                "checkpoint=excluded.checkpoint, updated_at=excluded.updated_at",
                (project_id, document, now),
            )
        return {
            "added_records": added,
            "duplicate_records": incoming.summary().total_records - added,
        }

    @staticmethod
    def _owner_get_usage_summary(
        db: sqlite3.Connection, p: dict[str, Any], _: float
    ) -> dict[str, Any]:
        return asdict(_project_ledger(db, p["project_id"]).summary())

    @staticmethod
    def _owner_get_usage_run(db: sqlite3.Connection, p: dict[str, Any], _: float) -> dict[str, Any]:
        return asdict(_project_ledger(db, p["project_id"]).get_run(p["kind"], p["run_id"]))

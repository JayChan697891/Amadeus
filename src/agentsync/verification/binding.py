"""Owner-only immutable DB provenance. No filesystem or execution verification."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import Field

from agentsync.errors import AgentSyncError
from agentsync.models import AdminAuth, CommitSHA
from agentsync.storage.database import connect

if TYPE_CHECKING:
    from agentsync.core.service import Core


class _Capture(AdminAuth):
    project_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    expected_candidate_sha: CommitSHA


@dataclass(frozen=True)
class CandidateBinding:
    source_kind: str
    project_id: str
    candidate_id: str
    snapshot_id: str
    candidate_sha: str
    base_sha: str
    left_sha: str
    right_sha: str
    left_worktree_id: str
    right_worktree_id: str
    left_task_id: str
    right_task_id: str
    left_task_version: int
    right_task_version: int
    creator_session_ids: tuple[str, ...]
    receipts: tuple[str, ...]
    provenance_sha256: str


def _invalid() -> NoReturn:
    raise AgentSyncError("invalid_candidate_binding", "Stored candidate metadata is invalid.", 409)


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _receipt(raw: Any) -> dict[str, Any]:
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 65536:
            _invalid()
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: _invalid())
        if not isinstance(value, dict):
            _invalid()
        # Also rejects numeric overflow (1e999), invalid Unicode and excessive nesting.
        _canonical(value).encode("utf-8")
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _invalid()


def _sha(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        _invalid()
    return value


def _row(db: sqlite3.Connection, table: str, project: str, identity: str) -> sqlite3.Row:
    # All table names are fixed internal call sites, never supplied by a caller.
    row = db.execute(
        f"SELECT * FROM {table} WHERE id=? AND project_id=?", (identity, project)
    ).fetchone()
    if row is None:
        _invalid()
    assert row is not None
    return row


def _identity(receipt: dict[str, Any], row: sqlite3.Row, operation: str, key: str = "id") -> None:
    if receipt.get("operation") != operation or receipt.get(key) != row["id"]:
        _invalid()


class OwnerCandidateBindings:
    def __init__(self, core: Core):
        self.core = core

    def capture(
        self, *, project_id: str, admin_token: str, candidate_id: str, expected_candidate_sha: str
    ) -> CandidateBinding:
        p = self.core._validated_payload(
            _Capture,
            {
                "project_id": project_id,
                "admin_token": admin_token,
                "candidate_id": candidate_id,
                "expected_candidate_sha": expected_candidate_sha,
            },
        )
        try:
            db = connect(self.core.db_path)
        except sqlite3.Error:
            raise AgentSyncError(
                "storage_error", "Candidate metadata storage unavailable.", 503
            ) from None
        try:
            db.execute("BEGIN")
            self.core._authenticate_owner(db, p)
            candidate = db.execute(
                "SELECT * FROM merge_candidates WHERE id=? AND project_id=?",
                (candidate_id, project_id),
            ).fetchone()
            if candidate is None:
                raise AgentSyncError("not_found", "Candidate not found.", 404)
            left = _row(db, "managed_worktrees", project_id, candidate["left_id"])
            right = _row(db, "managed_worktrees", project_id, candidate["right_id"])
            if left["snapshot_id"] != right["snapshot_id"]:
                _invalid()
            snapshot = _row(db, "repository_snapshots", project_id, left["snapshot_id"])
            tasks = tuple(_row(db, "tasks", project_id, item["task_id"]) for item in (left, right))
            for row in (candidate, left, right, snapshot):
                session = _row(db, "sessions", project_id, row["creator_session_id"])
                _row(db, "agents", project_id, session["agent_id"])
            cr, lr, rr, sr = tuple(
                _receipt(row["receipt"]) for row in (candidate, left, right, snapshot)
            )
            _identity(cr, candidate, "candidate", "candidate_id")
            _identity(sr, snapshot, "capture")
            base, sha = _sha(sr.get("base_sha")), _sha(cr.get("candidate_sha"))
            if sha != expected_candidate_sha.lower():
                raise AgentSyncError("version_conflict", "Candidate revision changed.", 409)
            for row, receipt in ((left, lr), (right, rr)):
                _identity(receipt, row, "create")
                if any(
                    receipt.get(key) != expected
                    for key, expected in {
                        "snapshot_id": snapshot["id"],
                        "task_id": row["task_id"],
                        "base_sha": base,
                        "head_sha": base,
                        "repository_path": sr.get("repository_path"),
                        "repository_identity": sr.get("root_identity"),
                        "config_sha256": sr.get("config_sha256"),
                    }.items()
                ):
                    _invalid()
            if not isinstance(sr.get("repository_path"), str) or not sr["repository_path"]:
                _invalid()
            identity = sr.get("root_identity")
            if (
                not isinstance(identity, list)
                or len(identity) != 2
                or any(not isinstance(v, str) or not v for v in identity)
            ):
                _invalid()
            if (
                not isinstance(sr.get("config_sha256"), str)
                or re.fullmatch("[0-9a-f]{64}", sr["config_sha256"]) is None
            ):
                _invalid()
            lh, rh = _sha(cr.get("left_sha")), _sha(cr.get("right_sha"))
            expected_binding = {
                "operation": "merge",
                "snapshot_id": snapshot["id"],
                "right_snapshot_id": snapshot["id"],
                "base_sha": base,
                "right_base_sha": base,
                "left_id": left["id"],
                "right_id": right["id"],
                "left": lh,
                "right": rh,
            }
            if cr.get("base_sha") != base or cr.get("input_binding") != expected_binding:
                _invalid()
            versions = tuple(task["version"] for task in tasks)
            if any(type(v) is not int or not 1 <= v <= 2**63 - 1 for v in versions):
                _invalid()
            receipts = tuple(_canonical(value) for value in (sr, lr, rr, cr))
            fields = {
                "source_kind": "managed_merge_candidate_metadata",
                "project_id": project_id,
                "candidate_id": candidate_id,
                "snapshot_id": snapshot["id"],
                "candidate_sha": sha,
                "base_sha": base,
                "left_sha": lh,
                "right_sha": rh,
                "left_worktree_id": left["id"],
                "right_worktree_id": right["id"],
                "left_task_id": left["task_id"],
                "right_task_id": right["task_id"],
                "left_task_version": versions[0],
                "right_task_version": versions[1],
            }
            creators = tuple(
                row["creator_session_id"] for row in (snapshot, left, right, candidate)
            )
            provenance = {
                "schema": "agentsync.candidate-binding.v1",
                **fields,
                "receipt_sha256": [_hash(value) for value in receipts],
                "creator_session_ids": creators,
            }
            return CandidateBinding(
                **fields,
                creator_session_ids=creators,
                receipts=receipts,
                provenance_sha256=_hash(_canonical(provenance)),
            )
        except sqlite3.Error:
            raise AgentSyncError(
                "storage_error", "Candidate metadata storage unavailable.", 503
            ) from None
        finally:
            db.rollback()
            db.close()

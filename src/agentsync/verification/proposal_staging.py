"""Owner-only, once-per-task staging of an authenticated inert publication.

This service authenticates publication, not model authorship. Preview is read-only;
stage_once binds explicit owner consent to its exact plan digest. It neither
executes code nor changes task state, queues verification or applies to source.
"""

from __future__ import annotations

import json
import math
import sqlite3
import stat
import time
import uuid
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import Field

from agentsync.proposals import parse_proposal
from agentsync.verification.binding import _receipt
from agentsync.verification.candidate import _linked_directory, _text
from agentsync.verification.candidate_jobs import (
    CandidateVerificationJobs,
    _dump,
    _error,
    _hash,
    _load,
    _Owner,
)
from agentsync.verification.snapshot import _repository
from agentsync.workspaces.git import GitWorkspaceStore, physical
from agentsync.workspaces.proposal import check_paths, stage_worktree, tree_modes

if TYPE_CHECKING:
    from agentsync.core.service import Core

_INTENT = "proposal_staging_admit"
_DONE = "proposal_staging_finish"


class _Lookup(_Owner):
    task_id: str = Field(min_length=1, max_length=200)


class _Plan(_Lookup):
    session_id: str = Field(min_length=1, max_length=200)
    session_token: str = Field(min_length=1, max_length=4096)
    expected_task_version: int = Field(ge=1, le=2**63 - 2)
    context_id: str = Field(min_length=1, max_length=200)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_session_id: str = Field(min_length=1, max_length=200)
    publication_request_id: str = Field(min_length=1, max_length=200)


class _Decision(_Plan):
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _reject() -> NoReturn:
    _error("proposal_staging_changed", "Publication, authority or staging pins do not match.")


def _saved(
    db: sqlite3.Connection, project: str, operation: str, task: str
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT payload_hash,response FROM owner_idempotency WHERE project_id=? AND operation=? AND request_id=?",
        (project, operation, task),
    ).fetchone()
    if row is None:
        return None
    data = _load(row["response"], 65536)
    if type(data) is not dict or _hash(_dump(data)) != row["payload_hash"]:
        _reject()
    return data


def _save(
    db: sqlite3.Connection, project: str, operation: str, task: str, value: dict[str, Any]
) -> None:
    raw = _dump(value)
    db.execute(
        "INSERT INTO owner_idempotency VALUES(?,?,?,?,?)",
        (project, operation, task, _hash(raw), raw),
    )


class OwnerProposalStaging:
    """Requires separate project-owner and active staging-worker credentials."""

    def __init__(self, core: Core):
        self._core = core
        self._jobs = CandidateVerificationJobs(core)

    def _plan(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, str]]]:
        session = self._core._authenticate(db, p, now)
        self._core._authorize_session(db, "create_worktree", session)
        task = self._core._task(db, p)
        if task["version"] != p["expected_task_version"] or task["status"] != "review":
            _reject()
        revision = db.execute(
            "SELECT * FROM context_revisions WHERE project_id=? AND context_id=? AND version=1",
            (p["project_id"], p["context_id"]),
        ).fetchone()
        publication = db.execute(
            "SELECT response FROM idempotency WHERE project_id=? AND session_id=? AND operation='publish_task_proposal' AND request_id=?",
            (p["project_id"], p["publication_session_id"], p["publication_request_id"]),
        ).fetchone()
        if (
            revision is None
            or publication is None
            or _hash(revision["content"]) != p["expected_content_sha256"]
        ):
            _reject()
        assert revision is not None and publication is not None
        saved = _load(publication["response"], 16384)
        content = _load(revision["content"], 65536)
        if type(content) is not dict or set(content) != {
            "format",
            "project_id",
            "task_id",
            "task_version",
            "worktree_id",
            "base_head",
            "execution_provenance",
            "files",
        }:
            _reject()
        if not isinstance(content["files"], list):
            _reject()
        paths: list[str] = []
        for item in content["files"]:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                _reject()
            paths.append(item["path"])
        files = parse_proposal(_dump({"files": content["files"]}), paths)
        expected = {
            "context_id": p["context_id"],
            "context_version": 1,
            "content_sha256": p["expected_content_sha256"],
            "task_id": p["task_id"],
            "task_version": content["task_version"],
            "worktree_id": content["worktree_id"],
            "base_head": content["base_head"],
            "verification": "unverified",
            "execution_provenance": "unverified",
        }
        if (
            saved != expected
            or content["format"] != "amadeus-source-proposal-v1"
            or content["project_id"] != p["project_id"]
            or content["task_id"] != p["task_id"]
            or content["execution_provenance"] != "unverified"
            or type(content["task_version"]) is not int
            or not 1 <= content["task_version"] < task["version"]
            or revision["author_session_id"] != p["publication_session_id"]
            or task["owner_session_id"] != p["publication_session_id"]
        ):
            _reject()
        author = db.execute(
            "SELECT agent_id FROM sessions WHERE project_id=? AND id=?",
            (p["project_id"], p["publication_session_id"]),
        ).fetchone()
        if author is None or revision["author_agent_id"] != author["agent_id"]:
            _reject()
        audit = db.execute(
            "SELECT 1 FROM audit_events WHERE project_id=? AND actor_kind='agent' AND actor_id=? AND operation='publish_task_proposal' AND target_id=? AND outcome='success' AND code='ok' AND request_id_digest=?",
            (
                p["project_id"],
                author["agent_id"],
                content["worktree_id"],
                _hash(p["publication_request_id"]),
            ),
        ).fetchone()
        if audit is None:
            _reject()
        row = db.execute(
            "SELECT * FROM managed_worktrees WHERE project_id=? AND id=? AND task_id=?",
            (p["project_id"], content["worktree_id"], p["task_id"]),
        ).fetchone()
        if row is None:
            _reject()
        assert row is not None
        creator = db.execute(
            "SELECT agent_id FROM sessions WHERE project_id=? AND id=?",
            (p["project_id"], row["creator_session_id"]),
        ).fetchone()
        if creator is None or creator["agent_id"] != author["agent_id"]:
            _reject()
        original = self._core._workspace_record(db, "managed_worktrees", p["project_id"], row["id"])
        snapshot = self._core._workspace_record(
            db, "repository_snapshots", p["project_id"], row["snapshot_id"]
        )
        if (
            original["task_id"] != p["task_id"]
            or original["snapshot_id"] != snapshot["id"]
            or original["id"] != row["id"]
            or snapshot["id"] != row["snapshot_id"]
            or original["operation"] != "create"
            or snapshot["operation"] != "capture"
            or original["base_sha"] != snapshot["base_sha"]
            or original["head_sha"] != snapshot["base_sha"]
        ):
            _reject()
        store = GitWorkspaceStore(self._core.data_dir, create=False)
        # Validate saved receipts and foreign Git indirection before any Git
        # process can read the corresponding directory/configuration.
        for record in (snapshot, original):
            disk = _receipt(_text(store._path("receipts", record["id"])))
            if disk != record:
                _reject()
        expected_intents = (
            (
                snapshot["id"],
                {
                    "operation": "capture",
                    "source": snapshot["source_root"],
                    "base_sha": snapshot["base_sha"],
                },
            ),
            (
                original["id"],
                {"operation": "create", "snapshot_id": snapshot["id"], "task_id": p["task_id"]},
            ),
        )
        for identity, expected_intent in expected_intents:
            if _receipt(_text(store._path("intents", identity))) != expected_intent:
                _reject()
        expected_repo = store._path("repositories", snapshot["id"])
        redirect = expected_repo / ".git"
        if redirect.exists() or redirect.is_symlink():
            _error("workspace_boundary", "Managed repository cannot contain a Git redirect.")
        config = expected_repo / "config"
        physical(config)
        if not stat.S_ISREG(config.stat().st_mode):
            _error("workspace_boundary", "Managed repository configuration must be regular.")
        repo = _repository(store, snapshot)
        hooks = store.root / "hooks"
        physical(hooks)
        if any(hooks.iterdir()):
            _error("workspace_boundary", "Proposal staging requires empty managed hooks.")
        store._source_config(repo)
        original_path = store._path("worktrees", original["id"])
        if (
            str(original_path) != original["path"]
            or physical(original_path) != original["root_identity"]
        ):
            _reject()
        _linked_directory(store, original_path, repo)
        actual = store.inspect_worktree(original)
        if actual["dirty"] or actual["head_sha"] != content["base_head"]:
            _reject()
        tree_modes(store, repo, snapshot["base_sha"])
        modes = tree_modes(store, repo, content["base_head"])
        check_paths(modes, files)
        identity = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "amadeus-proposal-stage:" + _dump([p["project_id"], p["task_id"], p["context_id"]]),
            )
        )
        candidate_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "amadeus-proposal-candidate:" + identity))
        plan = {
            "schema": "amadeus.owner-proposal-stage.v1",
            "project_id": p["project_id"],
            "task_id": p["task_id"],
            "task_version": task["version"],
            "context_id": p["context_id"],
            "context_version": 1,
            "content_sha256": p["expected_content_sha256"],
            "publication_session_id": p["publication_session_id"],
            "publication_request_sha256": _hash(p["publication_request_id"]),
            "publication_response_sha256": _hash(_dump(saved)),
            "publication_task_version": content["task_version"],
            "staging_session_id": session["id"],
            "staging_agent_id": session["agent_id"],
            "snapshot_id": snapshot["id"],
            "snapshot_sha256": _hash(_dump(snapshot)),
            "original_worktree_id": original["id"],
            "original_receipt_sha256": _hash(_dump(original)),
            "base_head": content["base_head"],
            "staging_worktree_id": identity,
            "candidate_id": candidate_id,
            "files": [
                {
                    "path": item["path"],
                    "sha256": _hash(item["content"]),
                    "utf8_bytes": len(item["content"].encode("utf-8")),
                    "mode": modes.get(item["path"], "100644"),
                }
                for item in files
            ],
            "model_provenance": "unverified",
            "task_verification": "unverified",
        }
        return plan, snapshot, original, files

    def preview(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Plan, payload)
        with self._jobs._transaction(p) as (db, now):
            if _saved(db, p["project_id"], _INTENT, p["task_id"]) is not None:
                _error("proposal_staging_exists", "This task already has a staging attempt.")
            plan, _, _, _ = self._plan(db, p, now)
            return {"plan": plan, "plan_sha256": _hash(_dump(plan))}

    def _final_authority(self, db: sqlite3.Connection, p: dict[str, Any], earliest: float) -> None:
        now = time.time()
        if not math.isfinite(now) or now < earliest:
            _error("clock_regressed", "Staging requires a finite non-regressed clock.")
        self._core._authenticate_owner(db, p)
        session = self._core._authenticate(db, p, now)
        self._core._authorize_session(db, "create_worktree", session)

    def stage_once(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Decision, payload)
        project, task_id = p["project_id"], p["task_id"]
        with self._jobs._transaction(p, write=True, operation=_INTENT) as (db, now):
            if _saved(db, project, _INTENT, task_id) is not None:
                _error("proposal_staging_exists", "This task already has a staging attempt.")
            plan, _, _, _ = self._plan(db, p, now)
            if _hash(_dump(plan)) != p["expected_plan_sha256"]:
                _reject()
            self._final_authority(db, p, now)
            _save(db, project, _INTENT, task_id, plan)
            self._core._audit_event(
                db, project, "owner", project, _INTENT, p, "success", "ok", {"task_id": task_id}
            )
        # Intent commits before any effect. Exceptions retain the fence; observing
        # incomplete work never calls the mutation path or attempts recovery.
        with self._jobs._transaction(p, write=True, operation=_DONE) as (db, now):
            current, snapshot, original, files = self._plan(db, p, now)
            if current != plan or _saved(db, project, _INTENT, task_id) != plan:
                _reject()
            store = GitWorkspaceStore(self._core.data_dir, create=False)
            created, head = stage_worktree(
                store, snapshot, original, files, plan["base_head"], plan["staging_worktree_id"]
            )
            candidate = store.prepare_merge_candidate(
                created, original, head, plan["base_head"], plan["candidate_id"]
            )
            self._final_authority(db, p, now)
            db.execute(
                "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
                (
                    created["id"],
                    project,
                    snapshot["id"],
                    task_id,
                    p["session_id"],
                    now,
                    json.dumps(created),
                ),
            )
            db.execute(
                "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
                (
                    candidate["candidate_id"],
                    project,
                    created["id"],
                    original["id"],
                    p["session_id"],
                    now,
                    json.dumps(candidate),
                ),
            )
            response = {
                "plan_sha256": p["expected_plan_sha256"],
                "task_id": task_id,
                "worktree_id": created["id"],
                "head_sha": head,
                "candidate_id": candidate["candidate_id"],
                "candidate_sha": candidate["candidate_sha"],
                "verification": "unverified",
                "execution_started": False,
            }
            _save(db, project, _DONE, task_id, response)
            self._core._audit_event(
                db, project, "owner", project, _DONE, p, "success", "ok", response
            )
            return {"state": "staged", **response}

    def status(self, **payload: Any) -> dict[str, Any]:
        """Historical owner-only metadata; no fresh execution/apply authority."""
        p = self._core._validated_payload(_Lookup, payload)
        with self._jobs._transaction(p) as (db, _):
            plan = _saved(db, p["project_id"], _INTENT, p["task_id"])
            result = _saved(db, p["project_id"], _DONE, p["task_id"])
            if plan is None:
                if result is not None:
                    _reject()
                return {"state": "not_started", "verification": "unverified"}
            if result is not None and result.get("plan_sha256") != _hash(_dump(plan)):
                _reject()
            return {
                "state": "staged" if result is not None else "incomplete",
                "historical": True,
                "verification": "unverified",
                "plan": plan,
                "result": result,
            }

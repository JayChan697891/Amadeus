"""Owner-approved create-only delivery to a private managed Git ref.

This service never writes to the registered source checkout. A dedicated plan
approval binds the exact verified candidate and destination. Consumption and
the permanent intent commit before Git. Observation never attempts creation.
"""

from __future__ import annotations

import dataclasses
import hmac
import math
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import Field

from agentsync.errors import AgentSyncError
from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import (
    CandidateVerificationJobs,
    _dump,
    _error,
    _hash,
    _load,
    _Owner,
)
from agentsync.verification.snapshot import _repository
from agentsync.verification.task_completion import task_projection
from agentsync.workspaces.git import GitWorkspaceStore, physical, valid_sha

if TYPE_CHECKING:
    from agentsync.core.service import Core


class _Lookup(_Owner):
    approval_id: str = Field(min_length=1, max_length=200)


class _Plan(_Lookup):
    expected_version: int = Field(ge=1, le=2**63 - 4)
    task_id: str = Field(min_length=1, max_length=200)
    expected_task_version: int = Field(ge=1, le=2**63 - 2)
    session_id: str = Field(min_length=1, max_length=200)
    session_token: str = Field(min_length=1, max_length=4096)


class _Decision(_Plan):
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


_APPROVED = "candidate_delivery_approve"
_INTENT = "candidate_delivery_admit"
_FENCE = "candidate_delivery_fence"


def _reject_plan() -> NoReturn:
    _error("delivery_plan_changed", "The verified candidate delivery plan does not match.")


def _entry(
    db: sqlite3.Connection, project: str, operation: str, identity: str
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT payload_hash,response FROM owner_idempotency "
        "WHERE project_id=? AND operation=? AND request_id=?",
        (project, operation, identity),
    ).fetchone()
    if row is None:
        return None
    data = _load(row["response"], 16384)
    if type(data) is not dict or not hmac.compare_digest(row["payload_hash"], _hash(_dump(data))):
        _reject_plan()
    return data


def _save(
    db: sqlite3.Connection, project: str, operation: str, identity: str, data: dict[str, Any]
) -> None:
    document = _dump(data)
    db.execute(
        "INSERT INTO owner_idempotency VALUES(?,?,?,?,?)",
        (project, operation, identity, _hash(document), document),
    )


def _ref(candidate_id: str) -> str:
    return "refs/agentsync/deliveries/" + _hash(candidate_id)


def _managed_repo(store: GitWorkspaceStore, snapshot: dict[str, Any]) -> Path:
    expected = store._path("repositories", snapshot["id"])
    try:
        (expected / ".git").lstat()
    except FileNotFoundError:
        return _repository(store, snapshot)
    _error("workspace_boundary", "A managed delivery repository cannot have a Git redirect.")


class OwnerCandidateDelivery:
    """Preview, approve and publish one verified candidate in managed storage."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._jobs = CandidateVerificationJobs(core)

    def _approval(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, state: str
    ) -> sqlite3.Row:
        requester = self._core._authenticate(db, p, now)
        self._core._authorize_session(db, "request_approval", requester)
        approval = self._core._approval(db, p, requester["agent_id"])
        if (
            approval["action"] != "apply_merge_candidate"
            or approval["subject_version"] != 1
            or approval["version"] != p["expected_version"]
            or approval["status"] != state
            or now < approval["updated_at"]
            or not now < approval["expires_at"]
        ):
            _reject_plan()
        return approval

    def _plan(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, state: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        approval = self._approval(db, p, now, state)
        task = self._core._task(db, p)
        if task["version"] != p["expected_task_version"] or task["status"] != "completed":
            _reject_plan()
        proof = task_projection(db, task)["verification"]
        if proof is None or proof["candidate_sha"] != approval["subject_sha"]:
            _reject_plan()
        job = self._jobs._row(db, p["project_id"], proof["job_id"])
        if job["candidate_id"] != approval["subject_id"]:
            _reject_plan()
        exported = OwnerCandidateExporter(self._core).export(
            project_id=p["project_id"],
            admin_token=p["admin_token"],
            candidate_id=job["candidate_id"],
            expected_candidate_sha=job["candidate_sha"],
        )
        binding = exported.binding
        prior = _load(job["metadata_json"], 4 * 1024 * 1024)["binding"]
        current = dataclasses.asdict(binding)
        for key in ("left_task_version", "right_task_version", "provenance_sha256"):
            current.pop(key)
        if any(_dump(value) != _dump(prior[key]) for key, value in current.items()):
            _reject_plan()
        for side in ("left", "right"):
            original = proof[f"{side}_task_version"]
            expected = original + int(task["id"] == proof[f"{side}_task_id"])
            if getattr(binding, f"{side}_task_version") != expected:
                _reject_plan()
        snapshot = exported.snapshot
        if (
            snapshot.commit_sha != proof["candidate_sha"]
            or snapshot.tree_sha != proof["tree_sha"]
            or snapshot.input_sha256 != proof["input_sha256"]
            or _hash(snapshot.source) != proof["source_sha256"]
        ):
            _reject_plan()
        plan = {
            "schema": "agentsync.managed-delivery-plan.v1",
            "approval_id": p["approval_id"],
            "pending_version": approval["version"] - int(state == "approved"),
            "requester_agent_id": approval["requester_agent_id"],
            "requester_session_id": p["session_id"],
            "task_id": task["id"],
            "task_version": task["version"],
            "verification_id": proof["id"],
            "verification_sha256": _hash(_dump(proof)),
            "candidate_id": job["candidate_id"],
            "candidate_sha": snapshot.commit_sha,
            "tree_sha": snapshot.tree_sha,
            "snapshot_id": binding.snapshot_id,
            "snapshot_receipt_sha256": _hash(binding.receipts[0]),
            "current_binding_sha256": binding.provenance_sha256,
            "destination_ref": _ref(job["candidate_id"]),
            "expires_at": approval["expires_at"],
        }
        return plan, _load(binding.receipts[0], 16384)

    @staticmethod
    def _now(earliest: float) -> float:
        now = time.time()
        if not math.isfinite(now) or now < earliest:
            _error("clock_regressed", "Delivery requires a finite non-regressed clock.")
        return now

    def preview(self, **payload: Any) -> dict[str, Any]:
        """Read the exact plan while the corresponding candidate request is pending."""
        p = self._core._validated_payload(_Plan, payload)
        with self._jobs._transaction(p) as (db, now):
            plan, _ = self._plan(db, p, now, "pending")
            return {"plan": plan, "plan_sha256": _hash(_dump(plan))}

    def approve(self, **payload: Any) -> dict[str, Any]:
        """Approve the reviewed plan hash, rather than a generic destination."""
        p = self._core._validated_payload(_Decision, payload)
        with self._jobs._transaction(p, write=True, operation=_APPROVED) as (db, now):
            plan, _ = self._plan(db, p, now, "pending")
            if _hash(_dump(plan)) != p["plan_sha256"]:
                _reject_plan()
            final_now = self._now(now)
            self._approval(db, p, final_now, "pending")
            approval = self._core._change_approval(db, p, final_now, "approved", {"pending"})
            _save(db, p["project_id"], _APPROVED, p["approval_id"], plan)
            self._core._audit_event(
                db,
                p["project_id"],
                "owner",
                p["project_id"],
                _APPROVED,
                p,
                "allowed",
                "ok",
                approval,
            )
            return {"plan_sha256": p["plan_sha256"], "approval": approval}

    @staticmethod
    def _observe_ref(store: GitWorkspaceStore, repo: Path, plan: dict[str, Any]) -> str:
        _, raw = store._git(
            repo,
            "for-each-ref",
            "--format=%(refname)%00%(objectname)%00%(symref)",
            "--",
            plan["destination_ref"],
        )
        if not raw:
            loose = repo.joinpath(*plan["destination_ref"].split("/"))
            try:
                loose.lstat()
            except FileNotFoundError:
                pass
            else:
                return "mismatch"
            code, _ = store._git(
                repo, "symbolic-ref", "--quiet", plan["destination_ref"], accepted=(0, 1, 128)
            )
            if code == 0:
                return "mismatch"
            return "absent"
        expected = (plan["destination_ref"] + "\0" + plan["candidate_sha"] + "\0").encode("ascii")
        return "exact" if raw.splitlines() == [expected] else "mismatch"

    def publish_once(self, **payload: Any) -> dict[str, Any]:
        """Consume the approved plan before one fixed create-only managed Git effect."""
        p = self._core._validated_payload(_Decision, payload)
        project, approval_id = p["project_id"], p["approval_id"]
        with self._jobs._transaction(p, write=True, operation=_INTENT) as (db, now):
            self._approval(db, p, now, "approved")
            approved = _entry(db, project, _APPROVED, approval_id)
            if approved is None or _hash(_dump(approved)) != p["plan_sha256"]:
                _reject_plan()
            plan, snapshot = self._plan(db, p, now, "approved")
            if approved != plan:
                _reject_plan()
            if _entry(db, project, _FENCE, plan["candidate_id"]) is not None:
                _error("delivery_reserved", "A candidate delivery is already reserved.")
            store = GitWorkspaceStore(self._core.data_dir, create=False)
            repo = _managed_repo(store, snapshot)
            if self._observe_ref(store, repo, plan) != "absent":
                _error("delivery_reserved", "The managed delivery destination already exists.")
            final_now = self._now(now)
            self._approval(db, p, final_now, "approved")
            consumed = self._core._change_approval(db, p, final_now, "consumed", {"approved"})
            _save(db, project, _INTENT, approval_id, plan)
            _save(db, project, _FENCE, plan["candidate_id"], {"approval_id": approval_id})
            self._core._audit_event(
                db, project, "owner", project, _INTENT, p, "allowed", "ok", consumed
            )
        try:
            # The durable intent is irrevocable. A late failure retains it and
            # the consumed approval without creating or retrying another ref.
            with self._jobs._transaction(p, write=True, operation=_INTENT) as (db, admitted_now):
                requester = self._core._authenticate(db, p, admitted_now)
                self._core._authorize_session(db, "request_approval", requester)
                approval = self._core._approval(db, p, requester["agent_id"])
                current = self._core._task(db, p)
                proof = task_projection(db, current)["verification"]
                if (
                    requester["agent_id"] != plan["requester_agent_id"]
                    or requester["id"] != plan["requester_session_id"]
                    or not final_now <= admitted_now < plan["expires_at"]
                    or approval["status"] != "consumed"
                    or approval["version"] != p["expected_version"] + 1
                    or approval["subject_id"] != plan["candidate_id"]
                    or approval["subject_sha"] != plan["candidate_sha"]
                    or current["version"] != plan["task_version"]
                    or proof is None
                    or _hash(_dump(proof)) != plan["verification_sha256"]
                ):
                    _reject_plan()
                binding = OwnerCandidateBindings(self._core)._capture_in_transaction(
                    db,
                    project_id=project,
                    admin_token=p["admin_token"],
                    candidate_id=plan["candidate_id"],
                    expected_candidate_sha=plan["candidate_sha"],
                )
                if binding.provenance_sha256 != plan["current_binding_sha256"]:
                    _reject_plan()
                checked_snapshot = OwnerCandidateExporter._check(store, binding)
                if checked_snapshot != snapshot:
                    _reject_plan()
                repo = _managed_repo(store, checked_snapshot)
                hooks = store.root / "hooks"
                physical(hooks)
                if not hooks.is_dir() or any(hooks.iterdir()):
                    _error(
                        "workspace_boundary", "Managed delivery requires an empty hooks directory."
                    )
                if self._observe_ref(store, repo, plan) != "absent":
                    _error("delivery_reserved", "The managed delivery destination already exists.")
                dispatch_now = self._now(admitted_now)
                if dispatch_now >= min(plan["expires_at"], requester["expires_at"]):
                    _reject_plan()
                sha = valid_sha(plan["candidate_sha"])
                store._git(
                    repo, "update-ref", "--no-deref", plan["destination_ref"], sha, "0" * len(sha)
                )
                observed = self._observe_ref(store, repo, plan)
        except (AgentSyncError, OSError, UnicodeError, ValueError):
            observed = "unresolved"
        return {"plan": plan, "approval_status": "consumed", "effect": observed}

    def observe(self, **payload: Any) -> dict[str, Any]:
        """Inspect the reserved fixed reference. An absent ref is never recreated."""
        p = self._core._validated_payload(_Lookup, payload)
        with self._jobs._transaction(p) as (db, _):
            plan = _entry(db, p["project_id"], _INTENT, p["approval_id"])
            if plan is None:
                _error("not_found", "No managed delivery intent exists.", 404)
            approval = self._core._approval(db, p)
            approved = _entry(db, p["project_id"], _APPROVED, p["approval_id"])
            return self._observe_reserved(db, p, approval, approved, plan)

    def status(self, **payload: Any) -> dict[str, Any]:
        """Inspect saved approval and delivery evidence without an active requester session."""
        p = self._core._validated_payload(_Lookup, payload)
        project, approval_id = p["project_id"], p["approval_id"]
        with self._jobs._transaction(p) as (db, now):
            approval = self._core._approval(db, p)
            if approval["action"] != "apply_merge_candidate":
                _error("not_found", "No managed delivery approval exists.", 404)
            approved = _entry(db, project, _APPROVED, approval_id)
            intent = _entry(db, project, _INTENT, approval_id)
            if intent is not None:
                return self._observe_reserved(db, p, approval, approved, intent)
            fence = _entry(db, project, _FENCE, approval["subject_id"])
            if approval["status"] == "consumed" or fence == {"approval_id": approval_id}:
                _reject_plan()
            if approved is not None and (
                approved.get("approval_id") != approval_id
                or approved.get("candidate_id") != approval["subject_id"]
                or approved.get("candidate_sha") != approval["subject_sha"]
                or approved.get("requester_agent_id") != approval["requester_agent_id"]
                or type(approved.get("pending_version")) is not int
                or approval["version"] <= approved["pending_version"]
            ):
                _reject_plan()
            return {
                "plan": approved,
                "approval_status": self._core._public_approval(approval, now)["status"],
                "effect": "not_attempted",
            }

    def _observe_reserved(
        self,
        db: sqlite3.Connection,
        p: dict[str, Any],
        approval: sqlite3.Row,
        approved: dict[str, Any] | None,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            approval["action"] != "apply_merge_candidate"
            or approval["status"] != "consumed"
            or plan["approval_id"] != p["approval_id"]
            or approval["version"] != plan["pending_version"] + 2
            or approval["subject_id"] != plan["candidate_id"]
            or approval["subject_sha"] != plan["candidate_sha"]
            or approved != plan
            or _entry(db, p["project_id"], _FENCE, plan["candidate_id"])
            != {"approval_id": p["approval_id"]}
        ):
            _reject_plan()
        row = db.execute(
            "SELECT receipt FROM repository_snapshots WHERE id=? AND project_id=?",
            (plan["snapshot_id"], p["project_id"]),
        ).fetchone()
        if row is None or plan["destination_ref"] != _ref(plan["candidate_id"]):
            _reject_plan()
        snapshot = _load(row["receipt"], 16384)
        if _hash(_dump(snapshot)) != plan["snapshot_receipt_sha256"]:
            _reject_plan()
        store = GitWorkspaceStore(self._core.data_dir, create=False)
        return {
            "plan": plan,
            "approval_status": "consumed",
            "effect": self._observe_ref(store, _managed_repo(store, snapshot), plan),
        }

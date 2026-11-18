"""Explicit owner integration of an exact verified candidate into a new worktree."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from pydantic import Field

from agentsync.errors import AgentSyncError
from agentsync.verification.binding import OwnerCandidateBindings
from agentsync.verification.candidate import CandidateInput, OwnerCandidateExporter
from agentsync.verification.candidate_delivery import (
    OwnerCandidateDelivery,
    _entry,
    _Lookup,
    _Plan,
    _save,
)
from agentsync.verification.candidate_jobs import (
    CandidateVerificationJobs,
    _dump,
    _error,
    _hash,
    _load,
)
from agentsync.verification.task_completion import task_projection
from agentsync.workspaces.git import GitWorkspaceStore, physical
from agentsync.workspaces.integration import (
    IntegrationGit,
    _exists,
    _normal_path,
    _overlaps,
    integration_path,
)

if TYPE_CHECKING:
    from agentsync.core.service import Core

_APPROVED = "candidate_integration_approve"
_INTENT = "candidate_integration_admit"
_EFFECT = "candidate_integration_observed"
_FENCE = "candidate_integration_fence"


class _IntegrationPlan(_Plan):
    target_root: str = Field(min_length=1, max_length=1024)
    worktree_path: str = Field(min_length=1, max_length=1024)
    destination_branch: str = Field(min_length=1, max_length=80)


class _Decision(_IntegrationPlan):
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _reject() -> NoReturn:
    _error(
        "integration_plan_changed", "The exact verified candidate integration plan does not match."
    )


def _fence_keys(plan: dict[str, Any]) -> tuple[str, str]:
    return (
        _hash(_dump(["branch", plan["target_git_identity"], plan["destination_ref"].casefold()])),
        _hash(
            _dump(
                [
                    "worktree",
                    plan["worktree_parent_identity"],
                    _normal_path(Path(plan["worktree_path"]))[-1],
                ]
            )
        ),
    )


def _fence(db: sqlite3.Connection, project: str, approval: str, plan: dict[str, Any]) -> None:
    destination = Path(plan["worktree_path"])
    target = Path(plan["target_root"])
    keys = set(_fence_keys(plan))
    for row in db.execute(
        "SELECT project_id, request_id FROM owner_idempotency WHERE operation=? ORDER BY project_id,request_id",
        (_FENCE,),
    ):
        saved = _entry(db, row["project_id"], _FENCE, row["request_id"])
        if saved is None:
            _reject()
        if row["request_id"] in keys or (
            "worktree_path" in saved
            and (
                _overlaps(destination, Path(saved["worktree_path"]))
                or _overlaps(target, Path(saved["worktree_path"]))
                or _overlaps(destination, Path(saved["target_root"]))
            )
        ):
            _error(
                "integration_reserved",
                "An integration already reserves the destination branch or path.",
            )
    for key, details in zip(
        _fence_keys(plan),
        ({}, {"worktree_path": str(destination), "target_root": str(target)}),
        strict=True,
    ):
        _save(db, project, _FENCE, key, {"approval_id": approval, **details})


class OwnerCandidateIntegration:
    def __init__(self, core: Core) -> None:
        self._core = core
        self._jobs = CandidateVerificationJobs(core)
        self._delivery = OwnerCandidateDelivery(core)

    def _git(self) -> IntegrationGit:
        git = IntegrationGit(GitWorkspaceStore(self._core.data_dir, create=False))
        git.check_managed_environment()
        return git

    @staticmethod
    def _comparison(git: IntegrationGit, exported: CandidateInput) -> Path:
        return git.store._path("comparisons", exported.binding.candidate_id)

    def _checked_plan(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, state: str
    ) -> tuple[dict[str, Any], CandidateInput]:
        git = self._git()
        original, exported = self._delivery._candidate_plan(db, p, now, state)
        target = integration_path(p["target_root"])
        physical(target)
        target = target.resolve(strict=True)
        worktree = integration_path(p["worktree_path"])
        target_plan = git.target(target, exported.binding.base_sha)
        destination = git.destination(target, worktree, p["destination_branch"])
        git.candidate(self._comparison(git, exported), exported)
        return (
            original
            | target_plan
            | destination
            | {"schema": "agentsync.candidate-integration-plan.v1"},
            exported,
        )

    def _plan(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, state: str
    ) -> tuple[dict[str, Any], CandidateInput]:
        try:
            return self._checked_plan(db, p, now, state)
        except OSError:
            _error("integration_boundary", "The integration directories could not be inspected.")

    def preview(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_IntegrationPlan, payload)
        with self._jobs._transaction(p) as (db, now):
            plan, _ = self._plan(db, p, now, "pending")
            return {"plan": plan, "plan_sha256": _hash(_dump(plan))}

    def approve(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Decision, payload)
        with self._jobs._transaction(p, write=True, operation=_APPROVED) as (db, now):
            plan, _ = self._plan(db, p, now, "pending")
            if _hash(_dump(plan)) != p["plan_sha256"]:
                _reject()
            final_now = self._delivery._now(now)
            self._delivery._approval(db, p, final_now, "pending")
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

    def _assert_target(self, git: IntegrationGit, plan: dict[str, Any]) -> tuple[Path, Path]:
        target, worktree = Path(plan["target_root"]), Path(plan["worktree_path"])
        current = git.target(target, plan["base_sha"])
        if any(value != plan[key] for key, value in current.items()):
            _reject()
        destination = git.destination(
            target, worktree, plan["destination_ref"].removeprefix("refs/heads/")
        )
        if any(value != plan[key] for key, value in destination.items()):
            _reject()
        return target, worktree

    def _revalidate_consumed(
        self, db: sqlite3.Connection, p: dict[str, Any], now: float, plan: dict[str, Any]
    ) -> float:
        requester = self._core._authenticate(db, p, now)
        self._core._authorize_session(db, "request_approval", requester)
        approval = self._core._approval(db, p, requester["agent_id"])
        current = self._core._task(db, p)
        proof = task_projection(db, current)["verification"]
        if (
            requester["agent_id"] != plan["requester_agent_id"]
            or requester["id"] != plan["requester_session_id"]
            or not approval["updated_at"] <= now < plan["expires_at"]
            or approval["status"] != "consumed"
            or approval["version"] != plan["pending_version"] + 2
            or approval["subject_id"] != plan["candidate_id"]
            or approval["subject_sha"] != plan["candidate_sha"]
            or current["version"] != plan["task_version"]
            or proof is None
            or _hash(_dump(proof)) != plan["verification_sha256"]
        ):
            _reject()
        binding = OwnerCandidateBindings(self._core)._capture_in_transaction(
            db,
            project_id=p["project_id"],
            admin_token=p["admin_token"],
            candidate_id=plan["candidate_id"],
            expected_candidate_sha=plan["candidate_sha"],
        )
        if binding.provenance_sha256 != plan["current_binding_sha256"]:
            _reject()
        return min(plan["expires_at"], requester["expires_at"])

    def integrate_once(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Decision, payload)
        project, approval_id = p["project_id"], p["approval_id"]
        with self._jobs._transaction(p, write=True, operation=_INTENT) as (db, now):
            approved = _entry(db, project, _APPROVED, approval_id)
            if approved is None or _hash(_dump(approved)) != p["plan_sha256"]:
                _reject()
            plan, exported = self._plan(db, p, now, "approved")
            if approved != plan:
                _reject()
            _fence(db, project, approval_id, plan)
            final_now = self._delivery._now(now)
            self._delivery._approval(db, p, final_now, "approved")
            consumed = self._core._change_approval(db, p, final_now, "consumed", {"approved"})
            _save(db, project, _INTENT, approval_id, plan)
            self._core._audit_event(
                db, project, "owner", project, _INTENT, p, "allowed", "ok", consumed
            )

        try:
            with self._jobs._transaction(p, write=True, operation=_EFFECT) as (db, now):
                expires = self._revalidate_consumed(db, p, now, plan)
                git = self._git()
                if OwnerCandidateExporter._check(git.store, exported.binding) != _load(
                    exported.binding.receipts[0], 16384
                ):
                    _reject()
                comparison = self._comparison(git, exported)
                blobs = git.candidate(comparison, exported)
                target, worktree = self._assert_target(git, plan)
                with tempfile.TemporaryDirectory(
                    prefix="integration-", dir=git.store.root / "intents"
                ) as stage:
                    bundle = Path(stage) / "candidate.bundle"
                    pin = git.stage_bundle(comparison, target, bundle, plan)
                    self._assert_target(git, plan)
                    self._check_deadline(now, expires)
                    git.import_objects(target, bundle, pin, plan)
                self._assert_target(git, plan)
                self._check_deadline(now, expires)
                git.create_branch(target, plan)
                self._assert_original(git, target, worktree, plan)
                if _exists(worktree) or git.destination_state(target, plan) != "exact":
                    _reject()
                self._check_deadline(now, expires)
                git.write_worktree(target, worktree, plan, blobs)
                identity = git.verify_worktree(target, worktree, plan)
                self._assert_original(git, target, worktree, plan)
                _save(db, project, _EFFECT, approval_id, {"worktree_identity": identity})
                self._core._audit_event(
                    db, project, "owner", project, _EFFECT, p, "success", "ok", consumed
                )
        except (AgentSyncError, OSError, UnicodeError, ValueError):
            # The committed intent remains authoritative even if the Git effect
            # or its final observation could not be saved.
            pass
        return self.status(
            project_id=project, admin_token=p["admin_token"], approval_id=approval_id
        )

    def _check_deadline(self, now: float, expires: float) -> None:
        if self._delivery._now(now) >= expires:
            _reject()

    @staticmethod
    def _assert_original(
        git: IntegrationGit, target: Path, worktree: Path, plan: dict[str, Any]
    ) -> None:
        current = git.target(target, plan["base_sha"])
        if (
            any(value != plan[key] for key, value in current.items())
            or physical(worktree.parent) != plan["worktree_parent_identity"]
        ):
            _reject()

    def status(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Lookup, payload)
        project, approval_id = p["project_id"], p["approval_id"]
        with self._jobs._transaction(p) as (db, now):
            approval = self._core._approval(db, p)
            if approval["action"] != "apply_merge_candidate":
                _error("not_found", "No candidate integration approval exists.", 404)
            approved = _entry(db, project, _APPROVED, approval_id)
            intent = _entry(db, project, _INTENT, approval_id)
            result = _entry(db, project, _EFFECT, approval_id)
            approval_status = self._core._public_approval(approval, now)["status"]
            if approved is not None and (
                approved["approval_id"] != approval_id
                or approved["candidate_id"] != approval["subject_id"]
                or approved["candidate_sha"] != approval["subject_sha"]
                or approved["requester_agent_id"] != approval["requester_agent_id"]
                or approval["version"] <= approved["pending_version"]
            ):
                _reject()
            if intent is None:
                if result is not None or (approved is not None and approval_status == "consumed"):
                    _reject()
                return {
                    "plan": approved,
                    "approval_status": approval_status,
                    "effect": "not_attempted",
                }
            if (
                approved != intent
                or approval_status != "consumed"
                or approval["version"] != intent["pending_version"] + 2
                or any(
                    (_entry(db, project, _FENCE, key) or {}).get("approval_id") != approval_id
                    for key in _fence_keys(intent)
                )
            ):
                _reject()
            effect = "unknown"
            try:
                git = self._git()
                target, worktree = Path(intent["target_root"]), Path(intent["worktree_path"])
                self._assert_original(git, target, worktree, intent)
                ref = git.destination_state(target, intent)
                exists = _exists(worktree)
                if ref != "absent" or exists:
                    effect = "partial"
                if result is not None and ref == "exact" and exists:
                    if git.verify_worktree(target, worktree, intent) == result["worktree_identity"]:
                        effect = "exact"
            except (AgentSyncError, OSError, UnicodeError, ValueError):
                pass
            return {"plan": intent, "approval_status": approval_status, "effect": effect}

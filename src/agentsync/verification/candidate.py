"""Existing managed candidate input only; no preparation, dispatch or execution."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentsync.errors import AgentSyncError
from agentsync.verification.binding import (
    CandidateBinding,
    OwnerCandidateBindings,
    _canonical,
    _receipt,
)
from agentsync.verification.snapshot import CandidateSnapshot, _repository, export_candidate
from agentsync.workspaces.git import GitWorkspaceStore, physical

if TYPE_CHECKING:
    from agentsync.core.service import Core


def _fail() -> None:
    raise AgentSyncError("candidate_input_invalid", "Existing candidate evidence is invalid.", 409)


def _text(path: Path, limit: int = 65536) -> str:
    physical(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        _fail()
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or physical(path) != [str(info.st_dev), str(info.st_ino)]:
        _fail()
    return data.decode("utf-8", errors="strict")


def _pointer(path: Path) -> str:
    value = _text(path, 4096).removesuffix("\n").removesuffix("\r")
    if not value or "\n" in value or "\r" in value or "\0" in value:
        _fail()
    return value


def _physical_path(path: Path) -> Path:
    physical(path)
    return path.resolve()


def _linked_directory(store: GitWorkspaceStore, path: Path, repo: Path) -> None:
    """Reject foreign Git indirection without invoking Git in that directory."""
    pointer = _pointer(path / ".git")
    if not pointer.startswith("gitdir: "):
        _fail()
    admin = _physical_path(path / pointer[8:])
    admin_parent = _physical_path(repo / "worktrees")
    if not admin.is_dir() or admin.parent != admin_parent:
        _fail()
    common = _physical_path(admin / _pointer(admin / "commondir"))
    back = _physical_path(admin / _pointer(admin / "gitdir"))
    if common != repo.resolve() or back != (path / ".git").resolve():
        _fail()
    if (admin / "config.worktree").exists():
        _fail()
    # _git rechecks this identity for every command too.
    if physical(store.root) != store.root_identity:
        _fail()


@dataclass(frozen=True)
class CandidateInput:
    source_kind: str
    binding: CandidateBinding
    snapshot: CandidateSnapshot
    provenance_sha256: str


class OwnerCandidateExporter:
    def __init__(self, core: Core):
        self.core = core

    @staticmethod
    def _check(store: GitWorkspaceStore, binding: CandidateBinding) -> dict[str, Any]:
        snapshot, left, right, candidate = tuple(json.loads(value) for value in binding.receipts)
        records = (
            (binding.snapshot_id, snapshot),
            (binding.left_worktree_id, left),
            (binding.right_worktree_id, right),
            (binding.candidate_id, candidate),
        )
        for identity, expected in records:
            actual = _receipt(_text(store._path("receipts", identity)))
            if _canonical(actual) != _canonical(expected):
                _fail()
        intents = (
            (
                binding.snapshot_id,
                {
                    "operation": "capture",
                    "source": snapshot["source_root"],
                    "base_sha": binding.base_sha,
                },
            ),
            (
                binding.left_worktree_id,
                {
                    "operation": "create",
                    "snapshot_id": binding.snapshot_id,
                    "task_id": binding.left_task_id,
                },
            ),
            (
                binding.right_worktree_id,
                {
                    "operation": "create",
                    "snapshot_id": binding.snapshot_id,
                    "task_id": binding.right_task_id,
                },
            ),
            (binding.candidate_id, candidate["input_binding"]),
        )
        for identity, expected in intents:
            if _canonical(_receipt(_text(store._path("intents", identity)))) != _canonical(
                expected
            ):
                _fail()
        # This rejects metadata links/alternates and config changes before any Git
        # command can consult a worktree's .git pointer or foreign configuration.
        # A bare directory must not acquire a .git redirect: Git would prefer it
        # over the validated bare metadata even when that metadata is unchanged.
        expected_repo = store._path("repositories", binding.snapshot_id)
        redirect = expected_repo / ".git"
        if redirect.exists() or redirect.is_symlink():
            _fail()
        config = expected_repo / "config"
        physical(config)
        if not stat.S_ISREG(config.stat().st_mode):
            _fail()
        repo = _repository(store, snapshot)
        for receipt, identity, head in (
            (left, binding.left_worktree_id, binding.left_sha),
            (right, binding.right_worktree_id, binding.right_sha),
        ):
            path = store._path("worktrees", identity)
            if str(path) != receipt["path"] or physical(path) != receipt["root_identity"]:
                _fail()
            _linked_directory(store, path, repo)
            actual = store.inspect_worktree(receipt)
            if actual["head_sha"] != head or actual["dirty"]:
                _fail()
        path = store._path("comparisons", binding.candidate_id)
        if (
            str(path) != candidate["candidate_path"]
            or physical(path) != candidate["candidate_identity"]
        ):
            _fail()
        _linked_directory(store, path, repo)
        _, common = store._git(path, "rev-parse", "--git-common-dir")
        if _physical_path(path / common.decode("utf-8").strip()) != repo.resolve():
            _fail()
        if store._head(path) != binding.candidate_sha or store._status(path):
            _fail()
        _, raw = store._git(repo, "show", "-s", "--format=%P", binding.candidate_sha)
        parents = raw.decode("ascii").strip().split()
        if parents == [binding.left_sha]:
            code, _ = store._git(
                repo,
                "merge-base",
                "--is-ancestor",
                binding.right_sha,
                binding.left_sha,
                accepted=(0, 1),
            )
            if code:
                _fail()
        elif parents != [binding.left_sha, binding.right_sha]:
            _fail()
        return snapshot

    def export(
        self, *, project_id: str, admin_token: str, candidate_id: str, expected_candidate_sha: str
    ) -> CandidateInput:
        args = {
            "project_id": project_id,
            "admin_token": admin_token,
            "candidate_id": candidate_id,
            "expected_candidate_sha": expected_candidate_sha,
        }
        bindings = OwnerCandidateBindings(self.core)
        binding = bindings.capture(**args)
        try:
            store = GitWorkspaceStore(self.core.data_dir, create=False)
            receipt = self._check(store, binding)
            snapshot = export_candidate(store, receipt, binding.candidate_sha)
            self._check(store, binding)
            if bindings.capture(**args) != binding:
                raise AgentSyncError(
                    "stale_candidate_input", "Candidate metadata changed during export.", 409
                )
            kind = "managed_merge_candidate_input"
            provenance = {
                "schema": "agentsync.candidate-input.v1",
                "source_kind": kind,
                "binding_sha256": binding.provenance_sha256,
                "commit_sha": snapshot.commit_sha,
                "tree_sha": snapshot.tree_sha,
                "input_sha256": snapshot.input_sha256,
                "source_sha256": hashlib.sha256(snapshot.source).hexdigest(),
            }
            digest = hashlib.sha256(_canonical(provenance).encode("utf-8")).hexdigest()
            return CandidateInput(kind, binding, snapshot, digest)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, RecursionError):
            raise AgentSyncError(
                "candidate_input_invalid", "Existing candidate evidence is invalid.", 409
            ) from None

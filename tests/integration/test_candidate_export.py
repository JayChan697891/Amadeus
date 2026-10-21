"""Real disposable Git input export; candidate source is never executed."""

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_m4b_workspaces import (
    call,
    capture,
    commit_edit,
    comparison,
    git,
    source_fingerprint,
    worktree,
)
from test_m4b_workspaces import world as world

from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import candidate as module
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.workspaces.git import GitWorkspaceStore


def save_input(result, name, expected_source, parent_count):
    directory = os.environ.get("AGENTSYNC_CANDIDATE_INPUT_EVIDENCE_DIR")
    if not directory:
        return
    binding = dataclasses.asdict(result.binding)
    receipts = binding.pop("receipts")
    binding["receipt_sha256"] = [
        hashlib.sha256(value.encode("utf-8")).hexdigest() for value in receipts
    ]
    source_hash = hashlib.sha256(result.snapshot.source).hexdigest()
    expected_hash = hashlib.sha256(expected_source).hexdigest()
    assert source_hash == expected_hash
    provenance = {
        "schema": "agentsync.candidate-input.v1",
        "source_kind": result.source_kind,
        "binding_sha256": result.binding.provenance_sha256,
        "commit_sha": result.snapshot.commit_sha,
        "tree_sha": result.snapshot.tree_sha,
        "input_sha256": result.snapshot.input_sha256,
        "source_sha256": source_hash,
    }
    assert (
        hashlib.sha256(
            json.dumps(
                provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        == result.provenance_sha256
    )
    environment = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
    target = Path(directory) / environment
    assert target.is_absolute()
    target.mkdir(parents=True, exist_ok=True)
    data = {
        "environment_id": environment,
        "actual_git_object_export": True,
        "execution_verified": False,
        "filesystem_atomicity_verified": False,
        "source_kind": result.source_kind,
        "binding": binding,
        "input_provenance": provenance,
        "input_provenance_sha256": result.provenance_sha256,
        "manifest": result.snapshot.manifest,
        "expected_literal_source_sha256": expected_hash,
        "expected_fixture_manifest_paths": ["left.txt", "right.txt", "same.txt", "solution.py"],
        "parent_count": parent_count,
    }
    assert [entry[0] for entry in result.snapshot.manifest] == data[
        "expected_fixture_manifest_paths"
    ]
    (target / (name + ".json")).write_text(
        json.dumps(data, sort_keys=True, indent=2), encoding="utf-8"
    )


@pytest.fixture
def prepared(world):
    core, owner, (a, b), root = world
    (root / "solution.py").write_text("def solve(x): return 'base'\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate input baseline")
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    (Path(left["path"]) / "solution.py").write_bytes(b"def solve(x): return 'candidate'\n")
    git(left["path"], "add", "solution.py")
    git(
        left["path"],
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "candidate literal bytes",
    )
    lh = git(left["path"], "rev-parse", "HEAD")
    rh = commit_edit(right, "right.txt", "right changed\n")
    result = call(
        core,
        a,
        "prepare_merge_candidate",
        **comparison(left, right, lh, rh),
        request_id="input-candidate",
    )
    args = {
        **owner,
        "candidate_id": result["candidate_id"],
        "expected_candidate_sha": result["candidate_sha"],
    }
    with connect(core.db_path) as db:
        receipt = json.loads(
            db.execute(
                "SELECT receipt FROM merge_candidates WHERE id=?", (result["candidate_id"],)
            ).fetchone()[0]
        )
    # Every negative fixture starts from an actual successful object export.
    assert (
        OwnerCandidateExporter(core).export(**args).snapshot.source
        == b"def solve(x): return 'candidate'\n"
    )
    return core, args, left, right, receipt


def export(prepared, **extra):
    return OwnerCandidateExporter(prepared[0]).export(**(prepared[1] | extra))


def test_real_merged_candidate_bytes_and_immutable_provenance(prepared):
    core, _, _, _, _ = prepared
    before = source_fingerprint(core.data_dir / "managed-git")
    result = export(prepared)
    assert result.source_kind == "managed_merge_candidate_input"
    assert result.snapshot.source == b"def solve(x): return 'candidate'\n"
    assert result.snapshot.commit_sha == result.binding.candidate_sha != result.binding.base_sha
    assert {row[0] for row in result.snapshot.manifest} >= {"solution.py", "left.txt", "right.txt"}
    assert result == export(prepared)
    provenance = {
        "schema": "agentsync.candidate-input.v1",
        "source_kind": result.source_kind,
        "binding_sha256": result.binding.provenance_sha256,
        "commit_sha": result.snapshot.commit_sha,
        "tree_sha": result.snapshot.tree_sha,
        "input_sha256": result.snapshot.input_sha256,
        "source_sha256": hashlib.sha256(result.snapshot.source).hexdigest(),
    }
    assert (
        result.provenance_sha256
        == hashlib.sha256(
            json.dumps(
                provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.snapshot = None
    assert source_fingerprint(core.data_dir / "managed-git") == before
    repo = core.data_dir / "managed-git" / "repositories" / result.binding.snapshot_id
    assert git(repo, "show", "-s", "--format=%P", result.snapshot.commit_sha).split() == [
        result.binding.left_sha,
        result.binding.right_sha,
    ]
    save_input(result, "merged-input", b"def solve(x): return 'candidate'\n", 2)


def test_single_parent_when_right_is_ancestor(world):
    core, owner, (a, b), root = world
    (root / "solution.py").write_bytes(b"def solve(x): return x\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "baseline solution")
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lh = commit_edit(left, "left.txt", "left-only\n")
    candidate = call(
        core,
        a,
        "prepare_merge_candidate",
        **comparison(left, right, lh, snapshot["base_sha"]),
        request_id="ancestor-input",
    )
    result = OwnerCandidateExporter(core).export(
        **owner,
        candidate_id=candidate["candidate_id"],
        expected_candidate_sha=candidate["candidate_sha"],
    )
    assert result.snapshot.source == b"def solve(x): return x\n"
    repo = core.data_dir / "managed-git" / "repositories" / result.binding.snapshot_id
    assert git(repo, "show", "-s", "--format=%P", result.snapshot.commit_sha).split() == [
        result.binding.left_sha
    ]
    save_input(result, "single-parent-input", b"def solve(x): return x\n", 1)


@pytest.mark.parametrize("side", ["left", "right", "candidate"])
@pytest.mark.parametrize("change", ["dirty", "head"])
def test_changed_worktree_is_rejected(prepared, side, change):
    _, _, left, right, candidate = prepared
    path = Path(
        {"left": left["path"], "right": right["path"], "candidate": candidate["candidate_path"]}[
            side
        ]
    )
    (path / "fixture-change.txt").write_text("isolated mutation\n")
    if change == "head":
        git(path, "add", ".")
        git(
            path,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "unexpected fixture HEAD",
        )
    with pytest.raises(AgentSyncError):
        export(prepared)


@pytest.mark.parametrize(
    "target",
    [
        "capture_receipt",
        "create_receipt",
        "candidate_receipt",
        "capture_intent",
        "create_intent",
        "candidate_intent",
    ],
)
def test_missing_existing_evidence_is_not_reconstructed(prepared, target):
    core, _, left, _, candidate = prepared
    group = "receipts" if target.endswith("receipt") else "intents"
    identity = (
        candidate["candidate_id"]
        if target.startswith("candidate")
        else left["worktree_id"]
        if target.startswith("create")
        else candidate["input_binding"]["snapshot_id"]
    )
    path = core.data_dir / "managed-git" / group / identity
    path.unlink()
    before = source_fingerprint(core.data_dir / "managed-git")
    with pytest.raises(AgentSyncError):
        export(prepared)
    assert not path.exists()
    assert source_fingerprint(core.data_dir / "managed-git") == before


@pytest.mark.parametrize(
    "raw",
    ['{"duplicate":1,"duplicate":2}', '{"x":NaN}', "[]", "not-json", '{"x":"' + "x" * 66000 + '"}'],
    ids=["duplicate", "nonfinite", "array", "malformed", "oversized"],
)
def test_disk_receipt_is_strict_and_bounded(prepared, raw):
    core, _, _, _, candidate = prepared
    path = core.data_dir / "managed-git" / "receipts" / candidate["candidate_id"]
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(AgentSyncError):
        export(prepared)


@pytest.mark.parametrize("mutation", ["task", "owner", "candidate"])
def test_final_capture_rejects_authority_or_task_race(prepared, monkeypatch, mutation):
    core, _, left, _, _ = prepared
    original = module.export_candidate

    def raced(*args, **kwargs):
        result = original(*args, **kwargs)
        with connect(core.db_path) as db:
            if mutation == "task":
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (left["task_id"],))
            elif mutation == "owner":
                db.execute("UPDATE projects SET admin_hash=?", ("0" * 64,))
            else:
                row = db.execute("SELECT id,receipt FROM merge_candidates LIMIT 1").fetchone()
                receipt = json.loads(row["receipt"])
                receipt["fixture_change"] = True
                db.execute(
                    "UPDATE merge_candidates SET receipt=? WHERE id=?",
                    (json.dumps(receipt), row["id"]),
                )
        return result

    monkeypatch.setattr(module, "export_candidate", raced)
    with pytest.raises(AgentSyncError) as exc:
        export(prepared)
    assert exc.value.code == ("unauthorized" if mutation == "owner" else "stale_candidate_input")


def test_storage_open_existing_never_creates_missing_root(tmp_path):
    data = tmp_path / "missing-service"
    with pytest.raises(AgentSyncError):
        GitWorkspaceStore(data, create=False)
    assert not data.exists()


@pytest.mark.parametrize("change", ["config", "alternates", "backpointer", "commondir"])
def test_repository_and_link_metadata_tampering(prepared, change):
    core, _, left, _, candidate = prepared
    repo = (
        Path(left["path"]).parent.parent
        / "repositories"
        / candidate["input_binding"]["snapshot_id"]
    )
    if change == "config":
        with (repo / "config").open("a", encoding="utf-8") as stream:
            stream.write("\n[alias]\nfixture = changed\n")
    elif change == "alternates":
        (repo / "objects" / "info" / "alternates").write_text("missing-external-objects\n")
    else:
        pointer = (Path(left["path"]) / ".git").read_text().strip()[8:]
        admin = (Path(left["path"]) / pointer).resolve()
        (admin / ("gitdir" if change == "backpointer" else "commondir")).write_text(
            str(core.data_dir) + "\n"
        )
    with pytest.raises(AgentSyncError):
        export(prepared)


def test_post_export_disk_change_rejected(prepared, monkeypatch):
    original = module.export_candidate

    def raced(*args, **kwargs):
        result = original(*args, **kwargs)
        Path(prepared[4]["candidate_path"], "race.txt").write_text("after object reads\n")
        return result

    monkeypatch.setattr(module, "export_candidate", raced)
    with pytest.raises(AgentSyncError):
        export(prepared)


def test_wrong_owner_rejected_before_storage_open(prepared, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unauthorized request must not open managed storage")

    monkeypatch.setattr(module, "GitWorkspaceStore", forbidden)
    with pytest.raises(AgentSyncError) as exc:
        export(prepared, admin_token="invalid-secret-sentinel")
    assert exc.value.code == "unauthorized"
    assert "invalid-secret-sentinel" not in str(exc.value)


def test_bare_git_redirect_is_rejected_before_git(prepared, monkeypatch, tmp_path):
    core, _, _, _, candidate = prepared
    repo = (
        core.data_dir / "managed-git" / "repositories" / candidate["input_binding"]["snapshot_id"]
    )
    foreign = tmp_path / "foreign-bare"
    foreign.mkdir()
    git(foreign, "init", "--bare")
    (repo / ".git").write_bytes(("gitdir: " + str(foreign) + "\n").encode())
    original = subprocess.Popen

    def guarded(command, *args, **kwargs):
        if "-C" in command and Path(command[command.index("-C") + 1]).resolve() == repo.resolve():
            pytest.fail("Bare .git redirect must be rejected before any repository Git process")
        return original(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded)
    with pytest.raises(AgentSyncError):
        export(prepared)


@pytest.mark.parametrize("group", ["receipts", "intents", "comparisons", "home", "hooks"])
def test_storage_open_existing_never_creates_missing_group(tmp_path, group):
    store = GitWorkspaceStore(tmp_path)
    path = store.root / group
    path.rmdir()
    with pytest.raises(AgentSyncError):
        GitWorkspaceStore(tmp_path, create=False)
    assert not path.exists()


def test_export_seam_exists():
    assert callable(OwnerCandidateExporter.export)

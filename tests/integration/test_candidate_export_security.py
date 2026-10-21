"""Independent adversarial export checks using disposable actual Git repositories."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from test_m4b_workspaces import call, capture, commit_edit, comparison, git, worktree
from test_m4b_workspaces import world as world

from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.candidate import OwnerCandidateExporter


@pytest.fixture
def input_case(world):
    core, owner, (a, b), root = world
    (root / "solution.py").write_bytes(b"print('base')\n")
    git(root, "add", "solution.py")
    git(root, "commit", "-m", "isolated source baseline")
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    path = Path(left["path"])
    (path / "solution.py").write_bytes(b"print('candidate')\n")
    git(path, "add", "solution.py")
    git(
        path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "isolated candidate source",
    )
    lh = git(path, "rev-parse", "HEAD")
    rh = commit_edit(right, "right.txt", "right candidate change\n")
    candidate = call(
        core,
        a,
        "prepare_merge_candidate",
        **comparison(left, right, lh, rh),
        request_id="export-security",
    )
    with connect(core.db_path) as db:
        receipt = json.loads(
            db.execute(
                "SELECT receipt FROM merge_candidates WHERE id=?", (candidate["candidate_id"],)
            ).fetchone()[0]
        )
    store = core._workspace_store()
    args = {
        **owner,
        "candidate_id": candidate["candidate_id"],
        "expected_candidate_sha": candidate["candidate_sha"],
    }
    valid = OwnerCandidateExporter(core).export(**args)
    assert valid.source_kind == "managed_merge_candidate_input"
    assert valid.snapshot.source == b"print('candidate')\n"
    assert valid.snapshot.commit_sha == candidate["candidate_sha"]
    return core, store, args, receipt, snapshot


def test_foreign_git_pointer_rejected_before_candidate_git_invocation(
    input_case, tmp_path, monkeypatch
):
    core, store, args, receipt, _ = input_case
    candidate = Path(receipt["candidate_path"])
    bare = tmp_path / "foreign.git"
    checkout = tmp_path / "foreign-checkout"
    # Copy the same commit into another repository, so matching HEAD alone would
    # not establish that this candidate belongs to the trusted managed store.
    store._git(
        store.root,
        "clone",
        "--bare",
        "--no-local",
        str(
            core.data_dir / "managed-git" / "repositories" / receipt["input_binding"]["snapshot_id"]
        ),
        str(bare),
    )
    store._git(
        bare,
        "fetch",
        "--no-tags",
        str(
            core.data_dir / "managed-git" / "repositories" / receipt["input_binding"]["snapshot_id"]
        ),
        receipt["candidate_sha"],
    )
    store._git(bare, "worktree", "add", "--detach", str(checkout), receipt["candidate_sha"])
    # Updating an existing hidden Git file through r+b also works on Windows;
    # recreating/truncating it with wb can fail solely because of its attributes.
    with (candidate / ".git").open("r+b") as stream:
        stream.write((checkout / ".git").read_bytes())
        stream.truncate()
    original = subprocess.Popen

    def guard(command, *positional, **kwargs):
        if "-C" in command and Path(command[command.index("-C") + 1]) == candidate:
            pytest.fail("Foreign candidate .git was consulted by Git before boundary rejection")
        return original(command, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guard)
    with pytest.raises(AgentSyncError):
        OwnerCandidateExporter(core).export(**args)


def test_missing_disk_receipt_is_not_rebuilt(input_case):
    core, store, args, _, _ = input_case
    receipt = store.root / "receipts" / args["candidate_id"]
    receipt.unlink()
    before = {p.relative_to(store.root).as_posix() for p in store.root.rglob("*")}
    with pytest.raises(AgentSyncError):
        OwnerCandidateExporter(core).export(**args)
    assert not receipt.exists()
    assert {p.relative_to(store.root).as_posix() for p in store.root.rglob("*")} == before


def test_candidate_with_same_tree_but_wrong_parents_is_rejected(input_case):
    core, store, args, receipt, snapshot = input_case
    candidate = Path(receipt["candidate_path"])
    _, tree = store._git(candidate, "rev-parse", "HEAD^{tree}")
    _, commit = store._git(
        candidate,
        "commit-tree",
        tree.decode().strip(),
        "-p",
        snapshot["base_sha"],
        "-m",
        "isolated incorrect parent fixture",
    )
    sha = commit.decode().strip()
    store._git(candidate, "reset", "--hard", sha)
    receipt["candidate_sha"] = sha
    with connect(core.db_path) as db:
        db.execute(
            "UPDATE merge_candidates SET receipt=? WHERE id=?",
            (json.dumps(receipt), args["candidate_id"]),
        )
    (store.root / "receipts" / args["candidate_id"]).write_text(json.dumps(receipt))
    with pytest.raises(AgentSyncError):
        OwnerCandidateExporter(core).export(**(args | {"expected_candidate_sha": sha}))


def test_bare_repository_git_redirect_is_rejected_before_repository_git(
    input_case, tmp_path, monkeypatch
):
    core, store, args, _, snapshot = input_case
    repo = store.root / "repositories" / snapshot["snapshot_id"]
    foreign = tmp_path / "other-bare.git"
    store._git(store.root, "init", "--bare", str(foreign))
    (repo / ".git").write_text("gitdir: " + str(foreign) + "\n", encoding="utf-8")
    original = subprocess.Popen

    def guard(command, *positional, **kwargs):
        if "-C" in command and Path(command[command.index("-C") + 1]) == repo:
            pytest.fail("Managed bare repository .git redirect reached Git before rejection")
        return original(command, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guard)
    with pytest.raises(AgentSyncError):
        OwnerCandidateExporter(core).export(**args)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO metadata fixture requires Linux")
def test_nonregular_bare_config_is_rejected_without_reading_it(input_case, monkeypatch):
    core, store, args, _, snapshot = input_case
    config = store.root / "repositories" / snapshot["snapshot_id"] / "config"
    config.unlink()
    os.mkfifo(config)
    original = Path.read_bytes

    def guard(path):
        if path == config:
            pytest.fail("Nonregular config must be rejected before a potentially blocking read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guard)
    with pytest.raises(AgentSyncError):
        OwnerCandidateExporter(core).export(**args)

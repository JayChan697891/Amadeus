"""Real disposable Git workflows; no model/client compatibility is implied."""

import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient

GIT = shutil.which("git")


def git(root, *args):
    assert GIT, "Git is required for the M4B acceptance tier"
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        [
            GIT,
            "-c",
            "core.hooksPath=" + os.devnull,
            # Fixture commits must finish all their writes before fingerprinting.
            # Detached automatic maintenance can otherwise remove a captured lock.
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "-C",
            str(root),
            *args,
        ],
        env=environment,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return result.stdout.decode("utf-8").strip()


def test_fixture_git_disables_automatic_maintenance_even_with_repository_overrides(tmp_path):
    git(tmp_path, "init", "--initial-branch=fixture-main")
    git(tmp_path, "config", "gc.auto", "1")
    git(tmp_path, "config", "maintenance.auto", "true")
    # Query real Git's effective configuration, including the helper's overrides.
    assert git(tmp_path, "config", "--get", "gc.auto") == "0"
    assert git(tmp_path, "config", "--get", "maintenance.auto") == "false"


def call(core, actor, operation, **payload):
    return core.execute(operation, {**actor, **payload})


def source_fingerprint(root):
    """Include original user files, index, refs, config, and committed objects."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "user-repository"
    root.mkdir()
    git(root, "init", "--initial-branch=fixture-main")
    git(root, "config", "user.name", "Isolated acceptance fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    for name in ("same.txt", "left.txt", "right.txt"):
        (root / name).write_text("original\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "isolated baseline")
    core = Core(tmp_path / "service-state")
    project = core.execute("create_project", {"name": "Git acceptance", "root_path": str(root)})
    actors = []
    for name in ("Developer A", "Developer B"):
        registered = core.execute("register_agent", {**project, "name": name})
        owner_grant(core, project, registered)
        actors.append(
            {
                "project_id": project["project_id"],
                "session_id": registered["session_id"],
                "session_token": registered["session_token"],
            }
        )
    return core, project, actors, root


def capture(world):
    core, _, (a, _), _ = world
    return call(core, a, "capture_repository", request_id=uuid4().hex)


def worktree(world, snapshot, actor):
    core, _, _, _ = world
    task = call(core, actor, "create_task", title="isolated edit", request_id=uuid4().hex)
    return call(
        core,
        actor,
        "create_worktree",
        snapshot_id=snapshot["snapshot_id"],
        task_id=task["id"],
        request_id=uuid4().hex,
    )


def commit_edit(tree, name, text):
    path = Path(tree["path"])
    (path / name).write_text(text, encoding="utf-8")
    git(path, "add", "--", name)
    git(
        path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "isolated change",
    )
    return git(path, "rev-parse", "HEAD")


def comparison(left, right, left_head, right_head):
    return {
        "left_id": left["worktree_id"],
        "right_id": right["worktree_id"],
        "expected_left_head": left_head,
        "expected_right_head": right_head,
    }


def test_committed_only_capture_and_independent_owned_worktrees_preserve_original(world):
    core, _, (a, b), root = world
    (root / "same.txt").write_text("private uncommitted user edit\n", encoding="utf-8")
    (root / "untracked.txt").write_text("private untracked user file\n", encoding="utf-8")
    git(root, "status", "--porcelain")
    original = source_fingerprint(root)
    snapshot = capture(world)
    assert snapshot["source_dirty"] is True
    assert snapshot["committed_only"] is True
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    assert left["path"] != right["path"]
    for tree in (left, right):
        owned = Path(tree["path"]).resolve()
        assert owned.is_relative_to((core.data_dir / "managed-git").resolve())
        assert (owned / "same.txt").read_text() == "original\n"
        assert not (owned / "untracked.txt").exists()
        common = Path(git(owned, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = owned / common
        assert common.resolve().is_relative_to((core.data_dir / "managed-git").resolve())
        assert not (common / "objects/info/alternates").exists()
        source_object = next((root / ".git/objects").glob("[0-9a-f][0-9a-f]/*"))
        managed_object = common / "objects" / source_object.relative_to(root / ".git/objects")
        if managed_object.exists():
            assert not os.path.samefile(source_object, managed_object)
    assert source_fingerprint(root) == original
    assert not (root / ".git/worktrees").exists()


def test_actual_same_line_conflict_uses_third_tree_and_preserves_both_actors(world):
    core, _, (a, b), root = world
    original = source_fingerprint(root)
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lsha = commit_edit(left, "same.txt", "agent A\n")
    rsha = commit_edit(right, "same.txt", "agent B\n")
    result = call(core, a, "compare_worktrees", **comparison(left, right, lsha, rsha))
    assert result["mergeable"] is False
    assert "same.txt" in result["conflict_paths"]
    assert "same.txt" in result["overlapping_paths"]
    assert result["merge_exit_code"] != 0
    assert git(Path(left["path"]), "rev-parse", "HEAD") == lsha
    assert git(Path(right["path"]), "rev-parse", "HEAD") == rsha
    assert not git(Path(left["path"]), "status", "--porcelain")
    assert not git(Path(right["path"]), "status", "--porcelain")
    with pytest.raises(AgentSyncError):
        call(
            core,
            a,
            "prepare_merge_candidate",
            **comparison(left, right, lsha, rsha),
            request_id="conflict",
        )
    assert source_fingerprint(root) == original


def test_nonconflicting_candidate_awaits_approval_and_replay_is_immutable(world):
    core, _, (a, b), root = world
    original = source_fingerprint(root)
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lsha = commit_edit(left, "left.txt", "left work\n")
    rsha = commit_edit(right, "right.txt", "right work\n")
    args = comparison(left, right, lsha, rsha)
    result = call(core, a, "compare_worktrees", **args)
    assert result["mergeable"] is True
    assert result["conflict_paths"] == []
    assert result["merge_exit_code"] == 0
    candidate = call(core, a, "prepare_merge_candidate", **args, request_id="prepare-once")
    assert candidate["status"] == "awaiting_human_approval"
    assert set(candidate["changed_paths"]) == {"left.txt", "right.txt"}
    assert len(candidate["candidate_sha"]) in (40, 64)
    assert "approved" not in candidate
    assert call(core, a, "prepare_merge_candidate", **args, request_id="prepare-once") == candidate
    assert source_fingerprint(root) == original


def test_owner_can_inspect_pending_delivery_without_exposing_it_to_agents(world):
    core, owner, (first, second), root = world
    original = source_fingerprint(root)
    snapshot = capture(world)
    left, right = worktree(world, snapshot, first), worktree(world, snapshot, second)
    lsha = commit_edit(left, "left.txt", "delivery fixture left\n")
    rsha = commit_edit(right, "right.txt", "delivery fixture right\n")
    candidate = call(
        core, first, "prepare_merge_candidate", **comparison(left, right, lsha, rsha),
        request_id="delivery-fixture",
    )
    approval = call(
        core, first, "request_approval", action="apply_merge_candidate",
        subject_id=candidate["candidate_id"], subject_sha=candidate["candidate_sha"],
        request_id="approval-fixture",
    )
    sdk = AgentSyncClient(core.data_dir)
    operation = "get_candidate_delivery_status"
    assert sdk.owner_call(operation, **owner, approval_id=approval["id"]) == {
        "ok": True,
        "data": {"plan": None, "approval_status": "pending", "effect": "not_attempted"},
    }
    wrong = sdk.owner_call(
        operation, project_id=owner["project_id"], admin_token="fixture-wrong-token",
        approval_id=approval["id"],
    )
    assert wrong["error"]["code"] == "unauthorized"
    assert sdk.call(operation, **first, approval_id=approval["id"])["error"]["code"] == "unknown_operation"
    rejected = sdk.owner_call(
        "approve_candidate_delivery",
        **owner,
        approval_id=approval["id"],
        expected_version=approval["version"],
        task_id=left["task_id"],
        expected_task_version=1,
        session_id=first["session_id"],
        session_token=first["session_token"],
        plan_sha256="0" * 64,
    )
    assert rejected["error"]["code"] == "delivery_plan_changed"
    assert sdk.owner_call(operation, **owner, approval_id=approval["id"])["data"]["approval_status"] == "pending"
    assert source_fingerprint(root) == original


def test_dirty_and_stale_worktree_inputs_fail_without_discarding_edits(world):
    core, _, (a, b), _ = world
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    args = comparison(left, right, left["head_sha"], right["head_sha"])
    dirty = Path(left["path"]) / "private.txt"
    dirty.write_text("do not discard", encoding="utf-8")
    inspected = call(core, a, "inspect_worktree", worktree_id=left["worktree_id"])
    assert inspected["dirty"] is True
    with pytest.raises(AgentSyncError) as error:
        call(core, a, "compare_worktrees", **args)
    assert error.value.code == "dirty_worktree"
    assert dirty.read_text() == "do not discard"
    git(Path(left["path"]), "add", "private.txt")
    git(
        Path(left["path"]),
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "preserve private fixture",
    )
    with pytest.raises(AgentSyncError) as error:
        call(core, a, "compare_worktrees", **args)
    assert error.value.code == "stale_snapshot"
    assert dirty.read_text() == "do not discard"


def test_concurrent_create_request_has_one_owned_worktree_and_restart_replays(world):
    core, _, (a, _), root = world
    original = source_fingerprint(root)
    snapshot = capture(world)
    task = call(core, a, "create_task", title="one logical tree", request_id="race-task")
    payload = {
        "snapshot_id": snapshot["snapshot_id"],
        "task_id": task["id"],
        "request_id": "one-logical-create",
    }

    def create(_):
        return call(Core(core.data_dir), a, "create_worktree", **payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, range(2)))
    assert results[0] == results[1]
    reopened = call(Core(core.data_dir), a, "create_worktree", **payload)
    assert reopened == results[0]
    assert Path(reopened["path"]).is_dir()
    assert source_fingerprint(root) == original


def test_cross_project_objects_and_invalid_auth_are_rejected(world, tmp_path, monkeypatch):
    core, _, (a, _), _ = world
    snapshot = capture(world)
    tree = worktree(world, snapshot, a)
    foreign_root = tmp_path / "foreign"
    foreign_root.mkdir()
    foreign_project = core.execute(
        "create_project", {"name": "foreign", "root_path": str(foreign_root)}
    )
    registered = core.execute("register_agent", {**foreign_project, "name": "outsider"})
    owner_grant(core, foreign_project, registered)
    foreign = {
        "project_id": foreign_project["project_id"],
        "session_id": registered["session_id"],
        "session_token": registered["session_token"],
    }
    task = call(core, foreign, "create_task", title="foreign", request_id="foreign")

    def forbidden_store(_self):
        pytest.fail("Workspace backend constructed before authorization/object scoping")

    monkeypatch.setattr(Core, "_workspace_store", forbidden_store)
    with pytest.raises(AgentSyncError) as error:
        call(
            core,
            foreign,
            "create_worktree",
            snapshot_id=snapshot["snapshot_id"],
            task_id=task["id"],
            request_id="foreign-create",
        )
    assert error.value.code == "not_found"
    with pytest.raises(AgentSyncError) as error:
        call(core, foreign, "inspect_worktree", worktree_id=tree["worktree_id"])
    assert error.value.code == "not_found"
    with pytest.raises(AgentSyncError):
        call(
            core,
            {**a, "session_token": "invalid-secret"},
            "capture_repository",
            request_id="bad-auth",
        )


@pytest.mark.parametrize(
    "sha", ["HEAD", "HEAD~1", "--help", "a" * 39, "z" * 40, "a" * 40 + ";echo injected"]
)
def test_revision_expressions_are_not_accepted_as_expected_commits(world, sha):
    core, _, (a, b), root = world
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    original = source_fingerprint(root)
    with pytest.raises(AgentSyncError) as error:
        call(core, a, "compare_worktrees", **comparison(left, right, sha, right["head_sha"]))
    assert error.value.code == "validation_error"
    assert source_fingerprint(root) == original


def test_source_hooks_fsmonitor_and_inherited_git_configuration_never_execute(
    world, monkeypatch, tmp_path
):
    core, _, (a, _), root = world
    marker = tmp_path / "configuration-executed"
    script = tmp_path / "malicious-hook.sh"
    script.write_text(
        "#!/bin/sh\nprintf executed > '" + marker.as_posix() + "'\n", encoding="utf-8"
    )
    script.chmod(0o755)
    hooks = root / ".git/hooks"
    for name in ("post-checkout", "post-merge", "pre-auto-gc"):
        (hooks / name).write_bytes(script.read_bytes())
        (hooks / name).chmod(0o755)
    git(root, "config", "core.fsmonitor", script.as_posix())
    git(root, "config", "core.hooksPath", hooks.as_posix())
    # Fixture Git commands themselves run with fsmonitor disabled from this point.
    marker.unlink(missing_ok=True)
    original = source_fingerprint(root)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", script.as_posix())
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", script.as_posix())
    snapshot = capture(world)
    tree = worktree(world, snapshot, a)
    assert (Path(tree["path"]) / "same.txt").read_text() == "original\n"
    assert not marker.exists()
    assert source_fingerprint(root) == original


def test_external_git_directory_indirection_is_rejected_without_modification(world, tmp_path):
    core, _, (a, _), root = world
    detached_git = tmp_path / "external-private-git"
    (root / ".git").rename(detached_git)
    (root / ".git").write_text("gitdir: " + detached_git.as_posix() + "\n", encoding="utf-8")
    original = source_fingerprint(root)
    with pytest.raises(AgentSyncError):
        call(core, a, "capture_repository", request_id="external-gitdir")
    assert source_fingerprint(root) == original
    assert detached_git.is_dir()


def test_create_intent_recovers_after_side_effect_before_receipt(world, monkeypatch):
    from agentsync.workspaces.git import GitWorkspaceStore

    core, _, (a, _), root = world
    snapshot = capture(world)
    task = call(
        core, a, "create_task", title="recover interrupted side effect", request_id="recover-task"
    )
    args = {
        "snapshot_id": snapshot["snapshot_id"],
        "task_id": task["id"],
        "request_id": "recover-create",
    }
    original = source_fingerprint(root)
    save = GitWorkspaceStore._save

    def crash_before_receipt(self, path, value):
        if path.parent.name == "receipts":
            raise RuntimeError("Injected crash after owned worktree creation")
        return save(self, path, value)

    monkeypatch.setattr(GitWorkspaceStore, "_save", crash_before_receipt)
    with pytest.raises(RuntimeError, match="Injected crash"):
        call(core, a, "create_worktree", **args)
    managed = core.data_dir / "managed-git"
    existing = list((managed / "worktrees").iterdir())
    assert len(existing) == 1 and existing[0].is_dir()
    monkeypatch.setattr(GitWorkspaceStore, "_save", save)
    recovered = call(Core(core.data_dir), a, "create_worktree", **args)
    assert Path(recovered["path"]) == existing[0]
    assert call(core, a, "create_worktree", **args) == recovered
    assert source_fingerprint(root) == original
    receipts = "\n".join(
        path.read_text(encoding="utf-8") for path in (managed / "receipts").iterdir()
    )
    assert a["session_token"] not in receipts
    assert "admin_token" not in receipts


def test_existing_unknown_managed_work_is_not_deleted_on_retry(world, monkeypatch):
    from agentsync.workspaces.git import GitWorkspaceStore

    core, _, (a, _), _ = world
    snapshot = capture(world)
    task = call(core, a, "create_task", title="unknown work preserved", request_id="unknown-task")
    args = {
        "snapshot_id": snapshot["snapshot_id"],
        "task_id": task["id"],
        "request_id": "unknown-create",
    }
    save = GitWorkspaceStore._save

    def crash_before_receipt(self, path, value):
        if path.parent.name == "receipts":
            raise RuntimeError("Injected interruption")
        return save(self, path, value)

    monkeypatch.setattr(GitWorkspaceStore, "_save", crash_before_receipt)
    with pytest.raises(RuntimeError):
        call(core, a, "create_worktree", **args)
    owned = next((core.data_dir / "managed-git/worktrees").iterdir())
    unknown = owned / "unknown-user-work.txt"
    unknown.write_text("must survive retry", encoding="utf-8")
    monkeypatch.setattr(GitWorkspaceStore, "_save", save)
    with pytest.raises(AgentSyncError):
        call(Core(core.data_dir), a, "create_worktree", **args)
    assert unknown.read_text() == "must survive retry"


@pytest.mark.parametrize("kind", ["alternate_objects", "submodule", "committed_symlink"])
def test_unsupported_external_object_and_committed_link_boundaries(world, tmp_path, kind):
    core, _, (a, _), root = world
    if kind == "alternate_objects":
        external = tmp_path / "external-objects"
        external.mkdir()
        (root / ".git/objects/info/alternates").write_text(
            external.as_posix() + "\n", encoding="utf-8"
        )
    elif kind == "submodule":
        head = git(root, "rev-parse", "HEAD")
        git(root, "update-index", "--add", "--cacheinfo", "160000," + head + ",nested-module")
        git(root, "commit", "-m", "unsupported committed gitlink")
    else:
        # Construct an actual Git symlink entry without Windows symlink privileges.
        target = tmp_path / "symlink-target-text"
        target.write_text("../outside-owned-root", encoding="utf-8")
        blob = git(root, "hash-object", "-w", str(target))
        git(root, "update-index", "--add", "--cacheinfo", "120000," + blob + ",committed-link")
        git(root, "commit", "-m", "unsupported committed symlink")
    original = source_fingerprint(root)
    with pytest.raises(AgentSyncError):
        call(core, a, "capture_repository", request_id="unsupported-" + kind)
    assert source_fingerprint(root) == original


def test_nul_parsed_unicode_and_space_filenames_survive_conflict_comparison(world):
    core, _, (a, b), root = world
    name = "中文 name.txt"
    (root / name).write_text("original\n", encoding="utf-8")
    git(root, "add", "--", name)
    git(root, "commit", "-m", "unicode fixture")
    original = source_fingerprint(root)
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lsha = commit_edit(left, name, "left\n")
    rsha = commit_edit(right, name, "right\n")
    result = call(core, a, "compare_worktrees", **comparison(left, right, lsha, rsha))
    assert result["conflict_paths"] == [name]
    assert result["overlapping_paths"] == [name]
    assert source_fingerprint(root) == original


def test_managed_repository_configuration_tampering_is_rejected(world):
    core, _, (a, _), root = world
    snapshot = capture(world)
    tree = worktree(world, snapshot, a)
    path = Path(tree["path"])
    git(path, "config", "user.name", "external tamper")
    original = source_fingerprint(root)
    with pytest.raises(AgentSyncError):
        call(core, a, "inspect_worktree", worktree_id=tree["worktree_id"])
    assert git(path, "config", "user.name") == "external tamper"
    assert source_fingerprint(root) == original


def test_merge_candidate_recovers_after_commit_before_receipt(world, monkeypatch):
    from agentsync.workspaces.git import GitWorkspaceStore

    core, _, (a, b), root = world
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lsha = commit_edit(left, "left.txt", "left recovered\n")
    rsha = commit_edit(right, "right.txt", "right recovered\n")
    args = {**comparison(left, right, lsha, rsha), "request_id": "recover-candidate"}
    original = source_fingerprint(root)
    save = GitWorkspaceStore._save

    def crash_candidate_receipt(self, path, value):
        if path.parent.name == "receipts":
            raise RuntimeError("Injected interruption after candidate commit")
        return save(self, path, value)

    monkeypatch.setattr(GitWorkspaceStore, "_save", crash_candidate_receipt)
    with pytest.raises(RuntimeError, match="Injected interruption"):
        call(core, a, "prepare_merge_candidate", **args)
    candidates = list((core.data_dir / "managed-git/comparisons").iterdir())
    # Directory identity is deterministic; locate the actual candidate commit.
    heads = {git(path, "rev-parse", "HEAD") for path in candidates if path.is_dir()}
    monkeypatch.setattr(GitWorkspaceStore, "_save", save)
    candidate = call(Core(core.data_dir), a, "prepare_merge_candidate", **args)
    assert candidate["candidate_sha"] in heads
    assert candidate["status"] == "awaiting_human_approval"
    assert call(core, a, "prepare_merge_candidate", **args) == candidate
    assert source_fingerprint(root) == original


@pytest.mark.parametrize("configuration", ["clean", "smudge", "process", "include", "includeIf"])
def test_active_source_filters_and_includes_cannot_execute_before_status(
    world, tmp_path, configuration
):
    core, _, (a, _), root = world
    marker = tmp_path / "source-filter-executed"
    script = tmp_path / "active-source-filter.sh"
    script.write_text(
        "#!/bin/sh\nprintf executed > '" + marker.as_posix() + "'\nexit 1\n", encoding="utf-8"
    )
    script.chmod(0o755)
    (root / ".gitattributes").write_text("*.txt filter=malicious\n", encoding="utf-8")
    git(root, "add", ".gitattributes")
    git(root, "commit", "-m", "active filter fixture attributes")
    # Configure only after fixture writes/commit so setup cannot trigger it.
    if configuration in {"clean", "smudge", "process"}:
        git(root, "config", "filter.malicious." + configuration, script.as_posix())
    else:
        included = tmp_path / "untrusted-included-config"
        included.write_text("[core]\n fsmonitor = " + script.as_posix() + "\n", encoding="utf-8")
        key = (
            "include.path"
            if configuration == "include"
            else "includeIf.gitdir:" + root.as_posix() + "/.path"
        )
        git(root, "config", key, included.as_posix())
    (root / "same.txt").write_text("dirty content requiring status filter\n", encoding="utf-8")
    original = source_fingerprint(root)
    with pytest.raises(AgentSyncError):
        call(core, a, "capture_repository", request_id="active-filter-" + configuration)
    assert not marker.exists(), "Source-configured executable ran before the safety rejection"
    assert source_fingerprint(root) == original


def test_persisted_create_receipt_cannot_rebind_snapshot_after_database_rollback(
    world, monkeypatch
):
    from agentsync.workspaces.git import GitWorkspaceStore

    core, _, (a, _), root = world
    first, second = capture(world), capture(world)
    assert first["snapshot_id"] != second["snapshot_id"]
    task = call(core, a, "create_task", title="receipt scope", request_id="receipt-task")
    args = {
        "snapshot_id": first["snapshot_id"],
        "task_id": task["id"],
        "request_id": "persist-then-crash",
    }
    original = source_fingerprint(root)
    save = GitWorkspaceStore._save
    persisted = []

    def save_receipt_then_crash(self, path, value):
        result = save(self, path, value)
        if path.parent.name == "receipts":
            persisted.append(
                (path, path.read_bytes(), json.loads(path.read_text(encoding="utf-8")))
            )
            raise RuntimeError("Injected database rollback after durable receipt")
        return result

    monkeypatch.setattr(GitWorkspaceStore, "_save", save_receipt_then_crash)
    with pytest.raises(RuntimeError, match="durable receipt"):
        call(core, a, "create_worktree", **args)
    assert len(persisted) == 1
    receipt_path, receipt_bytes, receipt = persisted[0]
    assert receipt["snapshot_id"] == first["snapshot_id"]
    monkeypatch.setattr(GitWorkspaceStore, "_save", save)
    with pytest.raises(AgentSyncError):
        call(
            Core(core.data_dir),
            a,
            "create_worktree",
            **{**args, "snapshot_id": second["snapshot_id"]},
        )
    assert receipt_path.read_bytes() == receipt_bytes
    recovered = call(Core(core.data_dir), a, "create_worktree", **args)
    assert recovered["snapshot_id"] == first["snapshot_id"]
    assert recovered["path"] == receipt["path"]
    assert source_fingerprint(root) == original


def test_persisted_candidate_cannot_rebind_pair_after_database_rollback(world, monkeypatch):
    from agentsync.workspaces.git import GitWorkspaceStore

    core, _, (a, b), root = world
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lsha = commit_edit(left, "left.txt", "first parent work\n")
    rsha = commit_edit(right, "right.txt", "second parent work\n")
    args = {**comparison(left, right, lsha, rsha), "request_id": "persist-candidate-then-crash"}
    original = source_fingerprint(root)
    save = GitWorkspaceStore._save
    persisted = []

    def save_receipt_then_crash(self, path, value):
        result = save(self, path, value)
        if path.parent.name == "receipts":
            persisted.append(
                (path, path.read_bytes(), json.loads(path.read_text(encoding="utf-8")))
            )
            raise RuntimeError("Injected database rollback after durable candidate")
        return result

    monkeypatch.setattr(GitWorkspaceStore, "_save", save_receipt_then_crash)
    with pytest.raises(RuntimeError, match="durable candidate"):
        call(core, a, "prepare_merge_candidate", **args)
    assert len(persisted) == 1
    receipt_path, receipt_bytes, receipt = persisted[0]
    monkeypatch.setattr(GitWorkspaceStore, "_save", save)
    # Both trees and expected commits are valid; only their ordered request binding changes.
    changed = {**comparison(right, left, rsha, lsha), "request_id": args["request_id"]}
    with pytest.raises(AgentSyncError):
        call(Core(core.data_dir), a, "prepare_merge_candidate", **changed)
    assert receipt_path.read_bytes() == receipt_bytes
    recovered = call(Core(core.data_dir), a, "prepare_merge_candidate", **args)
    assert recovered["candidate_sha"] == receipt["candidate_sha"]
    assert recovered["left_sha"] == lsha and recovered["right_sha"] == rsha
    assert source_fingerprint(root) == original

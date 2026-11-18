"""Actual disposable Git/Core staging, no model or candidate code execution."""

import json
import runpy
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import owner_grant
from test_m4b_workspaces import git, source_fingerprint
from test_task_proposals import world as world

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import proposal_staging as module
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.proposal_staging import OwnerProposalStaging


def setup(world, files=None, review=True):
    core, owner, _, auth, request, tree, _ = world
    files = files or [
        {"path": "solution.py", "content": "raise RuntimeError('INERT_STAGE_SENTINEL')\n"}
    ]
    request = request | {
        "allowed_paths": [item["path"] for item in files],
        "proposal_json": json.dumps({"files": files}),
    }
    published = core.execute("publish_task_proposal", request)
    version = request["expected_version"]
    if review:
        version = core.execute(
            "update_task",
            {
                **auth,
                "task_id": request["task_id"],
                "lease_token": request["lease_token"],
                "expected_version": version,
                "status": "review",
                "request_id": "submit",
            },
        )["version"]
    stager = core.execute("register_agent", {**owner, "name": "Owner staging worker"})
    owner_grant(core, owner, stager, ("worker",))
    args = {
        **owner,
        "session_id": stager["session_id"],
        "session_token": stager["session_token"],
        "task_id": request["task_id"],
        "expected_task_version": version,
        "context_id": published["context_id"],
        "expected_content_sha256": published["content_sha256"],
        "publication_session_id": auth["session_id"],
        "publication_request_id": request["request_id"],
    }
    return OwnerProposalStaging(core), args, files


def decision(service, args):
    return args | {"expected_plan_sha256": service.preview(**args)["plan_sha256"]}


def observe(service, args):
    return service.status(**{key: args[key] for key in ("project_id", "admin_token", "task_id")})


def test_real_candidate_reopens_and_old_trees_tasks_are_unchanged(world):
    core, owner, _, auth, request, tree, source = world
    service, args, files = setup(
        world,
        [
            {"path": "solution.py", "content": "raise RuntimeError('INERT_STAGE_SENTINEL')\n"},
            {"path": "nested/值.py", "content": "# exact UTF-8\n"},
            {"path": "baseline.txt", "content": "reviewed replacement\n"},
        ],
    )
    tasks = core.execute("get_project_state", auth)["tasks"]
    original = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    preview = service.preview(**args)
    assert "INERT_STAGE_SENTINEL" not in json.dumps(preview)
    result = service.stage_once(**args, expected_plan_sha256=preview["plan_sha256"])
    assert result["state"] == "staged" and result["verification"] == "unverified"
    assert result["execution_started"] is False
    assert core.execute("get_project_state", auth)["tasks"] == tasks
    assert [source_fingerprint(path) for path in (source, Path(tree["path"]))] == original
    exported = OwnerCandidateExporter(core).export(
        **owner, candidate_id=result["candidate_id"], expected_candidate_sha=result["candidate_sha"]
    )
    assert exported.snapshot.source == files[0]["content"].encode()
    assert exported.binding.left_task_id == exported.binding.right_task_id == request["task_id"]
    assert exported.binding.creator_session_ids[1] == args["session_id"] != auth["session_id"]
    assert exported.binding.left_worktree_id != exported.binding.right_worktree_id
    staged_path = core.data_dir / "managed-git/worktrees" / result["worktree_id"]
    for item in files:
        assert staged_path.joinpath(item["path"]).read_bytes() == item["content"].encode()
    assert git(staged_path, "show", "-s", "--format=%P", result["head_sha"]) == tree["head_sha"]
    queued = CandidateVerificationJobs(core).enqueue(
        **owner,
        candidate_id=result["candidate_id"],
        expected_candidate_sha=result["candidate_sha"],
        profile=DockerProfile("sha256:" + "b" * 64, (JsonCase(None, None),)),
        request_id="queue",
    )
    assert queued["status"] == "queued"  # Admission only; no Docker execution.
    assert (
        observe(OwnerProposalStaging(Core(core.data_dir)), args)["result"]["candidate_sha"]
        == result["candidate_sha"]
    )
    with pytest.raises(AgentSyncError, match="already has"):
        service.stage_once(**args, expected_plan_sha256=preview["plan_sha256"])
    audit = core.execute_owner("list_audit", {**owner, "limit": 100, "offset": 0})
    assert "INERT_STAGE_SENTINEL" not in json.dumps(audit)
    assert {event["operation"] for event in audit["events"]} >= {
        "proposal_staging_admit",
        "proposal_staging_finish",
    }


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "session",
        "version",
        "hash",
        "publication",
        "dirty",
        "head",
        "audit",
        "context",
        "forged",
        "role",
        "consent",
    ],
)
def test_rejects_before_staging(world, monkeypatch, fault):
    core, owner, _, auth, request, tree, _ = world
    service, args, _ = setup(world)
    approved = decision(service, args)
    called = []
    monkeypatch.setattr(module, "stage_worktree", lambda *_: called.append(True))
    if fault == "owner":
        approved["admin_token"] = "wrong"
    elif fault == "session":
        approved["session_token"] = "wrong"
    elif fault == "version":
        approved["expected_task_version"] += 1
    elif fault == "hash":
        approved["expected_content_sha256"] = "f" * 64
    elif fault == "publication":
        approved["publication_request_id"] = "absent"
    elif fault == "dirty":
        (Path(tree["path"]) / "dirty.txt").write_bytes(b"dirty")
    elif fault == "head":
        git(
            tree["path"],
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "head drift",
        )
    elif fault == "role":
        members = core.execute_owner("list_members", {**owner, "limit": 100, "offset": 0})[
            "members"
        ]
        with connect(core.db_path) as db:
            agent_id = db.execute(
                "SELECT agent_id FROM sessions WHERE id=?", (args["session_id"],)
            ).fetchone()[0]
        member = next(item for item in members if item["agent_id"] == agent_id)
        core.execute_owner(
            "set_agent_roles",
            {
                **owner,
                "agent_id": member["agent_id"],
                "roles": ["viewer"],
                "expected_version": member["version"],
                "request_id": "revoke-stager",
            },
        )
    elif fault == "consent":
        approved["expected_plan_sha256"] = "e" * 64
    elif fault == "forged":
        context = core.execute(
            "get_context", {**auth, "context_id": args["context_id"], "version": 1}
        )
        forged = core.execute(
            "publish_context",
            {
                **auth,
                "kind": "note",
                "title": "Unverified source proposal",
                "content": context["content"],
                "source": "amadeus:task-proposal",
                "request_id": "forged",
            },
        )
        approved["context_id"] = forged["id"]
    else:
        with connect(core.db_path) as db:
            if fault == "audit":
                db.execute("DELETE FROM audit_events WHERE operation='publish_task_proposal'")
            else:
                db.execute(
                    "UPDATE context_revisions SET content='{}' WHERE context_id=?",
                    (args["context_id"],),
                )
    with pytest.raises(AgentSyncError):
        service.stage_once(**approved)
    assert called == []
    assert observe(service, args)["state"] == "not_started"


def test_running_task_must_submit_through_existing_lease_gate(world):
    service, args, _ = setup(world, review=False)
    with pytest.raises(AgentSyncError, match="pins do not match"):
        service.preview(**args)
    assert observe(service, args)["state"] == "not_started"


@pytest.mark.parametrize(
    "path", ["BASELINE.txt", "baseline.txt/child.py", ".gitattributes", "nested/.gitmodules"]
)
def test_existing_tree_alias_and_git_control_paths_are_rejected(world, path):
    service, args, _ = setup(world, [{"path": path, "content": "inert"}])
    with pytest.raises(AgentSyncError):
        service.preview(**args)
    assert observe(service, args)["state"] == "not_started"


@pytest.mark.parametrize("phase", ["after_worktree", "final_audit"])
def test_crash_retains_once_fence_and_never_replays_effect(world, monkeypatch, phase):
    core = world[0]
    service, args, _ = setup(world)
    approved = decision(service, args)
    stage = module.stage_worktree
    audit = core._audit_event

    def fail_stage(*values):
        stage(*values)
        raise RuntimeError("Synthetic interruption after real worktree commit")

    def fail_audit(*values):
        if values[4] == "proposal_staging_finish":
            raise RuntimeError("Synthetic final audit failure")
        return audit(*values)

    monkeypatch.setattr(
        module, "stage_worktree", fail_stage if phase == "after_worktree" else stage
    )
    monkeypatch.setattr(core, "_audit_event", fail_audit)
    with pytest.raises(RuntimeError, match="Synthetic"):
        service.stage_once(**approved)
    state = observe(OwnerProposalStaging(Core(core.data_dir)), args)
    assert state["state"] == "incomplete"
    assert (core.data_dir / "managed-git/worktrees" / state["plan"]["staging_worktree_id"]).exists()
    with connect(core.db_path) as db:
        assert db.execute("SELECT count(*) FROM managed_worktrees").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM merge_candidates").fetchone()[0] == 0
    with pytest.raises(AgentSyncError, match="already has"):
        service.stage_once(**approved)


def test_concurrent_call_creates_one_candidate(world):
    service, args, _ = setup(world)
    approved = decision(service, args)

    def attempt(_):
        try:
            return service.stage_once(**approved)["state"]
        except AgentSyncError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == ["proposal_staging_exists", "staged"]


def test_producer_may_expire_but_owner_staging_identity_must_be_current(world):
    service, args, _ = setup(world)
    with connect(world[0].db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (args["publication_session_id"],))
    result = service.stage_once(**decision(service, args))
    assert result["state"] == "staged"
    with connect(world[0].db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (args["session_id"],))
    assert observe(service, args)["state"] == "staged"  # Owner-only historical read.


@pytest.fixture
def owner_resume(world, monkeypatch):
    core, owner, publisher, _, _, _, _ = world
    service, initial, files = setup(world)
    stage = service.preview(**initial)
    old = {
        "staging": stage,
        "binding": {
            "task_id": initial["task_id"],
            "review_task_version": initial["expected_task_version"],
            "context_id": initial["context_id"],
            "publication_sha256": initial["expected_content_sha256"],
        },
    }
    history = {key: initial[key] for key in ("publication_session_id", "publication_request_id")}
    original = {
        "producer": publisher,
        "receiver": publisher,
        "stager": {"agent_id": stage["plan"]["staging_agent_id"]},
        "reviewer": publisher,
    }
    now = time.time() + 3601
    monkeypatch.setattr(time, "time", lambda: now)
    assert publisher["expires_at"] <= now
    credentials = {}
    for operation, role in (("stager", "worker"), ("reviewer", "reviewer")):
        actor = core.execute("register_agent", {**owner, "name": f"Fresh {operation}"})
        owner_grant(core, owner, actor, (role,))
        credentials[operation] = {key: actor[key] for key in ("session_id", "session_token")}
    tool = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "tools/resume_live_solution_verification.py")
    )
    actors = tool["actor_binding"](core, owner, original, credentials)
    assert actors["stager"]["agent_id"] != actors["reviewer"]["agent_id"]
    return service, owner, old, history, credentials, actors, tool["stage_preview"], files


def test_owner_resume_stages_same_proposal_after_publisher_expiry(owner_resume):
    service, owner, old, history, credentials, actors, preview, files = owner_resume
    stage, payload = preview(service, owner, old, history, credentials["stager"], actors["stager"])
    assert stage["plan_sha256"] != old["staging"]["plan_sha256"]
    assert stage["plan"]["publication_session_id"] == history["publication_session_id"]
    with pytest.raises(AgentSyncError):
        service.stage_once(**payload, expected_plan_sha256=old["staging"]["plan_sha256"])
    result = service.stage_once(**payload, expected_plan_sha256=stage["plan_sha256"])
    assert result["task_id"] == old["binding"]["task_id"] and result["execution_started"] is False
    export = OwnerCandidateExporter(service._core).export(
        **owner, candidate_id=result["candidate_id"], expected_candidate_sha=result["candidate_sha"]
    )
    assert export.snapshot.source == files[0]["content"].encode()
    with pytest.raises(AgentSyncError) as duplicate:
        preview(service, owner, old, history, credentials["stager"], actors["stager"])
    assert duplicate.value.code == "proposal_staging_exists"


def test_owner_resume_refuses_changed_original_plan(owner_resume):
    service, owner, old, history, credentials, actors, preview, _ = owner_resume
    old["staging"]["plan"]["original_receipt_sha256"] = "a" * 64
    with pytest.raises(AssertionError):
        preview(service, owner, old, history, credentials["stager"], actors["stager"])
    assert (
        observe(service, owner | {"task_id": old["binding"]["task_id"]})["state"] == "not_started"
    )


def test_owner_resume_refuses_changed_capture_record_before_authenticating():
    tool_path = Path(__file__).resolve().parents[2] / "tools/resume_live_solution_verification.py"
    tool = runpy.run_path(str(tool_path))
    original = {
        "stage-plan.json": tool["ORIGINAL_STAGE"],
        "producer-capture.json": "a" * 64,
        "receiver-capture.json": "b" * 64,
    }
    plan = {
        "binding": {
            f"{actor}_capture_record_sha256": original[f"{actor}-capture.json"]
            for actor in ("producer", "receiver")
        }
    }
    for modified in ("producer-capture.json", "receiver-capture.json"):
        actual = original | {modified: "c" * 64}
        live = SimpleNamespace(
            sha=lambda path, hashes=actual: hashes[path.name],
            present=lambda _: False,
            read=lambda name: {"stage-plan.json": plan}[name],
        )
        with pytest.raises(AssertionError):
            tool["prepare_result"](live, None, None, None, {}, None, {})


def test_historical_receipt_does_not_authorize_changed_task(world):
    core, _, _, auth, request, _, _ = world
    service, args, _ = setup(world)
    service.stage_once(**decision(service, args))
    with connect(core.db_path) as db:
        db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (request["task_id"],))
    state = observe(service, args)
    assert state["historical"] is True and state["verification"] == "unverified"
    with pytest.raises(AgentSyncError):
        service.preview(**args)


@pytest.mark.parametrize("where", ["repository", "worktree"])
def test_foreign_git_indirection_rejected_before_consulting_it(world, tmp_path, monkeypatch, where):
    service, args, _ = setup(world)
    approved = decision(service, args)
    core, _, _, _, _, original, _ = world
    repo = core.data_dir / "managed-git/repositories" / original["snapshot_id"]
    foreign = tmp_path / "foreign.git"
    shutil.copytree(repo, foreign)
    before = source_fingerprint(foreign)
    target = repo if where == "repository" else Path(original["path"])
    pointer = target / ".git"
    with pointer.open("r+b" if pointer.exists() else "xb") as stream:
        stream.write(("gitdir: " + foreign.as_posix() + "\n").encode())
        stream.truncate()
    spawn = subprocess.Popen

    def guarded(command, *positional, **kwargs):
        if "-C" in command and Path(command[command.index("-C") + 1]) == target:
            pytest.fail("Git consulted the redirected directory before rejection")
        return spawn(command, *positional, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded)
    with pytest.raises(AgentSyncError):
        service.stage_once(**approved)
    assert source_fingerprint(foreign) == before
    assert observe(service, args)["state"] == "not_started"


def test_foreign_project_cannot_observe_or_stage_publication(world, tmp_path):
    service, args, _ = setup(world)
    root = tmp_path / "other-project"
    root.mkdir()
    foreign = world[0].execute("create_project", {"name": "Other", "root_path": str(root)})
    with pytest.raises(AgentSyncError):
        service.preview(**(args | foreign))
    assert service.status(**foreign, task_id=args["task_id"])["state"] == "not_started"


@pytest.mark.parametrize("change", ["hooks", "config", "receipt", "intent"])
def test_changed_managed_metadata_is_not_repaired(world, change):
    service, args, _ = setup(world)
    approved = decision(service, args)
    core, _, _, _, _, tree, _ = world
    store = core.data_dir / "managed-git"
    if change == "hooks":
        (store / "hooks/pre-commit").write_bytes(b"not executable fixture")
    elif change == "config":
        with (store / "repositories" / tree["snapshot_id"] / "config").open("ab") as stream:
            stream.write(b"\n[amadeus]\n changed = true\n")
    else:
        (
            store / ("receipts" if change == "receipt" else "intents") / tree["worktree_id"]
        ).write_text("{}", encoding="utf-8")
    before = source_fingerprint(store)
    with pytest.raises(AgentSyncError):
        service.stage_once(**approved)
    assert source_fingerprint(store) == before
    assert observe(service, args)["state"] == "not_started"


@pytest.mark.parametrize("location", ["snapshot", "head"])
def test_tracked_attributes_are_rejected_before_staging(world, location):
    core, owner, member, auth, request, tree, source = world
    target = source if location == "snapshot" else Path(tree["path"])
    (target / ".gitattributes").write_bytes(b"*.py text eol=crlf\n")
    git(target, "add", ".gitattributes")
    git(
        target,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "Unsupported attributes fixture",
    )
    if location == "snapshot":
        snapshot = core.execute("capture_repository", {**auth, "request_id": "attributes-snapshot"})
        tree = core.execute(
            "create_worktree",
            {
                **auth,
                "task_id": request["task_id"],
                "snapshot_id": snapshot["snapshot_id"],
                "request_id": "attributes-tree",
            },
        )
    request = request | {
        "worktree_id": tree["worktree_id"],
        "expected_head": git(tree["path"], "rev-parse", "HEAD"),
    }
    service, args, _ = setup((core, owner, member, auth, request, tree, source))
    with pytest.raises(AgentSyncError, match="attribute/module"):
        service.preview(**args)
    assert observe(service, args)["state"] == "not_started"

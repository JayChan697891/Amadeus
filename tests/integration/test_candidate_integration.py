"""Real disposable Git integration with explicitly synthetic verifier evidence."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from test_candidate_execution import attempt, protocol_candidate, synthetic_backend
from test_candidate_jobs import owner
from test_m4b_workspaces import git, source_fingerprint
from test_m4b_workspaces import world as world
from test_verified_task_completion import approve_delivery, completion_args, reviewer, submit_pair

import agentsync
from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient
from agentsync.storage.database import connect
from agentsync.verification import candidate_executor, candidate_jobs
from agentsync.verification.task_completion import OwnerVerifiedTaskCompletion
from agentsync.workspaces.git import GitWorkspaceStore
from agentsync.workspaces.integration import IntegrationGit

PREVIEW = "preview_candidate_integration"
APPROVE = "approve_candidate_integration"
INTEGRATE = "integrate_candidate"
STATUS = "get_candidate_integration_status"
CODE = b"def solve(x): return 'candidate'\n"


def original_checkout(target):
    entries = source_fingerprint(target)
    return {name: value for name, value in entries.items() if not name.startswith(".git/")} | {
        name: entries[name]
        for name in (".git/HEAD", ".git/index", ".git/config", ".git/refs/heads/fixture-main")
    }


def request(
    prepared,
    requester,
    completed,
    target,
    destination,
    *,
    name="fixture-integration",
    branch="verified-output",
):
    core, candidate = prepared[:2]
    approval = core.execute(
        "request_approval",
        {
            **requester,
            "action": "apply_merge_candidate",
            "subject_id": candidate["candidate_id"],
            "subject_sha": candidate["expected_candidate_sha"],
            "request_id": name,
        },
    )
    lookup = {**owner(prepared), "approval_id": approval["id"]}
    return lookup, {
        **lookup,
        "session_id": requester["session_id"],
        "session_token": requester["session_token"],
        "expected_version": approval["version"],
        "task_id": completed["task_id"],
        "expected_task_version": completed["version"],
        "target_root": str(target),
        "worktree_path": str(destination),
        "destination_branch": branch,
    }


def approve(client, payload):
    result = client.owner_call(PREVIEW, **payload)
    assert result["ok"], result
    preview = result["data"]
    confirmation = {**payload, "plan_sha256": preview["plan_sha256"]}
    result = client.owner_call(APPROVE, **confirmation)
    assert result["ok"], result
    return preview["plan"], confirmation | {
        "expected_version": result["data"]["approval"]["version"]
    }


def local_cli(core, op, payload):
    return subprocess.run(
        [
            sys.executable,
            "-s",
            "-B",
            "-m",
            "agentsync",
            "--data-dir",
            str(core.data_dir),
            "owner",
            op,
        ],
        cwd=core.data_dir,
        env=os.environ | {"PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1])},
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.fixture
def integrated_candidate(world, monkeypatch):
    core, _, actors, root = world
    git(root, "config", "core.autocrlf", "false")
    (root / ".gitattributes").write_bytes(b"*.txt text eol=crlf\n*.py text eol=lf\n*.png binary\n")
    git(root, "add", ".gitattributes")
    git(root, "add", "--renormalize", "--", "*.txt")
    git(root, "commit", "-m", "normal text and binary attributes")
    prepared = protocol_candidate(world, CODE)
    submit_pair(prepared, world)
    executor, args, _ = attempt(prepared)
    monkeypatch.setattr(candidate_executor, "verify_python_json_lines", synthetic_backend)
    completed = OwnerVerifiedTaskCompletion(core).complete_once(
        **completion_args(prepared, args, executor.execute_once(**args), reviewer(prepared))
    )
    target = root.parent / "target"
    git(root, "clone", "--no-hardlinks", "--no-local", str(root), str(target))
    git(target, "config", "core.autocrlf", "false")
    assert (target / "same.txt").read_bytes() == b"original\r\n"
    return prepared, actors[0], completed, root, target, target.parent / "integrated"


def test_exact_owner_cli_integration_materializes_verified_blob_bytes(integrated_candidate):
    prepared, requester, completed, source, target, destination = integrated_candidate
    core = prepared[0]
    hooks = target / ".git" / "hooks"
    sentinel = target.parent / "hook-ran"
    for name in ("reference-transaction", "post-checkout"):
        path = hooks / name
        path.write_text(
            f"#!/bin/sh\nprintf run > '{sentinel.as_posix()}'\nexit 1\n", encoding="utf-8"
        )
        path.chmod(0o755)
    original, baseline = original_checkout(target), source_fingerprint(source)
    client = AgentSyncClient(core.data_dir)
    lookup, payload = request(prepared, requester, completed, target, destination)
    first = client.owner_call(PREVIEW, **payload)["data"]
    assert (
        client.owner_call(APPROVE, **payload, plan_sha256="0" * 64)["error"]["code"]
        == "integration_plan_changed"
    )
    plan, run = approve(client, payload)
    assert plan == first["plan"] and plan["base_sha"] == git(target, "rev-parse", "HEAD")
    assert client.call(INTEGRATE, **run)["error"]["code"] == "unknown_operation"
    assert (
        client.owner_call(INTEGRATE, **(run | {"admin_token": "wrong"}))["error"]["code"]
        == "unauthorized"
    )
    assert not client.owner_call(
        INTEGRATE, **(run | {"expected_version": run["expected_version"] - 1})
    )["ok"]
    assert not client.owner_call(INTEGRATE, **(run | {"destination_branch": "other"}))["ok"]
    assert client.owner_call(STATUS, **lookup)["data"]["effect"] == "not_attempted"
    result = local_cli(core, INTEGRATE, run)
    assert result.returncode == 0, result.stdout
    assert all(
        run[key] not in result.stdout and run[key] not in result.stderr
        for key in ("admin_token", "session_token")
    )
    assert json.loads(result.stdout)["data"] == {
        "plan": plan,
        "approval_status": "consumed",
        "effect": "exact",
    }
    assert git(target, "symbolic-ref", "HEAD") == "refs/heads/fixture-main"
    assert git(destination, "symbolic-ref", "HEAD") == plan["destination_ref"]
    assert git(destination, "rev-parse", "HEAD^{tree}") == plan["tree_sha"]
    assert (destination / "solution.py").read_bytes() == CODE
    assert (destination / "same.txt").read_bytes() == b"original\n"
    assert (target / "same.txt").read_bytes() == b"original\r\n"
    assert not sentinel.exists() and original_checkout(target) == original
    assert source_fingerprint(source) == baseline
    reopened = AgentSyncClient(core.data_dir)
    assert reopened.owner_call(STATUS, **lookup)["data"]["effect"] == "exact"
    assert not reopened.owner_call(INTEGRATE, **run)["ok"]
    (destination / "same.txt").write_bytes(b"original\r\n")
    before_observe = source_fingerprint(destination)
    assert reopened.owner_call(STATUS, **lookup)["data"]["effect"] == "partial"
    assert source_fingerprint(destination) == before_observe
    with connect(core.db_path) as db:
        events = db.execute(
            "SELECT operation FROM audit_events WHERE operation LIKE 'candidate_integration_%' AND outcome IN ('allowed','success')"
        ).fetchall()
    assert sorted(row[0] for row in events) == [
        "candidate_integration_admit",
        "candidate_integration_approve",
        "candidate_integration_observed",
    ]


@pytest.mark.parametrize(
    "fault",
    [
        "dirty",
        "dirty-after-approval",
        "staged",
        "untracked",
        "hidden-index",
        "skip-worktree",
        "stale-base",
        "existing-branch",
        "existing-path",
        "include",
        "filter",
        "external-attributes",
        "expired",
        "private-approval",
    ],
)
def test_rejects_unsafe_target_or_unbound_approval(integrated_candidate, fault, monkeypatch):
    prepared, requester, completed, _, target, destination = integrated_candidate
    client = AgentSyncClient(prepared[0].data_dir)
    lookup, payload = request(prepared, requester, completed, target, destination)
    marker = target.parent / "external-ran"
    if fault == "dirty":
        (target / "same.txt").write_bytes(b"uncommitted\r\n")
    elif fault == "dirty-after-approval":
        _, run = approve(client, payload)
        (target / "same.txt").write_bytes(b"changed after approval\r\n")
    elif fault == "staged":
        (target / "same.txt").write_bytes(b"staged\r\n")
        git(target, "add", "same.txt")
    elif fault == "untracked":
        (target / "untracked.txt").write_bytes(b"private\n")
    elif fault in ("hidden-index", "skip-worktree"):
        flag = "--assume-unchanged" if fault == "hidden-index" else "--skip-worktree"
        git(target, "update-index", flag, "same.txt")
    elif fault == "stale-base":
        git(
            target,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "new head",
        )
    elif fault == "existing-branch":
        git(target, "branch", "VERIFIED-OUTPUT")
    elif fault == "existing-path":
        destination.mkdir()
    elif fault in ("include", "filter", "external-attributes"):
        if fault in ("include", "filter"):
            # This active clean filter would run if status got past config validation.
            script = target.parent / "filter.sh"
            script.write_text(
                f"#!/bin/sh\nprintf run > '{marker.as_posix()}'\ncat\n", encoding="utf-8"
            )
            script.chmod(0o755)
            with (target / ".gitattributes").open("ab") as file:
                file.write(b"*.txt filter=fixture\n")
            (target / "same.txt").write_bytes(b"dirty file requires clean conversion\r\n")
            if fault == "include":
                include = target.parent / "included.cfg"
                git(
                    target,
                    "config",
                    "--file",
                    str(include),
                    "filter.fixture.clean",
                    script.as_posix(),
                )
                key, value = "include.path", str(include)
            else:
                key, value = "filter.fixture.clean", script.as_posix()
        else:
            key, value = "core.attributesFile", str(marker)
        git(target, "config", key, value)
    elif fault == "expired":
        plan, run = approve(client, payload)
        monkeypatch.setattr(
            candidate_jobs, "time", SimpleNamespace(time=lambda: plan["expires_at"])
        )
    else:
        _, private_plan, private_run = approve_delivery(prepared, requester, completed)
        run = payload | {
            "approval_id": private_plan["approval_id"],
            "expected_version": private_run["expected_version"],
            "plan_sha256": private_run["plan_sha256"],
        }
    before = source_fingerprint(target)
    response = (
        client.owner_call(INTEGRATE, **run)
        if fault in ("expired", "private-approval", "dirty-after-approval")
        else client.owner_call(PREVIEW, **payload)
    )
    assert not response["ok"]
    assert not marker.exists() and source_fingerprint(target) == before
    status = client.owner_call(STATUS, **lookup)["data"]
    assert status["effect"] == "not_attempted"
    if fault == "dirty-after-approval":
        assert status["approval_status"] == "approved" and not destination.exists()
        with connect(prepared[0].db_path) as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM owner_idempotency WHERE operation='candidate_integration_admit'"
                ).fetchone()[0]
                == 0
            )


@pytest.mark.parametrize(
    "fault", ["gitlink", "symlink", "filter", "working-tree-encoding", "ident"]
)
def test_integration_git_rejects_unsupported_committed_tree_or_attributes(world, fault):
    core, _, _, root = world
    store = GitWorkspaceStore(core.data_dir)
    if fault in ("gitlink", "symlink"):
        if fault == "gitlink":
            mode, sha = "160000", git(root, "rev-parse", "HEAD")
        else:
            text = root.parent / "symlink-object"
            text.write_bytes(b"same.txt")
            mode, sha = "120000", git(root, "hash-object", "-w", str(text))
        git(root, "update-index", "--add", "--cacheinfo", f"{mode},{sha},unsupported")
    else:
        value = {
            "filter": "filter=fixture",
            "working-tree-encoding": "working-tree-encoding=UTF-8",
            "ident": "ident",
        }[fault]
        # Stage the attribute directly so fixture preparation never applies it.
        attributes = root.parent / "attribute-object"
        attributes.write_text(f"*.txt {value}\n", encoding="ascii")
        sha = git(root, "hash-object", "-w", str(attributes))
        git(root, "update-index", "--add", "--cacheinfo", f"100644,{sha},.gitattributes")
    git(root, "commit", "-m", "fixture unsupported integration object")
    original = source_fingerprint(root)
    with pytest.raises(
        AgentSyncError, match="without symlinks or submodules|encoding and identifier"
    ) as denied:
        IntegrationGit(store).target(root, git(root, "rev-parse", "HEAD"))
    assert denied.value.code == "integration_boundary" and source_fingerprint(root) == original


@pytest.mark.parametrize(
    "stage,expected",
    [("import_objects", "unknown"), ("create_branch", "partial"), ("write_worktree", "partial")],
)
def test_process_exit_after_each_effect_preserves_fence(integrated_candidate, stage, expected):
    prepared, requester, completed, _, target, destination = integrated_candidate
    core = prepared[0]
    client = AgentSyncClient(core.data_dir)
    lookup, payload = request(prepared, requester, completed, target, destination)
    plan, run = approve(client, payload)
    script = """
import json, os, sys
from agentsync.sdk import AgentSyncClient
from agentsync.workspaces.integration import IntegrationGit
original = getattr(IntegrationGit, sys.argv[2])
def stop_after(self, *args, **kwargs):
    original(self, *args, **kwargs)
    os._exit(74)
setattr(IntegrationGit, sys.argv[2], stop_after)
result = AgentSyncClient(sys.argv[1]).owner_call('integrate_candidate', **json.load(sys.stdin))
raise SystemExit(23 if result['ok'] else 24)
"""
    completed_process = subprocess.run(
        [sys.executable, "-s", "-B", "-c", script, str(core.data_dir), stage],
        cwd=core.data_dir,
        env=os.environ | {"PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1])},
        input=json.dumps(run),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed_process.returncode == 74
    reopened = AgentSyncClient(core.data_dir)
    assert reopened.owner_call(STATUS, **lookup)["data"] == {
        "plan": plan,
        "approval_status": "consumed",
        "effect": expected,
    }
    before = source_fingerprint(target)
    assert not reopened.owner_call(INTEGRATE, **run)["ok"]
    assert source_fingerprint(target) == before
    assert destination.exists() is (stage == "write_worktree")
    if stage == "import_objects":
        _, second = request(prepared, requester, completed, target, destination, name="second")
        _, second_run = approve(reopened, second)
        assert (
            reopened.owner_call(INTEGRATE, **second_run)["error"]["code"] == "integration_reserved"
        )


def test_cross_approval_branch_and_path_reservations_are_atomic(integrated_candidate, monkeypatch):
    prepared, requester, completed, _, target, destination = integrated_candidate
    client = AgentSyncClient(prepared[0].data_dir)
    requests = [
        request(prepared, requester, completed, target, path, name=name, branch=branch)
        for path, name, branch in (
            (destination, "first", "branch-a"),
            (destination, "same-path", "branch-b"),
            (destination.with_name("other"), "same-ref", "BRANCH-A"),
        )
    ]
    plans = [approve(client, payload)[1] for _, payload in requests]
    entered, release = Event(), Event()

    def stop(*_args):
        entered.set()
        assert release.wait(timeout=20)
        raise OSError("Fixture after durable admission")

    monkeypatch.setattr(IntegrationGit, "stage_bundle", stop)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(client.owner_call, INTEGRATE, **plans[0])
        try:
            assert entered.wait(timeout=30)
            with sqlite3.connect(client.core.db_path) as db:
                assert (
                    db.execute(
                        "SELECT count(*) FROM owner_idempotency WHERE operation='candidate_integration_fence'"
                    ).fetchone()[0]
                    == 2
                )
            contenders = [pool.submit(client.owner_call, INTEGRATE, **plan) for plan in plans[1:]]
        finally:
            release.set()
        assert first.result(timeout=45)["data"]["effect"] == "unknown"
        assert all(
            future.result(timeout=45)["error"]["code"] == "integration_reserved"
            for future in contenders
        )
    assert not destination.exists()

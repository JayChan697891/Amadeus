"""Real disposable Core/Git data publication; no model, apply or code execution."""

import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from conftest import owner_grant
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from test_m4b_workspaces import git, source_fingerprint

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient
from agentsync.storage.database import connect


@pytest.fixture
def world(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--initial-branch=fixture-main")
    git(source, "config", "user.name", "Proposal fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / "baseline.txt").write_text("unchanged\n", encoding="utf-8")
    git(source, "add", "baseline.txt")
    git(source, "commit", "-m", "fixture")
    core = Core(tmp_path / "core")
    owner = core.execute("create_project", {"name": "Proposal", "root_path": str(source)})
    member = core.execute("register_agent", {**owner, "name": "Worker"})
    owner_grant(core, owner, member, ("worker",))
    auth = {
        "project_id": owner["project_id"],
        "session_id": member["session_id"],
        "session_token": member["session_token"],
    }
    task = core.execute("create_task", {**auth, "title": "Code proposal", "request_id": "task"})
    snapshot = core.execute("capture_repository", {**auth, "request_id": "snapshot"})
    tree = core.execute(
        "create_worktree",
        {
            **auth,
            "task_id": task["id"],
            "snapshot_id": snapshot["snapshot_id"],
            "request_id": "tree",
        },
    )
    claim = core.execute(
        "claim_task",
        {**auth, "task_id": task["id"], "expected_version": task["version"], "request_id": "claim"},
    )
    active = core.execute(
        "update_task",
        {
            **auth,
            "task_id": task["id"],
            "lease_token": claim["lease_token"],
            "expected_version": claim["version"],
            "status": "running",
            "request_id": "running",
        },
    )
    request = {
        **auth,
        "task_id": task["id"],
        "lease_token": claim["lease_token"],
        "expected_version": active["version"],
        "worktree_id": tree["worktree_id"],
        "expected_head": tree["head_sha"],
        "allowed_paths": ["answer.py"],
        "proposal_json": json.dumps(
            {
                "files": [
                    {
                        "path": "answer.py",
                        "content": "raise RuntimeError('INERT_PROPOSAL_SENTINEL')\n",
                    }
                ]
            }
        ),
        "request_id": "proposal",
    }
    return core, owner, member, auth, request, tree, source


def counts(core):
    with connect(core.db_path) as db:
        return {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("context_revisions", "merge_candidates", "candidate_verification_jobs")
        }


def test_publication_survives_restart_without_task_or_workspace_mutation(world):
    core, owner, _, auth, request, tree, source = world
    before = core.execute("get_project_state", auth)["tasks"]
    fingerprints = [source_fingerprint(p) for p in (source, Path(tree["path"]))]
    result = core.execute("publish_task_proposal", request)
    assert result["context_version"] == 1
    assert result["task_version"] == request["expected_version"]
    assert "INERT_PROPOSAL_SENTINEL" not in json.dumps(result)
    reopened = Core(core.data_dir)
    context = reopened.execute(
        "get_context",
        {**auth, "context_id": result["context_id"], "version": result["context_version"]},
    )
    assert hashlib.sha256(context["content"].encode()).hexdigest() == result["content_sha256"]
    content = json.loads(context["content"])
    assert content["task_id"] == request["task_id"]
    assert content["base_head"] == tree["head_sha"]
    assert content["execution_provenance"] == result["verification"] == "unverified"
    assert "INERT_PROPOSAL_SENTINEL" in content["files"][0]["content"]
    assert reopened.execute("get_project_state", auth)["tasks"] == before
    assert [source_fingerprint(p) for p in (source, Path(tree["path"]))] == fingerprints
    assert counts(core) == {
        "context_revisions": 1,
        "merge_candidates": 0,
        "candidate_verification_jobs": 0,
    }
    audit = core.execute_owner("list_audit", {**owner, "limit": 100, "offset": 0})
    assert "INERT_PROPOSAL_SENTINEL" not in json.dumps(audit)
    assert not (Path(tree["path"]) / "answer.py").exists()


def test_concurrent_replay_publishes_once_and_revocation_precedes_replay(world):
    core, owner, member, _, request, _, _ = world
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: Core(core.data_dir).execute("publish_task_proposal", request), range(2)
            )
        )
    assert results[0] == results[1]
    assert counts(core)["context_revisions"] == 1
    with pytest.raises(AgentSyncError) as exc:
        core.execute(
            "publish_task_proposal",
            {**request, "proposal_json": request["proposal_json"].replace("SENTINEL", "CHANGED")},
        )
    assert exc.value.code == "idempotency_conflict"
    owner_grant(core, owner, member, ("viewer",))
    with pytest.raises(AgentSyncError) as exc:
        core.execute("publish_task_proposal", request)
    assert exc.value.code == "forbidden"


@pytest.mark.parametrize(
    "scenario",
    [
        "version",
        "lease",
        "expired",
        "foreign-agent",
        "foreign-project",
        "other-task",
        "head",
        "dirty",
        "invalid-output",
    ],
)
def test_rejected_publication_has_no_context_or_candidate(world, scenario):
    core, owner, _, auth, request, tree, _ = world
    if scenario == "version":
        request["expected_version"] += 1
    elif scenario == "lease":
        request["lease_token"] = "invalid"
    elif scenario == "expired":
        with connect(core.db_path) as db:
            db.execute("UPDATE tasks SET lease_expires_at=0 WHERE id=?", (request["task_id"],))
            db.commit()
    elif scenario == "foreign-agent":
        other = core.execute("register_agent", {**owner, "name": "Other"})
        owner_grant(core, owner, other, ("worker",))
        other_tree = core.execute(
            "create_worktree",
            {
                **auth,
                "session_id": other["session_id"],
                "session_token": other["session_token"],
                "task_id": request["task_id"],
                "snapshot_id": tree["snapshot_id"],
                "request_id": "other-tree",
            },
        )
        request["worktree_id"] = other_tree["worktree_id"]
    elif scenario == "foreign-project":
        request["project_id"] = "foreign"
    elif scenario == "other-task":
        other = core.execute("create_task", {**auth, "title": "Other task", "request_id": "other"})
        other_tree = core.execute(
            "create_worktree",
            {
                **auth,
                "task_id": other["id"],
                "snapshot_id": tree["snapshot_id"],
                "request_id": "other-task-tree",
            },
        )
        request["worktree_id"] = other_tree["worktree_id"]
    elif scenario == "head":
        request["expected_head"] = "0" * 40
    elif scenario == "dirty":
        (Path(tree["path"]) / "baseline.txt").write_text("changed", encoding="utf-8")
    else:
        request["proposal_json"] = '{"files":[],"command":"run me"}'
    with pytest.raises(AgentSyncError) as exc:
        core.execute("publish_task_proposal", request)
    assert (
        exc.value.code
        == {
            "version": "version_conflict",
            "lease": "lease_denied",
            "expired": "lease_expired",
            "foreign-agent": "workspace_boundary",
            "foreign-project": "unauthorized",
            "other-task": "workspace_boundary",
            "head": "workspace_boundary",
            "dirty": "workspace_boundary",
            "invalid-output": "proposal_invalid",
        }[scenario]
    )
    assert counts(core) == {
        "context_revisions": 0,
        "merge_candidates": 0,
        "candidate_verification_jobs": 0,
    }


def test_audit_failure_rolls_back_context_and_idempotency(world, monkeypatch):
    core, _, _, _, request, _, _ = world
    original = core._audit_event

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic audit failure")

    monkeypatch.setattr(core, "_audit_event", fail)
    with pytest.raises(RuntimeError, match="Synthetic audit failure"):
        core.execute("publish_task_proposal", request)
    assert counts(core)["context_revisions"] == 0
    monkeypatch.setattr(core, "_audit_event", original)
    assert core.execute("publish_task_proposal", request)["context_version"] == 1


@pytest.mark.parametrize("change", ["advance", "expire"])
def test_replay_is_historical_after_task_changes(world, change):
    core, _, _, auth, request, _, _ = world
    published = core.execute("publish_task_proposal", request)
    if change == "advance":
        core.execute(
            "update_task",
            {
                **auth,
                "task_id": request["task_id"],
                "lease_token": request["lease_token"],
                "expected_version": request["expected_version"],
                "status": "review",
                "request_id": "review",
            },
        )
    else:
        with connect(core.db_path) as db:
            db.execute("UPDATE tasks SET lease_expires_at=0 WHERE id=?", (request["task_id"],))
            db.commit()
    before = core.execute("get_project_state", auth)["tasks"]
    assert Core(core.data_dir).execute("publish_task_proposal", request) == published
    assert core.execute("get_project_state", auth)["tasks"] == before
    assert counts(core)["context_revisions"] == 1


def test_lease_is_rechecked_after_git_inspection(world, monkeypatch):
    core, _, _, _, request, _, _ = world
    inspect = core._inspect_owned_worktree

    def inspect_then_expire(*args):
        result = inspect(*args)
        monkeypatch.setattr("agentsync.core.workspaces.time.time", lambda: 10**12)
        return result

    monkeypatch.setattr(core, "_inspect_owned_worktree", inspect_then_expire)
    with pytest.raises(AgentSyncError) as exc:
        core.execute("publish_task_proposal", request)
    assert exc.value.code == "lease_expired"
    assert counts(core)["context_revisions"] == 0


async def test_http_mcp_and_sdk_share_one_atomic_proposal(world):
    core, _, _, auth, request, _, _ = world
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=create_app(core.data_dir, "fixture-token"), client=("127.0.0.1", 123)
        ),
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer fixture-token"},
    ) as client:
        response = await client.post("/v1/publish_task_proposal", json=request)
        assert response.status_code == 200
        expected = response.json()
        assert expected["ok"] is True
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentsync", "--data-dir", str(core.data_dir), "mcp"],
        env=os.environ.copy(),
    )
    async with Client(parameters, read_timeout_seconds=15) as client:
        listing = await client.list_tools()
        schema = next(t.input_schema for t in listing.tools if t.name == "publish_task_proposal")
        assert {
            "task_id",
            "expected_version",
            "lease_token",
            "expected_head",
            "allowed_paths",
            "proposal_json",
        } <= set(schema["required"])
        response = await client.call_tool("publish_task_proposal", request)
        actual = response.structured_content or json.loads(response.content[0].text)
        assert actual == expected
    sdk = AgentSyncClient(core.data_dir)
    assert sdk.call("publish_task_proposal", **request) == expected
    context = sdk.call("get_context", **auth, context_id=expected["data"]["context_id"], version=1)
    assert context["ok"] is True
    assert counts(core)["context_revisions"] == 1

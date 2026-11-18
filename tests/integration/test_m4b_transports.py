"""Real Git and official MCP subprocess transport evidence, not model-client evidence."""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from conftest import owner_grant
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient


def git(root, *args):
    executable = shutil.which("git")
    assert executable, "Real Git is required for the M4B transport acceptance tier"
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(
        [
            executable,
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
        env=env,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return result.stdout.decode("utf-8").strip()


def test_fixture_git_disables_automatic_maintenance_even_with_repository_overrides(tmp_path):
    git(tmp_path, "init", "--initial-branch=fixture-main")
    git(tmp_path, "config", "gc.auto", "1")
    git(tmp_path, "config", "maintenance.auto", "true")
    # Query real Git's effective configuration, including the helper's overrides.
    assert git(tmp_path, "config", "--get", "gc.auto") == "0"
    assert git(tmp_path, "config", "--get", "maintenance.auto") == "false"


def fingerprint(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_m4b_five_mcp_operations_share_real_git_state_with_http_and_sdk(tmp_path):
    source = tmp_path / "disposable-source"
    source.mkdir()
    git(source, "init", "--initial-branch=fixture-main")
    git(source, "config", "user.name", "Transport acceptance fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / "baseline.txt").write_text("committed baseline\n", encoding="utf-8")
    git(source, "add", ".")
    git(source, "commit", "-m", "isolated baseline")
    original = fingerprint(source)
    data = tmp_path / "service-state"

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(data), "mcp"],
            env=os.environ.copy(),
        )
        async with Client(parameters, read_timeout_seconds=60) as client:

            async def call(operation, **payload):
                response = await client.call_tool(operation, payload)
                result = response.structured_content or json.loads(response.content[0].text)
                assert not response.is_error and result["ok"], result
                return result["data"]

            listing = await client.list_tools()
            schemas = {tool.name: tool.input_schema for tool in listing.tools}
            assert len(schemas) == 34
            for operation in (
                "capture_repository",
                "create_worktree",
                "inspect_worktree",
                "compare_worktrees",
                "prepare_merge_candidate",
            ):
                assert {"project_id", "session_id", "session_token"} <= set(
                    schemas[operation]["required"]
                )
            assert "request_id" in schemas["prepare_merge_candidate"]["required"]
            assert "expected_right_head" in schemas["compare_worktrees"]["required"]

            project = await call("create_project", name="M4B transport", root_path=str(source))
            actors = []
            for name in ("Developer A", "Developer B"):
                actor = await call("register_agent", **project, name=name)
                owner_grant(AgentSyncClient(data).core, project, actor)
                actors.append(
                    {
                        "project_id": project["project_id"],
                        "session_id": actor["session_id"],
                        "session_token": actor["session_token"],
                    }
                )
            snapshot = await call("capture_repository", **actors[0], request_id=uuid4().hex)
            assert snapshot["committed_only"] is True
            assert snapshot["source_dirty"] is False
            trees = []
            for actor, name in zip(actors, ("left", "right"), strict=True):
                task = await call(
                    "create_task", **actor, title=f"Edit {name}", request_id=uuid4().hex
                )
                tree = await call(
                    "create_worktree",
                    **actor,
                    snapshot_id=snapshot["snapshot_id"],
                    task_id=task["id"],
                    request_id=uuid4().hex,
                )
                path = Path(tree["path"])
                assert path.is_relative_to(data)
                (path / f"{name}.txt").write_text(f"{name} independent change\n", encoding="utf-8")
                git(path, "add", f"{name}.txt")
                git(
                    path,
                    "-c",
                    "user.name=Transport fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    f"isolated {name} change",
                )
                current = await call("inspect_worktree", **actor, worktree_id=tree["worktree_id"])
                assert current["dirty"] is False
                assert current["head_sha"] == git(path, "rev-parse", "HEAD")
                assert "repository_path" not in current and "root_identity" not in current
                trees.append(current)
            assert trees[0]["path"] != trees[1]["path"]
            pinned = {
                "left_id": trees[0]["worktree_id"],
                "right_id": trees[1]["worktree_id"],
                "expected_left_head": trees[0]["head_sha"],
                "expected_right_head": trees[1]["head_sha"],
            }
            compared = await call("compare_worktrees", **actors[0], **pinned)
            assert compared["mergeable"] is True
            assert compared["merge_exit_code"] == 0
            assert compared["conflict_paths"] == []
            candidate_request = {**actors[0], **pinned, "request_id": uuid4().hex}
            candidate = await call("prepare_merge_candidate", **candidate_request)
            assert candidate["status"] == "awaiting_human_approval"
            assert sorted(candidate["changed_paths"]) == ["left.txt", "right.txt"]
            assert "approved" not in candidate and "candidate_path" not in candidate

            # ASGI adapter and in-process SDK independently reopen the same SQLite/Core state.
            app = create_app(data, api_token="isolated-http-fixture")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1",
                headers={"Authorization": "Bearer isolated-http-fixture"},
            ) as http:
                result = await http.post(
                    "/v1/inspect_worktree",
                    json={**actors[1], "worktree_id": trees[0]["worktree_id"]},
                )
                assert result.status_code == 200
                assert result.json()["data"] == trees[0]
                replay = await http.post("/v1/prepare_merge_candidate", json=candidate_request)
                assert replay.status_code == 200
                assert replay.json()["data"] == candidate
            sdk = AgentSyncClient(data)
            inspected = sdk.call(
                "inspect_worktree", **actors[0], worktree_id=trees[1]["worktree_id"]
            )
            assert inspected["ok"] and inspected["data"] == trees[1]
            assert sdk.call("prepare_merge_candidate", **candidate_request) == {
                "ok": True,
                "data": candidate,
            }

    asyncio.run(scenario())
    assert fingerprint(source) == original

"""Real transport owner boundaries; seeded candidate is metadata, not Git/model proof."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient


def test_owner_sdk_http_and_stdin_cli_are_separate_authorities(tmp_path):
    data = tmp_path / "owner-transport-state"
    sdk = AgentSyncClient(data)
    project = sdk.call("create_project", name="Owner boundary", root_path=str(tmp_path))["data"]
    actor = sdk.call("register_agent", **project, name="default viewer")["data"]
    auth = {
        "project_id": project["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    denied = sdk.call("create_task", **auth, title="Not granted", request_id="before-grant")
    assert not denied["ok"]
    assert not sdk.call(
        "set_agent_roles",
        **project,
        agent_id=actor["agent_id"],
        roles=["worker"],
        expected_version=1,
        request_id="ordinary",
    )["ok"]
    assert not sdk.owner_call("list_members", **{**project, "admin_token": actor["session_token"]})[
        "ok"
    ]

    async def scenario():
        app = create_app(data, "owner-http-bearer")
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
            endpoint = "/owner/v1/set_agent_roles"
            payload = {
                **project,
                "agent_id": actor["agent_id"],
                "roles": ["worker"],
                "expected_version": 1,
                "request_id": "owner-http-grant",
            }
            assert (await http.post(endpoint, json=payload)).status_code == 401
            headers = {"Authorization": "Bearer owner-http-bearer"}
            bad = await http.post(
                endpoint, json={**payload, "admin_token": actor["session_token"]}, headers=headers
            )
            assert bad.status_code in {401, 403}
            response = await http.post(endpoint, json=payload, headers=headers)
            assert response.status_code == 200 and response.json()["ok"]
            assert response.json()["data"]["roles"] == ["worker"]
            assert (
                await http.post("/v1/set_agent_roles", json=payload, headers=headers)
            ).status_code == 404
            remote = httpx.ASGITransport(app=app, client=("192.0.2.1", 1))
            async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1") as outside:
                assert (
                    await outside.post(endpoint, json=payload, headers=headers)
                ).status_code == 403

    asyncio.run(scenario())
    assert sdk.call("create_task", **auth, title="Explicit owner grant", request_id="after-grant")[
        "ok"
    ]
    command = [sys.executable, "-m", "agentsync", "--data-dir", str(data), "owner", "list_members"]
    listed = subprocess.run(
        command, input=json.dumps(project), capture_output=True, text=True, timeout=15
    )
    assert listed.returncode == 0, listed.stderr
    envelope = json.loads(listed.stdout)
    assert envelope["ok"] and envelope["data"]["members"][0]["roles"] == ["worker"]
    assert project["admin_token"] not in listed.stdout + listed.stderr + " ".join(command)
    grant_command = [*command[:-1], "set_agent_roles"]
    cli_grant = subprocess.run(
        grant_command,
        input=json.dumps(
            {
                **project,
                "agent_id": actor["agent_id"],
                "roles": ["worker", "reviewer"],
                "expected_version": 2,
                "request_id": "cli-owner-grant",
            }
        ),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert cli_grant.returncode == 0, cli_grant.stderr
    assert json.loads(cli_grant.stdout)["data"]["roles"] == ["reviewer", "worker"]
    assert sdk.call("list_audit", **auth)["ok"]
    assert project["admin_token"] not in cli_grant.stdout + cli_grant.stderr + " ".join(
        grant_command
    )
    malformed = subprocess.run(
        command, input='{"admin_token":"DO-NOT-ECHO",', capture_output=True, text=True, timeout=15
    )
    assert malformed.returncode == 1
    assert "DO-NOT-ECHO" not in malformed.stdout + malformed.stderr
    assert not json.loads(malformed.stdout)["ok"]


def test_real_mcp_permissions_approval_tools_and_no_owner_discovery(tmp_path):
    data = tmp_path / "mcp-owner-state"
    sdk = AgentSyncClient(data)

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(data), "mcp"],
            env=os.environ.copy(),
        )
        async with Client(params, read_timeout_seconds=30) as client:

            async def call(operation, **payload):
                result = await client.call_tool(operation, payload)
                return result.structured_content or json.loads(result.content[0].text)

            listing = await client.list_tools()
            names = {tool.name for tool in listing.tools}
            assert len(names) == 33
            assert {"request_approval", "get_approval", "list_approvals", "list_audit"} <= names
            assert names.isdisjoint(
                {"set_agent_roles", "list_members", "decide_approval", "revoke_approval"}
            )
            project = (await call("create_project", name="M5 real stdio", root_path=str(tmp_path)))[
                "data"
            ]
            actor = (await call("register_agent", **project, name="viewer"))["data"]
            auth = {
                "project_id": project["project_id"],
                "session_id": actor["session_id"],
                "session_token": actor["session_token"],
            }
            denied = await call(
                "create_task", **auth, title="Not allowed", request_id="viewer-deny"
            )
            assert not denied["ok"]
            # Owner authority stays out of MCP, using the separate SDK control plane.
            granted = sdk.owner_call(
                "set_agent_roles",
                **project,
                agent_id=actor["agent_id"],
                roles=["worker", "reviewer"],
                expected_version=1,
                request_id="separate-owner-grant",
            )
            assert granted["ok"]
            task = (await call("create_task", **auth, title="Allowed", request_id="worker-write"))[
                "data"
            ]
            candidate_id = uuid4().hex
            candidate = {
                "candidate_id": candidate_id,
                "candidate_sha": "c" * 40,
                "base_sha": "a" * 40,
                "left_sha": "b" * 40,
                "right_sha": "d" * 40,
                "changed_paths": ["metadata-only.txt"],
                "status": "awaiting_human_approval",
            }
            # Fixture only: tests approval transport against immutable stored metadata.
            # Actual Git candidate creation is independently covered in M4B tests.
            with sqlite3.connect(sdk.core.db_path) as db:
                db.execute(
                    "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
                    ("snapshot", project["project_id"], actor["session_id"], time.time(), "{}"),
                )
                for tree in ("left", "right"):
                    db.execute(
                        "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
                        (
                            tree,
                            project["project_id"],
                            "snapshot",
                            task["id"],
                            actor["session_id"],
                            time.time(),
                            "{}",
                        ),
                    )
                db.execute(
                    "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
                    (
                        candidate_id,
                        project["project_id"],
                        "left",
                        "right",
                        actor["session_id"],
                        time.time(),
                        json.dumps(candidate),
                    ),
                )
            requested = await call(
                "request_approval",
                **auth,
                action="apply_merge_candidate",
                subject_id=candidate_id,
                subject_sha=candidate["candidate_sha"],
                reason="PRIVATE-METADATA-NOT-AUDIT",
                request_id="request",
            )
            assert requested["ok"] and requested["data"]["status"] == "pending"
            approval = requested["data"]
            assert "reason" not in approval
            got = await call("get_approval", **auth, approval_id=approval["id"])
            assert got["data"] == approval
            listed = await call("list_approvals", **auth)
            assert listed["ok"] and listed["data"]["approvals"] == [approval]
            decided = sdk.owner_call(
                "decide_approval",
                **project,
                approval_id=approval["id"],
                expected_version=approval["version"],
                accept=True,
                request_id="owner-decision",
            )
            assert decided["ok"] and decided["data"]["status"] == "approved"
            updated = await call("get_approval", **auth, approval_id=approval["id"])
            assert updated["data"]["status"] == "approved"
            audit = await call("list_audit", **auth)
            assert audit["ok"] and audit["data"]["events"]
            serialized = json.dumps(audit)
            for secret in (
                project["admin_token"],
                actor["session_token"],
                "PRIVATE-METADATA-NOT-AUDIT",
            ):
                assert secret not in serialized
            with sqlite3.connect(sdk.core.db_path) as db:
                saved = json.loads(
                    db.execute(
                        "SELECT receipt FROM merge_candidates WHERE id=?", (candidate_id,)
                    ).fetchone()[0]
                )
            assert saved["status"] == "awaiting_human_approval"

    asyncio.run(scenario())

import asyncio
import json
import os
import subprocess
import sys
from uuid import uuid4

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agentsync import __version__
from agentsync.cli import run_demo
from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient


def test_sdk_and_mock_demo_persist(tmp_path):
    result = run_demo(tmp_path / "demo")
    assert result["ok"]
    assert result["data"]["persistence_verified"]
    assert result["data"]["duplicate_claim_rejected"]
    client = AgentSyncClient(tmp_path / "other")
    invalid = client.call("execute_arbitrary_command", command="never run")
    assert invalid["ok"] is False
    assert set(invalid["error"]) == {"code", "message"}


def test_http_security_and_core_errors(tmp_path):
    async def scenario():
        app = create_app(tmp_path / "http", "local-secret")
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 123))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            health = await client.get("/health")
            assert health.json() == {"status": "ok", "version": __version__}
            missing = await client.post("/v1/create_project", json={})
            assert missing.status_code == 401
            headers = {"Authorization": "Bearer local-secret"}
            created = await client.post("/v1/create_project", headers=headers,
                                        json={"name": "HTTP", "root_path": str(tmp_path)})
            assert created.status_code == 200
            assert created.json()["ok"]
            invalid = await client.post("/v1/create_project", headers=headers,
                                        json={"name": "HTTP", "root_path": str(tmp_path), "extra": True})
            assert invalid.status_code == 400
            assert invalid.json()["ok"] is False
            malformed = await client.post("/v1/create_project", headers=headers, content="not json")
            assert malformed.status_code == 400
            hostile_host = await client.get("/health", headers={"Host": "evil.example"})
            assert hostile_host.status_code == 400
            assert "access-control-allow-origin" not in health.headers
        remote_transport = httpx.ASGITransport(app=app, client=("192.0.2.1", 1))
        async with httpx.AsyncClient(transport=remote_transport, base_url="http://localhost") as remote:
            assert (await remote.get("/health")).status_code == 403
    asyncio.run(scenario())


def test_cli_rejects_public_binding_and_missing_token(tmp_path):
    env = os.environ.copy()
    env.pop("AGENTSYNC_HTTP_TOKEN", None)
    for args, expected in [(["serve", "--host", "0.0.0.0"], "loopback"),
                           (["serve", "--host", "127.0.0.2"], "supported loopback"),
                           (["serve"], "AGENTSYNC_HTTP_TOKEN")]:
        result = subprocess.run([sys.executable, "-m", "agentsync", "--data-dir", str(tmp_path), *args],
                                env=env, text=True, capture_output=True, timeout=15)
        assert result.returncode == 2
        assert expected in result.stderr


def test_documented_sdk_import():
    from agentsync.sdk.client import AgentSyncClient as DocumentedClient
    assert DocumentedClient is AgentSyncClient


def test_real_mcp_stdio_tools_and_core(tmp_path):
    async def scenario():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(tmp_path / "mcp"), "mcp"], env=os.environ.copy())
        async with Client(params, read_timeout_seconds=15) as client:
            listing = await client.list_tools()
            names = {tool.name for tool in listing.tools}
            assert names == {"create_project", "register_agent", "heartbeat", "create_task", "list_tasks",
                "get_project_state", "claim_task", "renew_lease", "update_task", "review_task", "reclaim_expired"}
            create_schema = next(tool.input_schema for tool in listing.tools if tool.name == "create_task")
            assert "request_id" in create_schema["required"]
            assert "session_token" in create_schema["properties"]
            created = await client.call_tool("create_project", {"name": "MCP subprocess", "root_path": str(tmp_path)})
            assert not created.is_error
            envelope = created.structured_content or json.loads(created.content[0].text)
            assert envelope["ok"]
            assert "admin_token" in envelope["data"]
            registered = await client.call_tool("register_agent", {**envelope["data"], "name": "Native MCP agent"})
            session = registered.structured_content["data"]
            task_result = await client.call_tool("create_task", {"project_id": envelope["data"]["project_id"],
                "session_id": session["session_id"], "session_token": session["session_token"],
                "title": "Typed default lists", "request_id": str(uuid4())})
            assert task_result.structured_content["ok"]
            assert task_result.structured_content["data"]["dependencies"] == []
            rejected = await client.call_tool("list_tasks", {"project_id": envelope["data"]["project_id"],
                "session_id": "bad", "session_token": "bad"})
            error = rejected.structured_content or json.loads(rejected.content[0].text)
            assert error["ok"] is False
    asyncio.run(scenario())


def test_two_mcp_processes_share_atomic_claim(tmp_path):
    data_dir = tmp_path / "shared-mcp"
    sdk = AgentSyncClient(data_dir)
    project = sdk.call("create_project", name="Shared", root_path=str(tmp_path))["data"]
    agents = [sdk.call("register_agent", **project, name=name)["data"] for name in ("A", "B")]
    auth = [{"project_id": project["project_id"], "session_id": agent["session_id"],
             "session_token": agent["session_token"]} for agent in agents]
    task = sdk.call("create_task", **auth[0], title="Exclusive", request_id=str(uuid4()))["data"]

    async def scenario():
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(data_dir), "mcp"], env=os.environ.copy())
        async with Client(params, read_timeout_seconds=15) as first, Client(params, read_timeout_seconds=15) as second:
            results = await asyncio.gather(*[
                client.call_tool("claim_task", {**credentials, "task_id": task["id"],
                    "expected_version": task["version"], "request_id": str(uuid4())})
                for client, credentials in zip((first, second), auth, strict=True)])
            envelopes = [result.structured_content for result in results]
            assert sorted(item["ok"] for item in envelopes) == [False, True]
    asyncio.run(scenario())
    assert sdk.call("list_tasks", **auth[0])["data"]["tasks"][0]["status"] == "claimed"


def test_sdk_http_share_one_persistent_workflow(tmp_path):
    data_dir = tmp_path / "shared-http"
    sdk = AgentSyncClient(data_dir)
    project = sdk.call("create_project", name="Cross transport", root_path=str(tmp_path))["data"]
    agent_a = sdk.call("register_agent", **project, name="A")["data"]
    agent_b = sdk.call("register_agent", **project, name="B")["data"]
    auth_a = {"project_id": project["project_id"], "session_id": agent_a["session_id"], "session_token": agent_a["session_token"]}
    auth_b = {"project_id": project["project_id"], "session_id": agent_b["session_id"], "session_token": agent_b["session_token"]}
    task = sdk.call("create_task", **auth_a, title="SDK to HTTP", request_id=str(uuid4()))["data"]

    async def scenario():
        app = create_app(data_dir, "secret")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
                                    base_url="http://127.0.0.1", headers={"Authorization": "Bearer secret"}) as http:
            response = await http.post("/v1/claim_task", json={**auth_a, "task_id": task["id"], "expected_version": task["version"], "request_id": str(uuid4())})
            claimed = response.json()["data"]
            for status in ("running", "review"):
                response = await http.post("/v1/update_task", json={**auth_a, "task_id": task["id"], "lease_token": claimed["lease_token"],
                    "expected_version": claimed["version"], "status": status, "request_id": str(uuid4())})
                assert response.json()["ok"]
                updated = response.json()["data"]
                claimed["version"] = updated["version"]
            return claimed["version"]
    version = asyncio.run(scenario())
    result = sdk.call("review_task", **auth_b, task_id=task["id"], expected_version=version, accept=True,
                      evidence="Cross-transport integration assertion", request_id=str(uuid4()))
    assert result["ok"] and result["data"]["status"] == "completed"
    persisted = AgentSyncClient(data_dir).call("list_tasks", **auth_b)
    assert persisted["data"]["tasks"][0]["status"] == "completed"

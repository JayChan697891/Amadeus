import asyncio
import hashlib
import json
import os
import sys
from uuid import uuid4

import httpx
from conftest import owner_grant
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient


def test_m4_http_sdk_share_file_versions_and_leases(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    original = b"external editor owns this content\n"
    (root / "sample.txt").write_bytes(original)
    data = tmp_path / "data"
    sdk = AgentSyncClient(data)

    def call(operation, **payload):
        response = sdk.call(operation, **payload)
        assert response["ok"], response
        return response["data"]

    project = call("create_project", name="M4 HTTP", root_path=str(root))
    agent = call("register_agent", **project, name="A")
    owner_grant(sdk.core, project, agent)
    auth = {
        "project_id": project["project_id"],
        "session_id": agent["session_id"],
        "session_token": agent["session_token"],
    }

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(data, "local-secret"), client=("127.0.0.1", 123)
            ),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer local-secret"},
        ) as http:

            async def post(operation, **payload):
                response = await http.post("/v1/" + operation, json={**auth, **payload})
                assert response.status_code == 200, response.text
                assert response.json()["ok"]
                return response.json()["data"]

            inspected = await post("inspect_path", path="sample.txt")
            assert inspected == call("inspect_path", **auth, path="sample.txt")
            assert inspected["sha256"] == hashlib.sha256(original).hexdigest()
            assert "content" not in inspected
            checked = await post(
                "verify_file_version",
                path="sample.txt",
                expected_sha256=inspected["sha256"].upper(),
            )
            assert checked["matches"] is True
            lock = await post("acquire_file_lock", path="sample.txt", request_id=str(uuid4()))
            listed = call("list_file_locks", **auth)
            assert listed["locks"][0]["id"] == lock["id"]
            assert "lease_token" not in listed["locks"][0]
            assert not any("hash" in key for key in listed["locks"][0])
            renewed = await post(
                "renew_file_lock",
                lock_id=lock["id"],
                lease_token=lock["lease_token"],
                expected_version=lock["version"],
                request_id=str(uuid4()),
            )
            released = await post(
                "release_file_lock",
                lock_id=lock["id"],
                lease_token=renewed["lease_token"],
                expected_version=renewed["version"],
                request_id=str(uuid4()),
            )
            assert released["status"] == "released"
            assert "lease_token" not in released
            assert (await post("list_file_locks"))["locks"] == []
            (root / "sample.txt").write_bytes(b"external edit\n")
            assert not call(
                "verify_file_version",
                **auth,
                path="sample.txt",
                expected_sha256=inspected["sha256"],
            )["matches"]
            assert (root / "sample.txt").read_bytes() == b"external edit\n"

    asyncio.run(scenario())


def test_m4_mcp_explicit_tools_and_real_resource_workflow(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    data = tmp_path / "data"

    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(data), "mcp"],
            env=os.environ.copy(),
        )
        async with Client(params, read_timeout_seconds=20) as client:

            async def call(operation, **payload):
                response = await client.call_tool(operation, payload)
                result = response.structured_content or json.loads(response.content[0].text)
                assert not response.is_error and result["ok"], result
                return result["data"]

            listing = await client.list_tools()
            assert len(listing.tools) == 33
            tools = {tool.name: tool.input_schema for tool in listing.tools}
            for name in (
                "inspect_path",
                "verify_file_version",
                "acquire_file_lock",
                "renew_file_lock",
                "release_file_lock",
                "list_file_locks",
            ):
                assert "session_token" in tools[name]["required"]
            assert "expected_sha256" in tools["verify_file_version"]["required"]
            assert "request_id" in tools["acquire_file_lock"]["required"]
            project = await call("create_project", name="M4 MCP", root_path=str(root))
            agent = await call("register_agent", **project, name="MCP A")
            owner_grant(AgentSyncClient(data).core, project, agent)
            auth = {
                "project_id": project["project_id"],
                "session_id": agent["session_id"],
                "session_token": agent["session_token"],
            }
            inspected = await call("inspect_path", **auth, path="missing.txt")
            assert inspected == {
                "path": "missing.txt",
                "exists": False,
                "kind": "missing",
                "sha256": None,
                "size": None,
            }
            assert (
                await call("verify_file_version", **auth, path="missing.txt", expected_sha256=None)
            )["matches"]
            lock = await call(
                "acquire_file_lock", **auth, path="missing.txt", request_id=str(uuid4())
            )
            renewed = await call(
                "renew_file_lock",
                **auth,
                lock_id=lock["id"],
                lease_token=lock["lease_token"],
                expected_version=lock["version"],
                request_id=str(uuid4()),
            )
            listed = await call("list_file_locks", **auth)
            assert listed["locks"][0]["version"] == renewed["version"]
            released = await call(
                "release_file_lock",
                **auth,
                lock_id=lock["id"],
                lease_token=renewed["lease_token"],
                expected_version=renewed["version"],
                request_id=str(uuid4()),
            )
            assert released["status"] == "released"
            assert not (root / "missing.txt").exists()

    asyncio.run(scenario())

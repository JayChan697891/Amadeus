import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from agentsync.integrations.http import create_app
from agentsync.sdk import AgentSyncClient


def test_real_independent_mcp_client_process_handoff(tmp_path):
    example = Path(__file__).resolve().parents[2] / "examples" / "m3_handoff.py"
    result = subprocess.run(
        [sys.executable, str(example), "--data-dir", str(tmp_path / "relay")],
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["status"] == "completed"
    assert len(set(evidence["client_process_ids"])) == 3
    assert evidence["pinned_context_version"] == 1
    assert evidence["latest_context_version"] == 2
    assert "no desktop host or model" in evidence["evidence_scope"]


def test_mcp_handoff_has_explicit_nested_typed_schema(tmp_path):
    async def scenario():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "agentsync", "--data-dir", str(tmp_path), "mcp"],
            env=os.environ.copy(),
        )
        async with Client(params, read_timeout_seconds=15) as client:
            listing = await client.list_tools()
            assert len(listing.tools) == 18
            schema = next(t.input_schema for t in listing.tools if t.name == "submit_handoff")
            assert "package" in schema["required"]
            package = schema["properties"]["package"]
            if "$ref" in package:
                package = schema["$defs"][package["$ref"].split("/")[-1]]
            assert package["type"] == "object"
            assert "context_refs" in package["properties"]
            assert "summary" in package["required"]
            assert package["additionalProperties"] is False

    asyncio.run(scenario())


def test_http_m3_operations_share_sdk_core_and_fixed_snapshots(tmp_path):
    sdk = AgentSyncClient(tmp_path)

    def call(operation, **payload):
        envelope = sdk.call(operation, **payload)
        assert envelope["ok"], envelope
        return envelope["data"]

    project = call("create_project", name="HTTP M3", root_path=str(tmp_path))
    agents = [call("register_agent", **project, name=name) for name in ("A", "B")]
    auth = [
        {
            "project_id": project["project_id"],
            "session_id": a["session_id"],
            "session_token": a["session_token"],
        }
        for a in agents
    ]

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(tmp_path, "local-secret"), client=("127.0.0.1", 123)
            ),
            base_url="http://127.0.0.1",
            headers={"Authorization": "Bearer local-secret"},
        ) as http:

            async def post(operation, **payload):
                response = await http.post("/v1/" + operation, json=payload)
                assert response.status_code == 200, response.text
                envelope = response.json()
                assert envelope["ok"], envelope
                return envelope["data"]

            context = await post(
                "publish_context",
                **auth[0],
                kind="decision",
                title="接力决定",
                content="Immutable original",
                request_id=str(uuid4()),
            )
            assert call("get_context", **auth[1], context_id=context["id"]) == context
            historical = await post("get_context", **auth[1], context_id=context["id"], version=1)
            assert historical == context
            matches = await post("search_context", **auth[1], query="接力")
            assert matches["entries"][0]["id"] == context["id"]
            task = call("create_task", **auth[0], title="HTTP relay", request_id=str(uuid4()))
            claim = call(
                "claim_task",
                **auth[0],
                task_id=task["id"],
                expected_version=task["version"],
                request_id=str(uuid4()),
            )
            package = {
                "summary": "HTTP to SDK",
                "context_refs": [{"context_id": context["id"], "version": 1}],
                "changed_files": ["never-read.txt"],
                "open_questions": ["Next step?"],
                "evidence": ["metadata only"],
            }
            handoff = await post(
                "submit_handoff",
                **auth[0],
                task_id=task["id"],
                lease_token=claim["lease_token"],
                expected_version=claim["version"],
                target_agent_id=agents[1]["agent_id"],
                package=package,
                request_id=str(uuid4()),
            )
            read = await post("get_handoff", **auth[1], handoff_id=handoff["id"])
            assert read == call("get_handoff", **auth[1], handoff_id=handoff["id"])
            assert read["contexts"][0]["content"] == "Immutable original"
            withdrawn = await post(
                "withdraw_handoff",
                **auth[0],
                handoff_id=handoff["id"],
                expected_version=handoff["task_version"],
                reason="Recheck",
                request_id=str(uuid4()),
            )
            claim = call(
                "claim_task",
                **auth[0],
                task_id=task["id"],
                expected_version=withdrawn["task_version"],
                request_id=str(uuid4()),
            )
            handoff = call(
                "submit_handoff",
                **auth[0],
                task_id=task["id"],
                lease_token=claim["lease_token"],
                expected_version=claim["version"],
                target_agent_id=agents[1]["agent_id"],
                package=package,
                request_id=str(uuid4()),
            )
            accepted = await post(
                "resolve_handoff",
                **auth[1],
                handoff_id=handoff["id"],
                expected_version=handoff["task_version"],
                accept=True,
                request_id=str(uuid4()),
            )
            claim = call(
                "claim_task",
                **auth[1],
                task_id=task["id"],
                expected_version=accepted["task_version"],
                request_id=str(uuid4()),
            )
            assert claim["status"] == "claimed"
            assert not (tmp_path / "never-read.txt").exists()

    asyncio.run(scenario())

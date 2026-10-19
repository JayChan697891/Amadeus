"""AgentSync local command line entrypoints."""
import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentsync.sdk import AgentSyncClient


def run_demo(data_dir: str | Path) -> dict[str, Any]:
    """Exercise two mock agents, review, and a fresh Core reading persisted state."""
    directory = Path(data_dir)
    if not directory.is_absolute():
        raise ValueError("Demo data directory must be absolute")
    directory.mkdir(parents=True, exist_ok=True)
    client = AgentSyncClient(directory)

    def call(operation: str, **payload: Any) -> dict[str, Any]:
        response = client.call(operation, **payload)
        if not response["ok"]:
            raise RuntimeError(f"Demo {operation} failed: {response['error']['code']}")
        return response["data"]

    project = call("create_project", name="Two mock agents", root_path=str(directory))
    credentials = {"project_id": project["project_id"], "admin_token": project["admin_token"]}
    agent_a = call("register_agent", **credentials, name="Mock implementer", capabilities=["mock"])
    agent_b = call("register_agent", **credentials, name="Mock reviewer", capabilities=["review"])
    auth_a = {"project_id": project["project_id"], "session_id": agent_a["session_id"], "session_token": agent_a["session_token"]}
    auth_b = {"project_id": project["project_id"], "session_id": agent_b["session_id"], "session_token": agent_b["session_token"]}
    task = call("create_task", **auth_a, title="Demonstrate persisted collaboration", request_id=str(uuid4()))
    claimed = call("claim_task", **auth_a, task_id=task["id"], expected_version=task["version"], request_id=str(uuid4()))
    duplicate = client.call("claim_task", **auth_b, task_id=task["id"], expected_version=claimed["version"], request_id=str(uuid4()))
    if duplicate["ok"]:
        raise RuntimeError("A second agent unexpectedly claimed an owned task")
    running = call("update_task", **auth_a, task_id=task["id"], lease_token=claimed["lease_token"], expected_version=claimed["version"], status="running", request_id=str(uuid4()))
    review = call("update_task", **auth_a, task_id=task["id"], lease_token=claimed["lease_token"], expected_version=running["version"], status="review", result="Mock implementation complete", request_id=str(uuid4()))
    completed = call("review_task", **auth_b, task_id=task["id"], expected_version=review["version"], accept=True, evidence="Mock reviewer assertion; no desktop host or code execution tested", request_id=str(uuid4()))
    fresh_client = AgentSyncClient(directory)
    persisted = fresh_client.call("list_tasks", **auth_b)
    if not persisted["ok"]:
        raise RuntimeError("Fresh Core could not read persisted tasks")
    persisted_task = next((item for item in persisted["data"]["tasks"] if item["id"] == task["id"]), None)
    if not persisted_task or persisted_task["status"] != "completed" or completed["status"] != "completed":
        raise RuntimeError("Completed task did not survive reopening the database")
    return {"ok": True, "data": {"project_id": project["project_id"], "task_id": task["id"], "status": persisted_task["status"], "duplicate_claim_rejected": True, "persistence_verified": True, "agents": 2, "scope": "local mock workflow; no desktop host compatibility verified"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentsync")
    parser.add_argument("--data-dir", default=None, help="Absolute local state directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Run official MCP stdio server")
    serve = commands.add_parser("serve", help="Run authenticated loopback HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    demo = commands.add_parser("demo", help="Run two mock agents against an explicit local database")
    demo.add_argument("--data-dir", dest="demo_data_dir")
    args = parser.parse_args(argv)
    data_dir = getattr(args, "demo_data_dir", None) or args.data_dir
    if data_dir and not Path(data_dir).is_absolute():
        parser.error("--data-dir must be absolute")
    if args.command == "demo":
        if not data_dir:
            parser.error("demo requires --data-dir PATH to avoid modifying default user state")
        print(json.dumps(run_demo(data_dir), ensure_ascii=False))
    elif args.command == "mcp":
        from agentsync.integrations.mcp import build_server
        build_server(data_dir).run()
    else:
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("serve --host must be a supported loopback host: 127.0.0.1, ::1, localhost")
        token = os.environ.get("AGENTSYNC_HTTP_TOKEN")
        if not token or not token.strip():
            parser.error("serve requires AGENTSYNC_HTTP_TOKEN")
        import uvicorn

        from agentsync.integrations.http import create_app
        uvicorn.run(create_app(data_dir, token), host=args.host, port=args.port, proxy_headers=False)
    return 0

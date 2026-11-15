"""Amadeus local command line entrypoints."""

import argparse
import asyncio
import json
import os
import sys
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
    for actor, roles in ((agent_a, ["worker"]), (agent_b, ["worker", "reviewer"])):
        granted = client.owner_call(
            "set_agent_roles",
            **credentials,
            agent_id=actor["agent_id"],
            roles=roles,
            expected_version=1,
            request_id=str(uuid4()),
        )
        if not granted["ok"]:
            raise RuntimeError("Demo owner role grant failed")
    auth_a = {
        "project_id": project["project_id"],
        "session_id": agent_a["session_id"],
        "session_token": agent_a["session_token"],
    }
    auth_b = {
        "project_id": project["project_id"],
        "session_id": agent_b["session_id"],
        "session_token": agent_b["session_token"],
    }
    task = call(
        "create_task",
        **auth_a,
        title="Demonstrate persisted collaboration",
        request_id=str(uuid4()),
    )
    claimed = call(
        "claim_task",
        **auth_a,
        task_id=task["id"],
        expected_version=task["version"],
        request_id=str(uuid4()),
    )
    duplicate = client.call(
        "claim_task",
        **auth_b,
        task_id=task["id"],
        expected_version=claimed["version"],
        request_id=str(uuid4()),
    )
    if duplicate["ok"]:
        raise RuntimeError("A second agent unexpectedly claimed an owned task")
    running = call(
        "update_task",
        **auth_a,
        task_id=task["id"],
        lease_token=claimed["lease_token"],
        expected_version=claimed["version"],
        status="running",
        request_id=str(uuid4()),
    )
    review = call(
        "update_task",
        **auth_a,
        task_id=task["id"],
        lease_token=claimed["lease_token"],
        expected_version=running["version"],
        status="review",
        result="Mock implementation complete",
        request_id=str(uuid4()),
    )
    completed = call(
        "review_task",
        **auth_b,
        task_id=task["id"],
        expected_version=review["version"],
        accept=True,
        evidence="Mock reviewer assertion; no desktop host or code execution tested",
        request_id=str(uuid4()),
    )
    fresh_client = AgentSyncClient(directory)
    persisted = fresh_client.call("list_tasks", **auth_b)
    if not persisted["ok"]:
        raise RuntimeError("Fresh Core could not read persisted tasks")
    persisted_task = next(
        (item for item in persisted["data"]["tasks"] if item["id"] == task["id"]), None
    )
    if (
        not persisted_task
        or persisted_task["status"] != "completed"
        or completed["status"] != "completed"
    ):
        raise RuntimeError("Completed task did not survive reopening the database")
    return {
        "ok": True,
        "data": {
            "project_id": project["project_id"],
            "task_id": task["id"],
            "status": persisted_task["status"],
            "duplicate_claim_rejected": True,
            "persistence_verified": True,
            "agents": 2,
            "scope": "local mock workflow; no desktop host compatibility verified",
        },
    }


def amadeus_main() -> int:
    return main(prog="amadeus")


def main(argv: list[str] | None = None, *, prog: str = "agentsync") -> int:
    arguments = sys.argv[1:] if argv is None else argv
    # Only a leading plan command takes this route; owner operations and values
    # named "plan" retain their existing command parsing.
    if arguments and arguments[0] == "plan":
        from agentsync.planning_cli import invalid_input, run_plan_cli

        return run_plan_cli() if len(arguments) == 1 else invalid_input()
    if arguments and arguments[0] == "plan-retry":
        from agentsync.planning_cli import invalid_input, run_retry_plan_cli

        return run_retry_plan_cli() if len(arguments) == 1 else invalid_input()
    if arguments and arguments[0] in {"usage", "model-usage"}:
        from agentsync.usage_cli import invalid_input, run_usage_cli

        return (
            run_usage_cli(arguments[2], model=arguments[0] == "model-usage")
            if len(arguments) == 3 and arguments[1] == "--project-id"
            else invalid_input()
        )
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--data-dir", default=None, help="Absolute local state directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Run official MCP stdio server")
    commands.add_parser("plan", help="Print offline dispatch advice from bounded stdin JSON")
    commands.add_parser("plan-retry", help="Print offline retry advice from bounded stdin JSON")
    usage = commands.add_parser("usage", help="Summarize a bounded stdin usage checkpoint offline")
    usage.add_argument("--project-id")
    model_usage = commands.add_parser(
        "model-usage", help="Summarize a bounded stdin model meter snapshot"
    )
    model_usage.add_argument("--project-id")
    owner = commands.add_parser(
        "owner", help="Owner operation; read credentials and payload JSON from stdin"
    )
    owner.add_argument("operation")
    relay_status = commands.add_parser(
        "relay-status", help="Inspect a local relay journal with project owner credentials on stdin"
    )
    relay_reconcile = commands.add_parser(
        "relay-reconcile", help="Reconcile one saved local wave using owner and session credentials"
    )
    for relay_command in (relay_status, relay_reconcile):
        relay_command.add_argument("--scratch-root", type=Path, required=True)
        relay_command.add_argument("--receipts", type=Path, required=True)
    relay_reconcile.add_argument("wave_id")
    relay_view = relay_status.add_mutually_exclusive_group()
    relay_view.add_argument("--history", action="store_true")
    relay_view.add_argument("--task-id", help="Show saved attempt observations for this task")
    relay_status.add_argument("--limit", type=int, default=16)
    relay_status.add_argument("--before")
    serve = commands.add_parser("serve", help="Run authenticated loopback HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    demo = commands.add_parser(
        "demo", help="Run two mock agents against an explicit local database"
    )
    demo.add_argument("--data-dir", dest="demo_data_dir")
    demo_mode = demo.add_mutually_exclusive_group()
    demo_mode.add_argument(
        "--workflow",
        action="store_true",
        help="Run a disposable fixed Mock workflow in the existing scratch parent",
    )
    demo_mode.add_argument(
        "--durable",
        action="store_true",
        help="Run a recoverable Mock handoff in a new local data directory",
    )
    mock_workflow = commands.add_parser(
        "mock-workflow", help="Run a disposable Mock task graph from bounded stdin JSON"
    )
    mock_workflow.add_argument("--scratch-parent", type=Path, required=True)
    workflow = commands.add_parser("workflow", help="Operate an owner-only durable Mock workflow")
    workflow.add_argument("operation", choices=("start", "resume", "status", "cancel"))
    args = parser.parse_args(argv)
    if args.command in {"plan", "plan-retry"}:
        from agentsync.planning_cli import invalid_input

        return invalid_input()
    if args.command in {"usage", "model-usage"}:
        from agentsync.usage_cli import invalid_input

        return invalid_input()
    if args.command == "mock-workflow":
        if args.data_dir is not None:
            parser.error("mock-workflow requires --scratch-parent instead of --data-dir")
        from agentsync.mock_workflow_cli import run_mock_workflow_cli

        return run_mock_workflow_cli(args.scratch_parent)
    data_dir = getattr(args, "demo_data_dir", None) or args.data_dir
    if data_dir and not Path(data_dir).is_absolute():
        parser.error("--data-dir must be absolute")
    if args.command == "workflow":
        if not data_dir:
            parser.error("workflow requires an explicit --data-dir")
        from agentsync.mock_workflow_cli import read_workflow_document

        try:
            payload = read_workflow_document()
            if type(payload) is not dict or {"operation", "self"}.intersection(payload):
                raise ValueError
        except (ValueError, RecursionError, OverflowError):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "validation_error",
                            "message": "Expected bounded workflow input.",
                        },
                    }
                )
            )
            return 1
        response = AgentSyncClient(data_dir).owner_call(
            f"{args.operation}_mock_workflow", **payload
        )
        print(json.dumps(response, ensure_ascii=True, allow_nan=False))
        return 0 if response["ok"] else 1
    if args.command in {"relay-status", "relay-reconcile"}:
        if not data_dir:
            parser.error(f"{args.command} requires an explicit --data-dir")
        if (
            args.command == "relay-status"
            and not args.history
            and (args.before is not None or args.limit != 16)
        ):
            parser.error("relay-status paging options require --history")
        from agentsync.relay_status_cli import run_relay_cli

        return run_relay_cli(
            Path(data_dir),
            args.scratch_root,
            args.receipts,
            history=getattr(args, "history", False),
            limit=getattr(args, "limit", 16),
            before=getattr(args, "before", None),
            task_id=getattr(args, "task_id", None),
            wave_id=getattr(args, "wave_id", None),
        )
    if args.command == "owner":
        try:
            raw = sys.stdin.read(65537)
            if len(raw) > 65536 or len(raw.encode("utf-8")) > 65536:
                raise ValueError("input exceeds limit")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or {"operation", "self"}.intersection(payload):
                raise ValueError("object required")
        except (ValueError, UnicodeError, RecursionError):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "validation_error",
                            "message": "stdin must contain a bounded JSON object with valid fields",
                        },
                    }
                )
            )
            return 1
        response = AgentSyncClient(data_dir).owner_call(args.operation, **payload)
        print(json.dumps(response, ensure_ascii=False))
        return 0 if response["ok"] else 1
    elif args.command == "demo":
        if not data_dir:
            parser.error("demo requires --data-dir PATH to avoid modifying default user state")
        if args.durable:
            from agentsync.durable_demo import DurableDemoError, run_durable_demo

            try:
                result = run_durable_demo(Path(data_dir))
            except FileExistsError:
                parser.error("demo --durable requires a new --data-dir")
            except DurableDemoError as error:
                parser.exit(1, f"{prog}: {error}\n")
        elif args.workflow:
            from agentsync.mock_workflow import run_mock_workflow_demo

            result = asyncio.run(run_mock_workflow_demo(Path(data_dir)))
        else:
            result = run_demo(data_dir)
        print(json.dumps(result, ensure_ascii=False))
    elif args.command == "mcp":
        from agentsync.integrations.mcp import build_server

        build_server(data_dir).run()
    else:
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error(
                "serve --host must be a supported loopback host: 127.0.0.1, ::1, localhost"
            )
        token = os.environ.get("AGENTSYNC_HTTP_TOKEN")
        if not token or not token.strip():
            parser.error("serve requires AGENTSYNC_HTTP_TOKEN")
        import uvicorn

        from agentsync.integrations.http import create_app

        uvicorn.run(
            create_app(data_dir, token), host=args.host, port=args.port, proxy_headers=False
        )
    return 0

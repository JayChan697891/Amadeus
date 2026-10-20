"""Real Python MCP client/server process handoff; no model or desktop host involved.

Run: python examples/m3_handoff.py --data-dir <a disposable directory>
Credentials travel only through child-process standard input/output, never a file.
Package paths, commands, and evidence are descriptive metadata, never executed.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def worker(job: dict[str, Any]) -> dict[str, Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentsync", "--data-dir", job["data_dir"], "mcp"],
        env=os.environ.copy(),
    )
    async with Client(params, read_timeout_seconds=30) as client:

        async def call(operation: str, **payload: Any) -> dict[str, Any]:
            response = await client.call_tool(operation, payload)
            envelope = response.structured_content or json.loads(response.content[0].text)
            require(not response.is_error and envelope["ok"], f"{operation}: {envelope}")
            return envelope["data"]

        if job["phase"] == "prepare":
            project = await call(
                "create_project", name="M3 process relay", root_path=job["data_dir"]
            )
            agents = [await call("register_agent", **project, name=name) for name in ("A", "B")]
            auth = [
                {
                    "project_id": project["project_id"],
                    "session_id": agent["session_id"],
                    "session_token": agent["session_token"],
                }
                for agent in agents
            ]
            context = await call(
                "publish_context",
                **auth[0],
                kind="requirement",
                title="接力要求",
                content="Preserve the pinned requirement",
                request_id=str(uuid4()),
            )
            task = await call(
                "create_task", **auth[0], title="Process relay", request_id=str(uuid4())
            )
            claim = await call(
                "claim_task",
                **auth[0],
                task_id=task["id"],
                expected_version=task["version"],
                request_id=str(uuid4()),
            )
            handoff = await call(
                "submit_handoff",
                **auth[0],
                task_id=task["id"],
                lease_token=claim["lease_token"],
                expected_version=claim["version"],
                target_agent_id=agents[1]["agent_id"],
                request_id=str(uuid4()),
                package={
                    "summary": "Continue from fixed requirement revision 1",
                    "completed_work": "Prepared the requirement and task",
                    "changed_files": ["metadata-only/example.txt"],
                    "open_questions": ["Should the next batch add a UI?"],
                    "evidence": ["Descriptive assertion; no file access or commands"],
                    "context_refs": [{"context_id": context["id"], "version": 1}],
                },
            )
            await call(
                "publish_context",
                **auth[0],
                kind="requirement",
                title="接力要求",
                content="Later requirement revision",
                context_id=context["id"],
                expected_version=1,
                request_id=str(uuid4()),
            )
            return {
                "auth": auth,
                "task_id": task["id"],
                "handoff_id": handoff["id"],
                "context_id": context["id"],
                "client_pid": os.getpid(),
            }

        state = job["state"]
        if job["phase"] == "continue":
            auth_b = state["auth"][1]
            handoff = await call("get_handoff", **auth_b, handoff_id=state["handoff_id"])
            require(handoff["contexts"][0]["version"] == 1, "Handoff snapshot drifted")
            context = await call("get_context", **auth_b, context_id=state["context_id"])
            require(context["version"] == 2, "Latest context was not updated")
            matches = await call("search_context", **auth_b, query="接力")
            require(matches["entries"][0]["version"] == 2, "Search returned old revision")
            accepted = await call(
                "resolve_handoff",
                **auth_b,
                handoff_id=handoff["id"],
                expected_version=handoff["task_version"],
                accept=True,
                request_id=str(uuid4()),
            )
            claim = await call(
                "claim_task",
                **auth_b,
                task_id=state["task_id"],
                expected_version=accepted["task_version"],
                request_id=str(uuid4()),
            )
            version = claim["version"]
            for status in ("running", "review"):
                updated = await call(
                    "update_task",
                    **auth_b,
                    task_id=state["task_id"],
                    lease_token=claim["lease_token"],
                    expected_version=version,
                    status=status,
                    result="Continued against pinned revision 1",
                    request_id=str(uuid4()),
                )
                version = updated["version"]
            return {
                "version": version,
                "client_pid": os.getpid(),
                "pinned_version": 1,
                "latest_version": context["version"],
            }

        require(job["phase"] == "review", "Unknown phase")
        reviewed = await call(
            "review_task",
            **state["auth"][0],
            task_id=state["task_id"],
            expected_version=job["version"],
            accept=True,
            evidence="A reviewed B's recorded relay result; protocol demonstration only",
            request_id=str(uuid4()),
        )
        return {"status": reviewed["status"], "client_pid": os.getpid()}


def launch(data_dir: str, phase: str, **payload: Any) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker"],
        input=json.dumps({"data_dir": data_dir, "phase": phase, **payload}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=90,
    )
    require(process.returncode == 0, f"Client process failed: {process.stderr}")
    return json.loads(process.stdout)


def run(data_dir: str) -> dict[str, Any]:
    state = launch(data_dir, "prepare")
    continued = launch(data_dir, "continue", state=state)
    reviewed = launch(data_dir, "review", state=state, version=continued["version"])
    pids = [state["client_pid"], continued["client_pid"], reviewed["client_pid"]]
    require(len(set(pids)) == 3, "Expected separate client processes")
    require(reviewed["status"] == "completed", "Independent review failed")
    return {
        "status": reviewed["status"],
        "project_id": state["auth"][0]["project_id"],
        "task_id": state["task_id"],
        "client_process_ids": pids,
        "pinned_context_version": continued["pinned_version"],
        "latest_context_version": continued["latest_version"],
        "evidence_scope": "Real Python MCP client/server processes; no desktop host or model",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--data-dir")
    args = parser.parse_args()
    if args.worker:
        output = asyncio.run(worker(json.load(sys.stdin)))
    else:
        if not args.data_dir:
            parser.error("--data-dir is required")
        output = run(str(Path(args.data_dir).resolve()))
    print(json.dumps(output, ensure_ascii=True))

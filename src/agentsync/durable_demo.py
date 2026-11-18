"""A fixed offline demo using the existing durable workflow and owner APIs."""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agentsync.sdk import AgentSyncClient

_RETRY_SECONDS = 3
_WORKFLOW_ENTRY = """\
from pathlib import Path
import sys
import agentsync
from agentsync.cli import main
if Path(agentsync.__file__).resolve() != Path(sys.argv[1]):
    raise SystemExit(2)
raise SystemExit(main(sys.argv[2:]))
"""


class DurableDemoError(RuntimeError):
    """A display-safe diagnostic for the scripted demo."""


def _data(response: dict[str, Any], operation: str) -> dict[str, Any]:
    if response["ok"] is not True:
        raise DurableDemoError(f"The durable Mock demo could not {operation}.")
    return response["data"]


def _workflow(directory: Path, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = Path(__file__).resolve().with_name("__init__.py")
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                _WORKFLOW_ENTRY,
                str(package),
                "--data-dir",
                str(directory),
                "workflow",
                operation,
            ],
            input=json.dumps(payload),
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DurableDemoError(
            f"The isolated workflow {operation} process could not finish."
        ) from None
    if process.returncode != 0:
        raise DurableDemoError(f"The isolated workflow {operation} process did not succeed.")
    try:
        response = json.loads(process.stdout)
    except (ValueError, RecursionError):
        raise DurableDemoError(f"The isolated workflow {operation} did not return JSON.") from None
    return _data(response, operation)


def run_durable_demo(directory: Path) -> dict[str, Any]:
    """Show new processes reopening the same workflow across a persisted retry."""
    try:
        directory.mkdir(mode=0o700, parents=True)
    except FileExistsError:
        raise
    except OSError:
        raise DurableDemoError(
            "The durable Mock demo could not create its data directory."
        ) from None
    directory = directory.resolve()
    client = AgentSyncClient(directory)
    owner = _data(
        client.call("create_project", name="Durable Mock handoff", root_path=str(directory)),
        "create its dedicated project",
    )
    started = _workflow(
        directory,
        "start",
        owner
        | {
            "request_id": "demo-start",
            "config": {
                "tasks": [
                    {
                        "label": "build",
                        "priority": 1,
                        "capability": "build",
                        "first_retry_after_seconds": _RETRY_SECONDS,
                        "handoff_on_success": True,
                    }
                ],
                "workers": [
                    {"label": name, "capabilities": ["build"]}
                    for name in ("producer", "recipient", "reviewer")
                ],
                "budget": {
                    "steps": 3,
                    "calls": 3,
                    "requested_output": 96,
                    "estimated_tokens": 288,
                    "estimated_cost": 2880,
                    "concurrency": 1,
                },
                "max_attempts_per_task": 3,
                "deadline_seconds": 60,
            },
        },
    )
    observed = _workflow(directory, "status", owner)
    if (
        started["state"] != "waiting"
        or observed != started
        or len(observed["tasks"]) != 1
        or [attempt["state"] for attempt in observed["attempts"]] != ["failed", "scheduled"]
    ):
        raise DurableDemoError("The saved Mock retry did not reopen as expected.")
    task_id = observed["tasks"][0]["id"]
    retry_at = observed["attempts"][1]["retry_at"]
    wait = max(0.0, retry_at - time.time())
    if wait > _RETRY_SECONDS:
        raise DurableDemoError("The saved retry is outside the demo's retry window.")
    time.sleep(wait + 0.05)
    finished = _workflow(
        directory,
        "resume",
        owner
        | {
            "request_id": "demo-resume",
            "expected_version": observed["version"],
        },
    )
    if (
        finished["state"] != "completed"
        or finished["run_id"] != observed["run_id"]
        or [(task["id"], task["status"]) for task in finished["tasks"]] != [(task_id, "completed")]
        or [attempt["state"] for attempt in finished["attempts"]]
        != ["failed", "succeeded", "succeeded"]
        or finished["simulation_only"] is not True
        or finished["verification"] != "unverified"
    ):
        raise DurableDemoError(
            "The resumed Mock task did not reach its expected simulated outcome."
        )

    handoffs = _data(
        client.owner_call("list_handoffs", **owner, task_id=task_id, status="accepted", limit=2),
        "read its accepted handoff",
    )["handoffs"]
    events = _data(
        client.owner_call("list_audit", **owner, limit=100), "read its reviewer observation"
    )
    reviews = [
        event["actor_id"]
        for event in events["events"]
        if event["operation"] == "review_task"
        and event["outcome"] == "success"
        and event["target_id"] == task_id
    ]
    if len(handoffs) != 1 or len(reviews) != 1 or events["has_more"]:
        raise DurableDemoError(
            "The durable Mock demo did not record exactly one handoff and review."
        )
    handoff = handoffs[0]
    if reviews[0] in {handoff["sender_agent_id"], handoff["recipient_agent_id"]}:
        raise DurableDemoError("The Mock reviewer was also a handoff participant.")

    return {
        "ok": True,
        "data": {
            "data_dir": str(directory),
            "project_id": owner["project_id"],
            "run_id": finished["run_id"],
            "task_id": task_id,
            "task_status": "completed",
            "reopened_state": "waiting",
            "resumed_in_fresh_process": True,
            "attempts": [attempt["state"] for attempt in finished["attempts"]],
            "handoff": {"id": handoff["id"], "status": handoff["status"]},
            "peer_review": {
                "distinct_from_handoff_participants": True,
                "evidence": "simulation_only/unverified",
            },
            "simulation_only": True,
            "verification": "unverified",
        },
    }

"""Create a dedicated project, then reopen a simulated workflow through the CLI.

Run with an installed Amadeus Python environment and a new absolute directory.
The owner credential stays in this process and each child's stdin. A real host
must keep it in its own private credential store to resume after this host exits.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from agentsync.sdk import AgentSyncClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    args = parser.parse_args()
    directory = args.data_directory
    if not directory.is_absolute():
        parser.error("Use an absolute directory.")
    try:
        directory.mkdir(mode=0o700, parents=True)
    except FileExistsError:
        parser.error("Use a new directory; existing state is never reused by this example.")
    directory = directory.resolve()

    # Project creation is a regular SDK operation, not an owner operation.
    response = AgentSyncClient(directory).call(
        "create_project", name="My persistent workflow", root_path=str(directory)
    )
    if not response["ok"]:
        raise SystemExit("Project creation failed.")
    owner = response["data"]

    def workflow(operation, **fields):
        child = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "agentsync",
                "--data-dir",
                str(directory),
                "workflow",
                operation,
            ],
            input=json.dumps(owner | fields),
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if child.returncode:
            raise SystemExit(f"Workflow {operation} failed; no retry was attempted.")
        result = json.loads(child.stdout)
        if not result["ok"]:
            raise SystemExit(f"Workflow {operation} was rejected.")
        data = result["data"]
        print(
            json.dumps(
                {
                    "operation": operation,
                    "run_id": data["run_id"],
                    "state": data["state"],
                    "version": data["version"],
                    "simulation_only": data["simulation_only"],
                    "verification": data["verification"],
                }
            )
        )
        return data

    started = workflow(
        "start",
        request_id="example-start",
        config={
            "tasks": [
                {
                    "label": "build",
                    "priority": 1,
                    "capability": "build",
                    "first_retry_after_seconds": 3,
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
    )
    observed = workflow("status")  # Another process reads the same saved run.
    if observed != started or observed["state"] != "waiting":
        raise SystemExit("The saved retry did not reopen as expected.")
    retry_at = next(row["retry_at"] for row in observed["attempts"] if row["state"] == "scheduled")
    wait = max(0, retry_at - time.time())
    if wait > 3:
        raise SystemExit("The saved retry is outside the example's three-second window.")
    time.sleep(wait + 0.05)
    finished = workflow("resume", request_id="example-resume", expected_version=observed["version"])
    if (
        finished["run_id"] != started["run_id"]
        or finished["state"] != "completed"
        or finished["simulation_only"] is not True
        or finished["verification"] != "unverified"
    ):
        raise SystemExit("The simulated workflow did not finish as expected.")


if __name__ == "__main__":
    main()

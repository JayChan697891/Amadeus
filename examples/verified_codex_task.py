"""Run one owner-approved Linux Codex task through verification and handoff.

Requires an existing project in ROOT/core, whose clean Git repository is inside
ROOT. The owner retains its project ID/token. A caller-prepared private Codex
home and existing Docker image are required. Tasks implement root solution.py
as a JSON-lines program. Cases are [{"input": ..., "expected": ...}].

Example (use actual absolute paths and a full existing image ID):
python -I -B examples/verified_codex_task.py --root /path/to/project \
  --project-id PROJECT --task /path/to/task.txt --cases /path/to/cases.json \
  --codex /path/to/codex --codex-sha256 SHA256 --codex-version VERSION \
  --codex-home /private/home \
  --image-id sha256:IMAGE_SHA256

Each launch and candidate effect needs its own exact terminal approval. This
single attempt stops on denial, failure or unknown state. Inspect saved state
through examples/recover_relay.py and the documented owner APIs before acting.
The example does not manage or remove the caller's prepared login home.
"""

import argparse
import asyncio
import getpass
import hashlib
import json
import os
import re
import sys
import time
import warnings
from dataclasses import asdict
from pathlib import Path

from agentsync.adapters.approved_launch import LaunchConsent, digest
from agentsync.adapters.codex_invocation import CodexHostProfile
from agentsync.controlled_relay import CodexProposalInput, RelayActor, RelayReviewer
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import HandoffReceiver, ProposalHandoffRequest
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verified_proposal_flow import VerifiedProposalFlow


def prompt(label):
    if not sys.stdin.isatty():
        raise ValueError("secure_terminal_required")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(label)


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def inputs(args):
    instruction = args.task.read_bytes()
    cases = args.cases.read_bytes()
    if not 0 < len(instruction) <= 1000 or len(cases) > 32768:
        raise ValueError("input_limit")
    goal = instruction.decode("utf-8").strip()
    if not goal:
        raise ValueError("empty_task")
    examples = json.loads(cases)
    if (
        not isinstance(examples, list)
        or not examples
        or any(
            not isinstance(case, dict) or set(case) != {"input", "expected"} for case in examples
        )
    ):
        raise ValueError("invalid_cases")
    profile = DockerProfile(
        args.image_id, tuple(JsonCase(case["input"], case["expected"]) for case in examples)
    )
    return goal, examples, profile


async def run(args, owner_token, goal, cases, profile):
    root = args.root.resolve(strict=True)
    database = root / "core/agentsync.db"
    if not database.is_file() or database.resolve(strict=True) != database:
        raise ValueError("existing_project_required")
    core = Core(root / "core")
    owner = {"project_id": args.project_id, "admin_token": owner_token}
    core.execute_owner("list_members", {**owner, "limit": 1})
    output = root / "terminal-run"
    output.mkdir(mode=0o700)
    receipts = output / "receipts"
    receipts.mkdir()
    home = output / "home"
    home.mkdir()
    secrets = [owner_token]

    def save(name, value):
        text = json.dumps(value, ensure_ascii=True, allow_nan=False)
        if any(secret in text for secret in secrets):
            raise ValueError("private_value_in_report")
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        emit(value)

    save(
        "entry.json",
        {
            "project_id": args.project_id,
            "model_call_limit": 2,
            "automatic_retry": False,
            "receipts": str(receipts),
        },
    )
    identities = {}
    for name in ("producer", "stager", "reviewer", "receiver"):
        actor = core.execute("register_agent", {**owner, "name": "Terminal " + name})
        secrets.append(actor["session_token"])
        core.execute_owner(
            "set_agent_roles",
            {
                **owner,
                "agent_id": actor["agent_id"],
                "roles": ["reviewer" if name == "reviewer" else "worker"],
                "expected_version": 1,
                "request_id": "terminal-roles-" + name,
            },
        )
        identities[name] = actor

    def auth(name):
        actor = identities[name]
        return {
            "project_id": args.project_id,
            "session_id": actor["session_id"],
            "session_token": actor["session_token"],
        }

    registered = Path(core.execute("get_project_state", auth("producer"))["project"]["root_path"])
    if not registered.resolve(strict=True).is_relative_to(root):
        raise ValueError("project_outside_scratch")
    task = core.execute(
        "create_task",
        {
            **auth("producer"),
            "title": "Owner terminal task",
            "request_id": "terminal-producer-task",
        },
    )
    snapshot = core.execute(
        "capture_repository", {**auth("producer"), "request_id": "terminal-snapshot"}
    )
    tree = core.execute(
        "create_worktree",
        {
            **auth("producer"),
            "task_id": task["id"],
            "snapshot_id": snapshot["snapshot_id"],
            "request_id": "terminal-producer-tree",
        },
    )
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "CODEX_HOME": str(args.codex_home.resolve(strict=True)),
        "TMP": str(home),
    }
    launches = 0

    async def authorize(review):
        nonlocal launches
        if launches >= 2:
            raise ValueError("model_call_limit")
        launches += 1
        plan = review.plan
        save(
            f"launch-{launches}-plan.json",
            {
                "client": review.client,
                "plan_sha256": review.plan_sha256,
                "task": asdict(review.task),
                "argv": plan.argv,
                "cwd": str(plan.cwd),
                "stdin_text": plan.stdin_text,
                "client_version": plan.expected_cli_version,
                "binary_sha256": plan.binary_sha256,
                "timeout_seconds": plan.timeout_seconds,
                "output_limit": plan.output_limit,
                "environment_sha256": digest(sorted(plan.child_env().items())),
                "owner_confirmation": "Independently confirm prepared login, subscription cost and isolation for this exact environment.",
            },
        )
        if (
            prompt("Confirm subscription-only cost and effective isolation by typing CONFIRM: ")
            != "CONFIRM"
        ):
            return None
        if prompt("Approve this launch by typing its plan SHA-256: ") != review.plan_sha256:
            return None
        save(f"launch-{launches}-approved.json", {"plan_sha256": review.plan_sha256})
        return LaunchConsent(
            "terminal-launch-" + str(launches), review.plan_sha256, time.time() + 30, True, True
        )

    def actor(name, workspace):
        identity = identities[name]
        return RelayActor(
            identity["agent_id"],
            identity["session_token"],
            CodexHostProfile(
                args.project_id,
                identity["session_id"],
                args.codex,
                Path(workspace["path"]),
                args.codex_sha256,
                expected_cli_version=args.codex_version,
                linux_readonly=True,
                max_timeout_seconds=90,
            ),
            workspace["worktree_id"],
            workspace["head_sha"],
            environment,
            authorize,
        )

    producer = actor("producer", tree)
    receiver = identities["receiver"]
    handoff = ProposalHandoffRequest(
        task["id"],
        HandoffReceiver(
            args.project_id, receiver["agent_id"], receiver["session_id"], receiver["session_token"]
        ),
        "terminal-handoff",
        "Read the independently verified proposal and explain its behavior in review.md. "
        "Do not use tools, run code, or change files.",
    )

    async def decide(stage, value, key):
        display = {"stage": stage, "value": value, "image_id": profile.image_id, "cases": cases}
        if stage == "staging":
            pin = value["plan"]
            context = core.execute(
                "get_context",
                {
                    **auth("producer"),
                    "context_id": pin["context_id"],
                    "version": pin["context_version"],
                },
            )
            if hashlib.sha256(context["content"].encode()).hexdigest() != pin["content_sha256"]:
                raise ValueError("proposal_changed")
            display["proposal_files"] = json.loads(context["content"])["files"]
        save(stage + "-plan.json", display)
        if prompt("Approve " + stage + " by typing its exact SHA-256: ") != value[key]:
            return None
        save(stage + "-approved.json", {key: value[key]})
        return value[key]

    def reviewer(name):
        identity = identities[name]
        return RelayReviewer(args.project_id, identity["session_id"], identity["session_token"])

    instruction = goal + (
        "\nReturn solution.py as a Python JSON-lines program: read one JSON value per stdin line, "
        "write one JSON result per stdout line. No extra output. Do not use tools, run code, or change files."
    )
    try:
        result = await VerifiedProposalFlow(core, root, receipts).run_once(
            producer,
            CodexProposalInput(
                task["id"], task["version"], instruction, ("solution.py",), submit_for_review=True
            ),
            handoff,
            admin_token=owner_token,
            stager=reviewer("stager"),
            reviewer=reviewer("reviewer"),
            profile=profile,
            approve_staging=lambda value: decide("staging", value, "plan_sha256"),
            approve_execution=lambda value: decide("execution", value, "metadata_sha256"),
            approve_completion=lambda value: decide("completion", value, "decision_sha256"),
            build_receiver=lambda who, workspace: actor("receiver", asdict(workspace)),
        )
        tasks = core.execute("list_tasks", auth("reviewer"))["tasks"]
        save(
            "result.json",
            {
                "flow": asdict(result),
                "tasks": [
                    {key: row[key] for key in ("id", "status", "version", "task_verification")}
                    for row in tasks
                ],
                "launch_approvals": launches,
                "receipts": str(receipts),
                "recovery": "Use examples/recover_relay.py with the existing owner credentials; inspect before another action.",
            },
        )
        states = {row["id"]: (row["status"], row["task_verification"]) for row in tasks}
        handed = result.handoff
        succeeded = (
            result.state == "handoff"
            and handed is not None
            and handed.state == "resolved"
            and states[task["id"]] == ("completed", "verified")
            and states.get(handed.task_id) == ("review", "unverified")
            and handed.wave is not None
            and handed.wave.state == "resolved"
            and [(row.task_id, row.state) for row in handed.wave.tasks]
            == [(handed.task_id, "ready_for_review")]
        )
        return 0 if succeeded else 1
    except (Exception, asyncio.CancelledError):
        save(
            "stopped.json",
            {
                "outcome": "unknown; inspect receipts and owner APIs before acting",
                "task_id": task["id"],
                "automatic_retry": False,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "task", "cases", "codex", "codex-home"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("project-id", "codex-sha256", "codex-version", "image-id"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or not __debug__:
        parser.error("This example requires Linux and the existing local Docker verifier.")
    if any(
        not getattr(args, name).is_absolute()
        for name in ("root", "task", "cases", "codex", "codex_home")
    ):
        parser.error("Use absolute paths.")
    if re.fullmatch(r"[0-9a-f]{64}", args.codex_sha256) is None:
        parser.error("Use the full reviewed Codex binary SHA-256.")
    os.umask(0o077)
    try:
        goal, cases, profile = inputs(args)
        token = prompt("Existing project owner token: ")
        return asyncio.run(run(args, token, goal, cases, profile))
    except (Exception, KeyboardInterrupt) as error:
        emit(
            {
                "error_code": error.code
                if isinstance(error, AgentSyncError)
                else type(error).__name__,
                "automatic_retry": False,
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Continue one confirmed-failed Codex task from its authentic saved checkpoint.

Linux only; requires the existing ROOT/core and exact original receipts/scratch
root, a caller-prepared private Codex home, and an owner token entered privately.
Keep this file beside verified_codex_task.py, whose terminal approval is reused.
One new receiver is prepared only after PREPARE; its credentials remain in memory.
The continuation plan and real launch require separate exact approvals. This is
one attempt, ending at review/unverified, with no candidate execution or retry.
Running again reads owner status only, including after a pre-dispatch failure.
The caller remains responsible for its prepared login and parent-safe cleanup.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import runpy
import stat
import sys
from dataclasses import asdict
from pathlib import Path

from agentsync.adapters.approved_launch import digest
from agentsync.adapters.codex_invocation import MAX_BINARY_BYTES, CodexHostProfile
from agentsync.continuation import ContinuationRequest, OwnerContinuation
from agentsync.controlled_relay import ControlledRelay, RelayActor
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import HandoffReceiver

_terminal = runpy.run_path(str(Path(__file__).with_name("verified_codex_task.py")))
prompt, prompt_async, emit, approve_launch = (
    _terminal[name] for name in ("prompt", "prompt_async", "emit", "approve_launch")
)


def succeeded(result):
    wave = result.get("wave")
    return (
        result.get("state") == "resolved"
        and result.get("task_status") == "review"
        and result.get("verification") == "unverified"
        and wave is not None
        and [(row["task_id"], row["state"]) for row in wave["tasks"]]
        == [(result["task_id"], "ready_for_review")]
    )


async def run(args, owner_token):
    root = args.root.resolve(strict=True)
    database = root / "core/agentsync.db"
    if not database.is_file() or database.resolve(strict=True) != database:
        raise ValueError("existing_project_required")
    receipts = args.receipts.resolve(strict=True)
    if not receipts.is_dir() or not receipts.is_relative_to(root):
        raise ValueError("existing_receipts_required")
    core = Core(root / "core")
    owner = {"project_id": args.project_id, "admin_token": owner_token}
    relay = ControlledRelay(core, root, receipts)
    observed = relay.owner_observe_codex_checkpoint(
        args.project_id, args.task_id, admin_token=owner_token
    )
    flow = OwnerContinuation(core, root, receipts)
    output = root / ("continue-" + digest([args.project_id, args.task_id]))
    # Status precedes pinning: after admission the original source is failed.
    # Partial directories also fence all new effects; never recreate a receiver.
    if output.exists():
        if not output.is_dir() or output.resolve(strict=True) != output:
            raise ValueError("physical_output_required")
        entry_path = output / "entry.json"
        if not entry_path.is_file() or entry_path.resolve(strict=True) != entry_path:
            raise ValueError("physical_entry_required")
        with entry_path.open("rb") as stream:
            encoded = stream.read(65537)
        if len(encoded) > 65536:
            raise ValueError("entry_limit")
        entry = json.loads(encoded)
        if (entry["project_id"], entry["source_task_id"]) != (args.project_id, args.task_id):
            raise ValueError("continuation_entry_mismatch")
        status = flow.status(args.project_id, entry["launch_sha256"], admin_token=owner_token)
        emit({"continuation": status, "status_only": True, "automatic_retry": False})
        return 0 if succeeded(status) else 1
    if observed["state"] != "saved":
        raise ValueError("saved_checkpoint_required")
    pin = flow.pin_failed_progress(
        args.project_id,
        args.task_id,
        context_id=observed["context_id"],
        context_version=observed["context_version"],
        content_sha256=observed["content_sha256"],
        admin_token=owner_token,
    )
    if args.codex_version != "0.167.0-alpha.3.2":
        raise ValueError("unsupported_linux_profile")
    binary_stat = args.codex.lstat()
    if not stat.S_ISREG(binary_stat.st_mode) or binary_stat.st_size > MAX_BINARY_BYTES:
        raise ValueError("binary_boundary")
    with args.codex.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != args.codex_sha256:
            raise ValueError("binary_pin_mismatch")
    codex_home = args.codex_home.resolve(strict=True)
    if not codex_home.is_dir():
        raise ValueError("private_home_required")
    # No identity or model effects have occurred. Pinning checks Core publication,
    # protocol receipts and the original dispatch-pinned, positively ended failure.
    with args.instruction.open("rb") as stream:
        instruction = stream.read(1001)
    if not 0 < len(instruction) <= 1000 or not instruction.decode("utf-8").strip():
        raise ValueError("input_limit")
    emit({"source": asdict(pin), "checkpoint": observed, "model_call_limit": 1})
    if await prompt_async("Prepare one new independent receiver by typing PREPARE: ") != "PREPARE":
        return 1
    output.mkdir(mode=0o700)
    secrets = [owner_token]

    def checked_text(value):
        text = json.dumps(value, ensure_ascii=True, allow_nan=False)
        if any(secret in text for secret in secrets):
            raise ValueError("private_value_in_report")
        return text

    def save(name, value):
        text = checked_text(value)
        descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        emit(value)

    save(
        "entry.json",
        {
            "project_id": args.project_id,
            "source_task_id": args.task_id,
            "launch_sha256": pin.launch_sha256,
            "source": asdict(pin),
            "model_call_limit": 1,
            "automatic_retry": False,
        },
    )
    try:
        identity = core.execute(
            "register_agent", {**owner, "name": "Terminal continuation receiver"}
        )
        secrets.append(identity["session_token"])
        core.execute_owner(
            "set_agent_roles",
            {
                **owner,
                "agent_id": identity["agent_id"],
                "roles": ["worker"],
                "expected_version": 1,
                "request_id": "terminal-continuation-" + pin.launch_sha256,
            },
        )
        receiver = HandoffReceiver(
            args.project_id, identity["agent_id"], identity["session_id"], identity["session_token"]
        )
        context = core.execute(
            "get_context",
            {
                **receiver.authentication(),
                "context_id": pin.context_id,
                "version": pin.context_version,
            },
        )
        if hashlib.sha256(context["content"].encode("utf-8")).hexdigest() != pin.content_sha256:
            raise ValueError("checkpoint_changed")
        files = json.loads(context["content"])["files"]
        registered = Path(
            core.execute("get_project_state", receiver.authentication())["project"]["root_path"]
        )
        if not registered.resolve(strict=True).is_relative_to(root):
            raise ValueError("project_outside_scratch")
        request = ContinuationRequest(
            receiver,
            pin,
            instruction.decode("utf-8").strip()
            + "\nContinue only the pinned allowed paths. Do not use tools, run code, or change files.",
            tuple(item["path"] for item in files),
            execution_seconds=90,
        )
        preview = flow.preview(request, admin_token=owner_token)
        display = {"proposal_files": files, "instruction": request.instruction}
        checked_text(display)
        emit(display)
        save("continuation-plan.json", preview)
        if (
            await prompt_async("Approve continuation by typing its exact plan SHA-256: ")
            != preview["plan_sha256"]
        ):
            return 1
        save("continuation-approved.json", {"plan_sha256": preview["plan_sha256"]})
        home = output / "home"
        home.mkdir(mode=0o700)
        launches = 0

        async def authorize(review):
            nonlocal launches
            if launches:
                raise ValueError("model_call_limit")
            launches += 1
            return await approve_launch(review, save, "receiver-launch")

        def build(who, workspace):
            return RelayActor(
                who.agent_id,
                who.session_token,
                CodexHostProfile(
                    args.project_id,
                    who.session_id,
                    args.codex,
                    workspace.path,
                    args.codex_sha256,
                    expected_cli_version=args.codex_version,
                    linux_readonly=True,
                    max_timeout_seconds=90,
                ),
                workspace.worktree_id,
                workspace.head_sha,
                {
                    "PATH": "/usr/bin:/bin",
                    "HOME": str(home),
                    "TMP": str(home),
                    "CODEX_HOME": str(codex_home),
                },
                authorize,
            )

        result = await flow.run_once(
            request,
            admin_token=owner_token,
            expected_plan_sha256=preview["plan_sha256"],
            build_receiver=build,
        )
        # Persist the actual return before any later inspection can fail.
        save("result.json", {"continuation": result, "launch_reviews": launches})
        state = {
            row["id"]: row for row in core.execute("list_tasks", receiver.authentication())["tasks"]
        }
        task_ids = [args.task_id] + ([result["task_id"]] if "task_id" in result else [])
        save(
            "postcheck.json",
            {
                "tasks": [
                    {
                        key: state[task_id][key]
                        for key in ("id", "status", "version", "task_verification")
                    }
                    for task_id in task_ids
                ]
            },
        )
        ready = (
            succeeded(result)
            and state[args.task_id]["status"] == "failed"
            and state[result["task_id"]]["task_verification"] == "unverified"
        )
        return 0 if ready else 1
    except (Exception, asyncio.CancelledError):
        save(
            "stopped.json",
            {"outcome": "unknown; inspect owner status before acting", "automatic_retry": False},
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipts", "instruction", "codex", "codex-home"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("project-id", "task-id", "codex-sha256", "codex-version"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or not __debug__:
        parser.error("This example requires Linux and the supported read-only Codex profile.")
    if any(
        not getattr(args, name).is_absolute()
        for name in ("root", "receipts", "instruction", "codex", "codex_home")
    ):
        parser.error("Use absolute paths.")
    if re.fullmatch(r"[0-9a-f]{64}", args.codex_sha256) is None:
        parser.error("Use the full reviewed Codex binary SHA-256.")
    os.umask(0o077)
    try:
        return asyncio.run(run(args, prompt("Existing project owner token: ")))
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

"""Owned proposal emitter and isolated host-process driver for verified recovery."""

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import agentsync
from agentsync.adapters.approved_launch import LaunchConsent
from agentsync.adapters.claude_invocation import ClaudeHostProfile
from agentsync.adapters.codex_invocation import CodexHostProfile
from agentsync.adapters.cursor_invocation import CursorHostProfile
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import RelayActor
from agentsync.core.service import Core
from agentsync.proposal_handoff import HandoffReceiver, ProposalHandoffRequest
from agentsync.relay_queue import RelayQueue
from agentsync.verification.owner_flow import OwnerCandidateFlow
from agentsync.verified_proposal_flow import VerifiedProposalFlow


def receiver_profile(client, original, receiver, workspace):
    fields = dict(
        project_id=receiver.project_id,
        session_id=receiver.session_id,
        executable=original.executable,
        root=workspace.path,
        expected_binary_sha256=original.expected_binary_sha256,
    )
    if client == "claude":
        return ClaudeHostProfile(**fields, model="fixture")
    if client == "cursor":
        return CursorHostProfile(**fields, expected_cli_version="fixture-1")
    assert client == "codex"
    return CodexHostProfile(**fields, expected_cli_version=original.expected_cli_version)


async def emit_proposal(
    start, path, content, *, cwd, timeout_seconds, output_limit, env, client="codex", fault=None
):
    message = json.dumps({"files": [{"path": path, "content": content}]})
    if fault == "bad-output":
        message = '{"files":[{"path":"wrong.md","content":"invalid"}]}'
    if client == "claude":
        events = [
            {"type": "system", "subtype": "init", "session_id": "owned-fixture"},
            {
                "type": "result",
                "subtype": "success",
                "session_id": "owned-fixture",
                "is_error": False,
                "result": message,
            },
        ]
        if fault == "tool-block":
            events.insert(
                1,
                {
                    "type": "assistant",
                    "session_id": "owned-fixture",
                    "message": {
                        "role": "assistant",
                        "stop_reason": "end_turn",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "fixture-tool",
                                "name": "Fixture",
                                "input": {},
                            }
                        ],
                    },
                },
            )
    elif client == "cursor":
        events = [
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 2,
                "duration_api_ms": 1,
                "session_id": "owned-fixture",
                "result": message,
            }
        ]
    else:
        assert client == "codex"
        events = [
            {"type": "thread.started", "thread_id": "local-verified-flow-fixture"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "reply", "type": "agent_message", "text": message},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1},
            },
        ]
        if fault == "codex-tool":
            events.insert(
                2,
                {
                    "type": "item.completed",
                    "item": {
                        "id": "fixture-tool",
                        "type": "command_execution",
                    },
                },
            )
    payload = "\n".join(json.dumps(event) for event in events) + "\n"
    if fault == "unknown":
        payload = ""
    return await start(
        (sys.executable, "-I", "-c", "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"),
        cwd=cwd,
        stdin_text=payload,
        timeout_seconds=timeout_seconds,
        output_limit=output_limit,
        env=env,
    )


async def resume_from_disk(checkpoint, fixture):
    request_data = fixture["request"]
    request_data["receiver"] = HandoffReceiver(**request_data["receiver"])
    request_data["allowed_paths"] = tuple(request_data["allowed_paths"])
    request = ProposalHandoffRequest(**request_data)
    flow = VerifiedProposalFlow(
        Core(fixture["data_dir"]), Path(fixture["scratch"]), Path(fixture["receipts"])
    )
    approvals, launches = [], []
    original_start = CapturedProcess.start

    async def approve(plan):
        assert checkpoint == "resume"
        approvals.append(plan.plan_sha256)
        return LaunchConsent(
            "owned-protocol-fixture-" + plan.plan_sha256,
            plan.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    def build_receiver(receiver, workspace):
        if checkpoint == "pre-dispatch":
            # Task and worktree receipts are durable, but dispatch intent is absent.
            os._exit(73)
        profile = CodexHostProfile(
            receiver.project_id,
            receiver.session_id,
            Path(fixture["executable"]),
            workspace.path,
            fixture["binary_sha256"],
        )
        return RelayActor(
            receiver.agent_id,
            receiver.session_token,
            profile,
            workspace.worktree_id,
            workspace.head_sha,
            {},
            approve,
        )

    async def exit_after_intent(*args, **kwargs):
        # Handoff wrote and durably read dispatch intent before entering the queue.
        os._exit(73)

    def unexpected_verification(*args, **kwargs):
        raise AssertionError("Recovery attempted to execute a candidate again")

    async def receiver_only(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert checkpoint == "resume" and env == {}
        contract, _ = json.JSONDecoder().raw_decode(stdin_text.split("Host contract: ", 1)[1])
        assert contract["allowed_paths"] == ["review.md"]
        assert contract["input_context"] == fixture["pin"]
        process = await emit_proposal(
            original_start,
            "review.md",
            "Owned receiver protocol fixture, not a model review.\n",
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        launches.append(process)
        return process

    with (
        patch.object(CapturedProcess, "start", classmethod(receiver_only)),
        patch.object(OwnerCandidateFlow, "start_once", unexpected_verification),
    ):
        if checkpoint == "dispatch-intent":
            with patch.object(RelayQueue, "run_ready_once", exit_after_intent):
                await flow.resume_receiver(
                    request, admin_token=fixture["admin_token"], build_receiver=build_receiver
                )
            raise AssertionError("The dispatch-intent checkpoint was not reached")
        try:
            outcome = await flow.resume_receiver(
                request, admin_token=fixture["admin_token"], build_receiver=build_receiver
            )
        finally:
            for process in launches:
                await process.cancel()
                assert (await process.snapshot()).parent_ended is True

    assert checkpoint == "resume", "The pre-dispatch checkpoint was not reached"
    return {"outcome": asdict(outcome), "approvals": len(approvals), "launches": len(launches)}


if __name__ == "__main__":
    assert Path(agentsync.__file__).resolve() == Path(sys.argv[2])
    print(json.dumps(asyncio.run(resume_from_disk(sys.argv[1], json.load(sys.stdin)))))

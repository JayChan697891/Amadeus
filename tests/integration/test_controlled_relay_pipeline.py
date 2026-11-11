"""Exercise Core and Git with local protocol fixtures, never with real clients."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pytest
from conftest import owner_grant
from test_m4b_workspaces import commit_edit, git, source_fingerprint

from agentsync.adapters.approved_launch import LaunchConsent
from agentsync.adapters.codex_invocation import CodexHostProfile
from agentsync.adapters.cursor_invocation import CursorHostProfile
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import ControlledRelay, RelayActor, RelayInput, RelayReviewer
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue, RelayQueueItem


@pytest.mark.parametrize("conflict", [False, True], ids=["handoff-and-review", "conflict-before-launch"])
async def test_controlled_relay_with_disposable_core_and_git(tmp_path, monkeypatch, conflict):
    scratch = tmp_path.resolve()
    source = scratch / "source"
    source.mkdir()
    git(source, "init", "--initial-branch=fixture-main")
    git(source, "config", "user.name", "Relay fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    (source / "same.txt").write_text("original\n", encoding="utf-8")
    git(source, "add", "same.txt")
    git(source, "commit", "-m", "fixture baseline")
    original = source_fingerprint(source)

    core = Core(scratch / "core")
    owner = core.execute("create_project", {"name": "Fixture", "root_path": str(source)})
    project_id = owner["project_id"]
    actors = []
    for name in ("First worker", "Second worker", "Independent reviewer"):
        member = core.execute("register_agent", {**owner, "name": name})
        owner_grant(core, owner, member)
        actors.append(member)

    def call(member, operation, **payload):
        return core.execute(operation, {
            "project_id": project_id,
            "session_id": member["session_id"],
            "session_token": member["session_token"],
            **payload,
        })

    first, second, reviewer = actors
    task = call(first, "create_task", title="Fixture relay", request_id="task")
    snapshot = call(first, "capture_repository", request_id="snapshot")
    context = call(
        first, "publish_context", title="Fixture context", kind="progress",
        content="Pinned fixture context", request_id="context",
    )
    trees = [
        call(
            actor, "create_worktree", snapshot_id=snapshot["snapshot_id"],
            task_id=task["id"], request_id=f"worktree-{index}",
        )
        for index, actor in enumerate((first, second))
    ]
    heads = [tree["head_sha"] for tree in trees]
    if conflict:
        heads = [commit_edit(tree, "same.txt", f"fixture change {index}\n") for index, tree in enumerate(trees)]

    binary = scratch / "fixture-client.exe"
    binary.write_bytes(b"Non-executable test fixture")
    checksum = hashlib.sha256(binary.read_bytes()).hexdigest()
    receipts = scratch / "receipts"
    receipts.mkdir()
    approvals = []
    launches = []

    async def allow_fixture(review):
        approvals.append(review)
        return LaunchConsent(
            f"fixture-approval-{len(approvals)}", review.plan_sha256, time.time() + 30, True, True,
        )

    real_capture = CapturedProcess.start

    async def launch_fixture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert argv[0] == str(binary)
        assert not env
        launches.append(cwd)
        if cwd == Path(trees[0]["path"]):
            events = [
                {"type": "thread.started", "thread_id": "fixture-thread"},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {
                    "id": "fixture-message", "type": "agent_message", "text": "FIRST_FIXTURE",
                }},
                {"type": "turn.completed", "usage": {
                    "input_tokens": 2, "cached_input_tokens": 0, "output_tokens": 1,
                }},
            ]
        else:
            assert cwd == Path(trees[1]["path"])
            assert "Pinned fixture context" in argv[-1]
            events = [{
                "type": "result", "subtype": "success", "is_error": False,
                "duration_ms": 5, "duration_api_ms": 2, "session_id": "fixture-session",
                "result": "SECOND_FIXTURE",
            }]
        stream = "\n".join(json.dumps(event) for event in events)
        helper_env = {"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {}
        return await real_capture(
            (sys.executable, "-I", "-u", "-c", f"print({stream!r})"),
            cwd=cwd, stdin_text="", timeout_seconds=timeout_seconds,
            output_limit=output_limit, env=helper_env,
        )

    monkeypatch.setattr(CapturedProcess, "start", classmethod(launch_fixture))
    first_profile = CodexHostProfile(
        project_id, first["session_id"], binary, Path(trees[0]["path"]), checksum,
    )
    second_profile = CursorHostProfile(
        project_id, second["session_id"], binary, Path(trees[1]["path"]), checksum, "fixture-version",
    )
    prepared = [
        RelayActor(
            member["agent_id"], member["session_token"], profile,
            tree["worktree_id"], head, {}, allow_fixture,
        )
        for member, profile, tree, head in zip(
            (first, second), (first_profile, second_profile), trees, heads, strict=True,
        )
    ]
    request = RelayInput(
        task["id"], task["version"], context["context_id"], context["version"],
        hashlib.sha256(context["content"].encode("utf-8")).hexdigest(),
        "Return the first fixture value", "Return the second fixture value",
        "FIRST_FIXTURE", "SECOND_FIXTURE", timeout_seconds=10,
    )
    relay = ControlledRelay(core, scratch, receipts)
    queue = RelayQueue(relay)
    wave = await queue.run_ready_once(
        (RelayQueueItem(*prepared, request),), request_id="fixture-wave",
        admin_token=owner["admin_token"],
    )
    assert wave.state == "resolved"
    assert wave.verification == "unverified"
    assert source_fingerprint(source) == original
    if conflict:
        assert wave.tasks[0].state == "conflict"
        assert not launches and not approvals
        return

    assert wave.tasks[0].state == "ready_for_review"
    assert [approval.client for approval in approvals] == ["codex", "cursor"]
    assert launches == [Path(tree["path"]) for tree in trees]
    attempts = relay.owner_inspect_attempts(project_id, task["id"], admin_token=owner["admin_token"])
    assert [attempt.status for attempt in attempts] == ["expected_reply", "expected_reply"]
    with pytest.raises(AgentSyncError):
        relay.review_once(
            RelayReviewer(project_id, first["session_id"], first["session_token"]),
            task["id"], accept=True, evidence="Participant fixture",
        )
    checked = relay.review_once(
        RelayReviewer(project_id, reviewer["session_id"], reviewer["session_token"]),
        task["id"], accept=True, evidence="Independent fixture review",
    )
    assert checked["status"] == "completed"
    assert checked["latest_review"]["reviewer_agent_id"] == reviewer["agent_id"]

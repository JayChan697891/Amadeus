"""Known local Python protocol fixtures, not actual model or artifact verification."""

import asyncio
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_m4b_workspaces import source_fingerprint
from test_task_proposals import counts
from test_task_proposals import world as world

from agentsync.adapters.approved_launch import LaunchConsent
from agentsync.adapters.codex_invocation import CodexHostProfile
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import (
    CodexProposalInput,
    ControlledRelay,
    RelayActor,
    SingleCodexInput,
    _AttemptOutcome,
)
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect


@pytest.fixture
def pilot(world, tmp_path):
    core, owner, member, auth, _, old_tree, source = world
    task = core.execute(
        "create_task", {**auth, "title": "Proposal capture", "request_id": "capture-task"}
    )
    tree = core.execute(
        "create_worktree",
        {
            **auth,
            "task_id": task["id"],
            "snapshot_id": old_tree["snapshot_id"],
            "request_id": "capture-tree",
        },
    )
    binary = tmp_path / "fixture-client.exe"
    binary.write_bytes(b"Non-executable fixture")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    profile = CodexHostProfile(
        owner["project_id"],
        member["session_id"],
        binary.resolve(),
        Path(tree["path"]),
        hashlib.sha256(binary.read_bytes()).hexdigest(),
        expected_cli_version="0.167.0-alpha.3.2",
    )
    return core, owner, member, auth, task, tree, source, receipts, profile


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "bad-schema",
        "wrong-path",
        "multiple-messages",
        "denied",
        "stale-consent",
        "timeout",
        "cancel",
        "failed-exit",
        "dirty-after-launch",
        "version-after-launch",
        "lease-after-launch",
        "crash-after-publication",
        "changed-capture-digest",
        "changed-context-and-final-digest",
        "changed-final-launch-key",
        "changed-timeout-flag",
        "foreign-observer",
        "removed-observed-receipt",
        "newer-context-and-task",
        "concurrent-start",
    ],
)
async def test_proposal_capture_with_actual_core_git_and_owned_fixture_process(
    pilot, monkeypatch, scenario
):
    core, owner, member, auth, task, tree, source, receipts, profile = pilot
    scratch = source.parent
    approvals, launches, captures = [], [], []
    capture_started = asyncio.Event()
    text = json.dumps(
        {
            "files": [
                {
                    "path": "answer.py",
                    "content": "def add(a, b):\n    return a + b  # PROPOSAL_CAPTURE_SENTINEL\n",
                }
            ]
        }
    )
    original = source_fingerprint(source)
    original_tree = source_fingerprint(Path(tree["path"]))
    original_start = CapturedProcess.start
    preview = None

    async def approve(review):
        approvals.append(review)
        if scenario == "denied":
            return None
        return LaunchConsent(
            "fixture-approval",
            preview.plan_sha256 if scenario == "stale-consent" else review.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    async def start_fixture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        launches.append(cwd)
        assert cwd == Path(tree["path"]) and env == {}
        assert "amadeus-source-proposal-v1" in stdin_text and "answer.py" in stdin_text
        output = text
        if scenario == "bad-schema":
            output = '{"files":[],"command":"INERT malicious command"}'
        if scenario == "wrong-path":
            output = text.replace("answer.py", "other.py")
        events = [
            {"type": "thread.started", "thread_id": "private-fixture-thread"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "reply", "type": "agent_message", "text": output},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1},
            },
        ]
        if scenario == "multiple-messages":
            events.insert(
                3,
                {
                    "type": "item.completed",
                    "item": {"id": "reply-two", "type": "agent_message", "text": text},
                },
            )
        payload = "\n".join(json.dumps(event) for event in events) + "\n"
        program = "import sys,time;sys.stdout.write(" + repr(payload) + ");sys.stdout.flush()"
        if scenario in {"timeout", "cancel"}:
            program += ";time.sleep(30)"
        if scenario == "failed-exit":
            program += ";sys.exit(3)"
        captured = await original_start(
            (sys.executable, "-I", "-c", program),
            cwd=cwd,
            stdin_text="",
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captures.append(captured)
        if scenario == "dirty-after-launch":
            (cwd / "baseline.txt").write_text("fixture edit", encoding="utf-8")
        if scenario == "version-after-launch":
            with connect(core.db_path) as db:
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (task["id"],))
                db.commit()
        if scenario == "lease-after-launch":
            with connect(core.db_path) as db:
                db.execute("UPDATE tasks SET lease_expires_at=0 WHERE id=?", (task["id"],))
                db.commit()
        capture_started.set()
        return captured

    monkeypatch.setattr(CapturedProcess, "start", classmethod(start_fixture))
    actor = RelayActor(
        member["agent_id"],
        member["session_token"],
        profile,
        tree["worktree_id"],
        tree["head_sha"],
        {},
        approve,
    )
    spec = CodexProposalInput(
        task["id"],
        task["version"],
        "Provide the add function as inert code data.",
        ("answer.py",),
        1 if scenario == "timeout" else 10,
    )
    relay = ControlledRelay(core, scratch, receipts)
    assert relay.observe_codex_proposal(actor, task["id"]).state == "not_started"
    preview = relay.preview_codex_proposal(actor, spec, admin_token=owner["admin_token"])
    alternative = replace(spec, allowed_paths=("different.py",))
    assert (
        relay.preview_codex_proposal(
            actor, alternative, admin_token=owner["admin_token"]
        ).plan_sha256
        != preview.plan_sha256
    )
    assert not approvals and not launches and not list(receipts.iterdir())
    original_record = relay._record

    def record(key, stage, **details):
        if scenario == "crash-after-publication" and stage == "proposal-stored":
            raise RuntimeError("Synthetic publication boundary interruption")
        original_record(key, stage, **details)

    monkeypatch.setattr(relay, "_record", record)
    successful = scenario in {
        "success",
        "changed-capture-digest",
        "changed-context-and-final-digest",
        "changed-final-launch-key",
        "changed-timeout-flag",
        "foreign-observer",
        "removed-observed-receipt",
        "newer-context-and-task",
        "concurrent-start",
    }
    outcome = None
    try:
        if scenario == "cancel":
            execution = asyncio.create_task(
                relay.run_codex_proposal_once(actor, spec, admin_token=owner["admin_token"])
            )
            try:
                async with asyncio.timeout(5):
                    await capture_started.wait()
                execution.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await execution
            finally:
                if not execution.done():
                    execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
        elif scenario == "concurrent-start":
            results = await asyncio.gather(
                *(
                    relay.run_codex_proposal_once(actor, spec, admin_token=owner["admin_token"])
                    for _ in range(2)
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(result, AgentSyncError) for result in results) == 1
            outcome = next(result for result in results if not isinstance(result, BaseException))
        elif successful:
            outcome = await relay.run_codex_proposal_once(
                actor, spec, admin_token=owner["admin_token"]
            )
        else:
            expected = RuntimeError if scenario == "crash-after-publication" else AgentSyncError
            with pytest.raises(expected):
                await relay.run_codex_proposal_once(
                    actor,
                    alternative if scenario == "stale-consent" else spec,
                    admin_token=owner["admin_token"],
                )
        assert len(approvals) == 1
        assert len(launches) == (0 if scenario in {"denied", "stale-consent"} else 1)
        assert source_fingerprint(source) == original
        if scenario != "dirty-after-launch":
            assert source_fingerprint(Path(tree["path"])) == original_tree
        assert not (Path(tree["path"]) / "answer.py").exists()
        assert counts(core)["context_revisions"] == (
            1 if successful or scenario == "crash-after-publication" else 0
        )
        assert counts(core)["merge_candidates"] == counts(core)["candidate_verification_jobs"] == 0
        public = "\n".join(p.read_text(encoding="utf-8") for p in receipts.glob("*.json"))
        for secret in (
            "PROPOSAL_CAPTURE_SENTINEL",
            "INERT malicious command",
            "private-fixture-thread",
            member["session_token"],
        ):
            assert secret not in public
        if successful:
            assert outcome.state == "proposal_stored" and outcome.verification == "unverified"
            context = core.execute(
                "get_context", {**auth, "context_id": outcome.context_id, "version": 1}
            )
            assert "PROPOSAL_CAPTURE_SENTINEL" in context["content"]
            assert outcome.task_version > spec.expected_version
            assert "PROPOSAL_CAPTURE_SENTINEL" not in repr(outcome)
        key = relay._key(actor, task["id"])

        def alter(stage, field, value):
            path = receipts / relay._receipt_name(key, stage)
            record = json.loads(path.read_text(encoding="utf-8"))
            record[field] = value
            path.write_text(json.dumps(record), encoding="utf-8")

        if scenario == "changed-capture-digest":
            alter("first-observed", "proposal_sha256", "0" * 64)
        if scenario == "changed-final-launch-key":
            alter("proposal-stored", "launch_request_sha256", "0" * 64)
        if scenario == "changed-timeout-flag":
            alter("first-observed", "timed_out", True)
        if scenario == "removed-observed-receipt":
            (receipts / relay._receipt_name(key, "first-observed")).unlink()
        if scenario == "changed-context-and-final-digest":
            content = context["content"].replace("return a + b", "return 0")
            with connect(core.db_path) as db:
                db.execute(
                    "UPDATE context_revisions SET content=? WHERE context_id=?",
                    (content, outcome.context_id),
                )
                db.commit()
            alter("proposal-stored", "content_sha256", hashlib.sha256(content.encode()).hexdigest())
        if scenario == "newer-context-and-task":
            core.execute(
                "publish_context",
                {
                    **auth,
                    "kind": "note",
                    "title": "Later context",
                    "content": "later unrelated text",
                    "context_id": outcome.context_id,
                    "expected_version": 1,
                    "request_id": "later-context",
                },
            )
            with connect(core.db_path) as db:
                db.execute(
                    "UPDATE tasks SET version=version+1,lease_expires_at=0 WHERE id=?",
                    (task["id"],),
                )
                db.commit()
        reopened = ControlledRelay(type(core)(core.data_dir), scratch, receipts)
        if scenario == "foreign-observer":
            other = core.execute("register_agent", {**owner, "name": "Other viewer"})
            foreign = replace(
                actor,
                agent_id=other["agent_id"],
                session_token=other["session_token"],
                profile=replace(profile, session_id=other["session_id"]),
            )
            assert reopened.observe_codex_proposal(foreign, task["id"]).state == "incomplete"
        observed = reopened.observe_codex_proposal(actor, task["id"])
        assert observed.state == (
            "proposal_stored"
            if scenario
            in {"success", "newer-context-and-task", "concurrent-start", "foreign-observer"}
            else "incomplete"
        )
        assert reopened.observe(actor, task["id"]).state == "incomplete"
        for attempt in (
            lambda: reopened.run_codex_proposal_once(actor, spec, admin_token=owner["admin_token"]),
            lambda: reopened.run_codex_once(
                actor,
                SingleCodexInput(task["id"], task["version"], "fixed", "fixed"),
                admin_token=owner["admin_token"],
            ),
        ):
            with pytest.raises(AgentSyncError):
                await attempt()
        assert len(approvals) == 1
        current = next(
            t for t in core.execute("get_project_state", auth)["tasks"] if t["id"] == task["id"]
        )
        assert current["status"] == "running"
    finally:
        for capture in captures:
            await capture.cancel()
            assert (await capture.snapshot()).parent_ended is True


def test_internal_capture_and_spec_repr_do_not_expose_source():
    assert "secret" not in repr(_AttemptOutcome({"lease_token": "secret"}, "secret code"))
    spec = CodexProposalInput("task", 1, "secret prompt", ("b.py", "a.py"))
    assert spec.allowed_paths == ("a.py", "b.py")
    assert "secret" not in repr(spec)
    with pytest.raises(AgentSyncError):
        CodexProposalInput("task", 1, "input", ["answer.py"])
    with pytest.raises(AgentSyncError):
        CodexProposalInput("task", 1, "input", ("../x",))

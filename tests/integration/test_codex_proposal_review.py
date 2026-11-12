"""Controlled protocol fixture to actual Core/Git/queue; no real model or execution."""

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import owner_grant
from test_codex_proposal_capture import pilot as pilot
from test_m4b_workspaces import source_fingerprint
from test_task_proposals import world as world

from agentsync.adapters.approved_launch import LaunchConsent, digest
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import (
    CodexProposalInput,
    ControlledRelay,
    RelayActor,
    SingleCodexInput,
    _proposal_contract,
)
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase


@pytest.fixture
async def captured_processes():
    captures = []
    try:
        yield captures
    finally:
        for capture in captures:
            await capture.cancel()
            assert (await capture.snapshot()).parent_ended is True


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "default",
        "denied",
        "stale-launch-consent",
        "failed-exit",
        "before-review-intent",
        "after-core-review",
        "expired-after-store",
        "version-after-store",
        "dirty-after-store",
        "changed-opt-in",
        "missing-submitted",
        "changed-intent",
        "changed-task-version",
        "changed-task-owner",
        "changed-marker",
        "stale-stage-plan",
        "wrong-stager",
        "wrong-owner",
    ],
)
async def test_controlled_proposal_review_and_native_staging(
    pilot, monkeypatch, scenario, captured_processes
):
    core, owner, member, auth, task, tree, source, receipts, profile = pilot
    parent = source.parent
    launches, captures = [], captured_processes
    initial = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    original_start = CapturedProcess.start
    source_text = "def solve(value):\n    return value  # INERT_REVIEW_SENTINEL\n"
    output = json.dumps({"files": [{"path": "solution.py", "content": source_text}]})
    events = [
        {"type": "thread.started", "thread_id": "fixture-private-session"},
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
    default_preview = None

    async def approve(review):
        if scenario == "denied":
            return None
        return LaunchConsent(
            "fixture-review-approval",
            default_preview.plan_sha256
            if scenario == "stale-launch-consent"
            else review.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    async def start(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        launches.append(argv)
        assert env == {} and cwd == Path(tree["path"])
        contract = json.loads(stdin_text.split("Host contract: ", 1)[1])
        assert contract.get("submit_for_review", False) is (scenario != "default")
        payload = "\n".join(json.dumps(event) for event in events) + "\n"
        program = "import sys;sys.stdout.write(" + repr(payload) + ");sys.stdout.flush()"
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
        return captured

    monkeypatch.setattr(CapturedProcess, "start", classmethod(start))
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
        task["id"], task["version"], "Return inert solution source.", ("solution.py",), 10
    )
    relay = ControlledRelay(core, parent, receipts)
    default_preview = relay.preview_codex_proposal(actor, spec, admin_token=owner["admin_token"])
    assert (
        relay.preview_codex_proposal(
            actor, replace(spec, submit_for_review=False), admin_token=owner["admin_token"]
        ).plan_sha256
        == default_preview.plan_sha256
    )
    opt_in = replace(spec, submit_for_review=True)
    assert (
        relay.preview_codex_proposal(actor, opt_in, admin_token=owner["admin_token"]).plan_sha256
        != default_preview.plan_sha256
    )
    old_contract = {
        "format": "amadeus-source-proposal-v1",
        "allowed_paths": spec.allowed_paths,
        "max_json_bytes": 32768,
        "max_file_bytes": 8192,
        "expected_task_version": spec.expected_version,
        "worktree_id": actor.worktree_id,
        "base_head": actor.expected_head,
    }
    assert digest(
        _proposal_contract(actor, spec.expected_version, spec.allowed_paths, False)
    ) == digest(old_contract)
    assert relay.observe_codex_proposal_review(actor, task["id"]).state == "not_requested"
    record = relay._record

    def fault_record(key, stage, **details):
        if scenario == "before-review-intent" and stage == "proposal-review-intent":
            raise RuntimeError("Synthetic interruption before review intent")
        if scenario == "after-core-review" and stage == "proposal-review-submitted":
            raise RuntimeError("Synthetic interruption after Core review")
        record(key, stage, **details)
        if stage == "proposal-stored":
            if scenario in {"expired-after-store", "version-after-store"}:
                with connect(core.db_path) as db:
                    field = (
                        "lease_expires_at=0"
                        if scenario == "expired-after-store"
                        else "version=version+1"
                    )
                    db.execute("UPDATE tasks SET " + field + " WHERE id=?", (task["id"],))
            elif scenario == "dirty-after-store":
                (Path(tree["path"]) / "baseline.txt").write_bytes(b"owned fixture drift")

    monkeypatch.setattr(relay, "_record", fault_record)
    failing = {
        "denied",
        "stale-launch-consent",
        "failed-exit",
        "before-review-intent",
        "after-core-review",
        "expired-after-store",
        "version-after-store",
        "dirty-after-store",
    }
    chosen = spec if scenario == "default" else opt_in
    if scenario in failing:
        with pytest.raises((AgentSyncError, RuntimeError)):
            await relay.run_codex_proposal_once(actor, chosen, admin_token=owner["admin_token"])
    else:
        assert (
            await relay.run_codex_proposal_once(actor, chosen, admin_token=owner["admin_token"])
        ).state == "proposal_stored"
    key = relay._key(actor, task["id"])
    if scenario in {"changed-opt-in", "changed-intent", "missing-submitted"}:
        name = (
            "incomplete"
            if scenario == "changed-opt-in"
            else "proposal-review-intent"
            if scenario == "changed-intent"
            else "proposal-review-submitted"
        )
        path = receipts / relay._receipt_name(key, name)
        if scenario == "missing-submitted":
            path.unlink()
        else:
            data = json.loads(path.read_text())
            data["submit_for_review" if scenario == "changed-opt-in" else "content_sha256"] = (
                False if scenario == "changed-opt-in" else "f" * 64
            )
            path.write_text(json.dumps(data), encoding="utf-8")
    if scenario in {"changed-task-version", "changed-task-owner", "changed-marker"}:
        with connect(core.db_path) as db:
            if scenario == "changed-task-version":
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (task["id"],))
            elif scenario == "changed-task-owner":
                db.execute("UPDATE tasks SET owner_session_id=NULL WHERE id=?", (task["id"],))
            else:
                db.execute("UPDATE tasks SET result='other' WHERE id=?", (task["id"],))
    reopened = ControlledRelay(core, parent, receipts)
    observed = reopened.observe_codex_proposal_review(actor, task["id"])
    ready = {"success", "stale-stage-plan", "wrong-stager", "wrong-owner"}
    assert observed.state == (
        "submitted_for_review"
        if scenario in ready
        else "not_requested"
        if scenario == "default"
        else "incomplete"
    )
    assert observed.verification == "unverified"
    if scenario not in {"denied", "stale-launch-consent", "failed-exit", "changed-opt-in"}:
        assert reopened.observe_codex_proposal(actor, task["id"]).state == "proposal_stored"
    assert reopened.observe(actor, task["id"]).state == "incomplete"
    stager = core.execute("register_agent", {**owner, "name": "Dedicated staging worker"})
    owner_grant(core, owner, stager, ("worker",))
    staging = {
        "admin_token": owner["admin_token"],
        "staging_session_id": stager["session_id"],
        "staging_session_token": stager["session_token"],
    }
    if scenario == "wrong-stager":
        staging["staging_session_token"] = "invalid"
    elif scenario == "wrong-owner":
        staging["admin_token"] = "invalid"
    if scenario in {"success", "stale-stage-plan"}:
        preview = reopened.preview_codex_proposal_staging(actor, task["id"], **staging)
        assert (
            preview["plan"]["task_version"]
            == observed.review_task_version
            == observed.publication_task_version + 1
        )
        if scenario == "stale-stage-plan":
            with connect(core.db_path) as db:
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (task["id"],))
            with pytest.raises(AgentSyncError):
                reopened.stage_codex_proposal_once(
                    actor, task["id"], **staging, expected_plan_sha256=preview["plan_sha256"]
                )
        else:
            staged = reopened.stage_codex_proposal_once(
                actor, task["id"], **staging, expected_plan_sha256=preview["plan_sha256"]
            )
            candidate = OwnerCandidateExporter(core).export(
                **owner,
                candidate_id=staged["candidate_id"],
                expected_candidate_sha=staged["candidate_sha"],
            )
            assert candidate.snapshot.source == source_text.encode()
            job = CandidateVerificationJobs(core).enqueue(
                **owner,
                candidate_id=staged["candidate_id"],
                expected_candidate_sha=staged["candidate_sha"],
                profile=DockerProfile("sha256:" + "b" * 64, (JsonCase(None, None),)),
                request_id="proposal-queue",
            )
            assert job["status"] == "queued" and not job.get("execution_connected", False)
            assert (
                reopened.observe_codex_proposal_review(actor, task["id"]).state
                == "submitted_for_review"
            )
    else:
        with pytest.raises(AgentSyncError):
            reopened.preview_codex_proposal_staging(actor, task["id"], **staging)
    with pytest.raises(AgentSyncError):
        await reopened.run_codex_proposal_once(actor, chosen, admin_token=owner["admin_token"])
    with pytest.raises(AgentSyncError):
        await reopened.run_codex_once(
            actor,
            SingleCodexInput(task["id"], task["version"], "fixed", "fixed", 10),
            admin_token=owner["admin_token"],
        )
    assert len(launches) == (0 if scenario in {"denied", "stale-launch-consent"} else 1)
    for capture in captures:
        assert (await capture.snapshot()).parent_ended is True
    assert source_fingerprint(source) == initial[0]
    if scenario != "dirty-after-store":
        assert source_fingerprint(Path(tree["path"])) == initial[1]


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_review_submission_requires_boolean(value):
    with pytest.raises(AgentSyncError):
        CodexProposalInput("task", 1, "inert", ("solution.py",), 10, value)

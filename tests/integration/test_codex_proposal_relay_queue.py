"""Actual Core/Git and owned protocol fixtures. No model or candidate execution."""

import asyncio
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import owner_grant
from test_codex_proposal_capture import pilot as pilot
from test_m4b_workspaces import source_fingerprint
from test_task_proposals import counts
from test_task_proposals import world as world

import agentsync.controlled_relay as controlled_relay
from agentsync.adapters.approved_launch import LaunchConsent, digest, prepare_launch_review
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import CodexProposalInput, ControlledRelay, RelayActor, RelayInput
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import (
    CodexProposalPreviewTask,
    CodexProposalQueueItem,
    RelayPreviewTask,
    RelayQueue,
    RelayQueueItem,
)
from agentsync.storage.database import connect


@pytest.fixture
async def proposal_wave(pilot, monkeypatch):
    core, owner, member, auth, task, tree, source, receipts, profile = pilot
    approvals, captures = [], []
    started = asyncio.Event()
    reviewer = core.execute("register_agent", {**owner, "name": "Independent reviewer"})
    owner_grant(core, owner, reviewer, ("reviewer",))
    review_auth = {
        "project_id": owner["project_id"],
        "session_id": reviewer["session_id"],
        "session_token": reviewer["session_token"],
    }

    async def approve(plan):
        approvals.append(plan)
        return LaunchConsent(
            f"fixture-proposal-approval-{len(approvals)}",
            plan.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    original_start = CapturedProcess.start

    async def start_fixture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert env == {}
        contract = json.loads(stdin_text.split("Host contract: ", 1)[1])
        assert contract["submit_for_review"] is True
        assert len(contract["wave_sha256"]) == 64
        proposal = {"files": [{"path": "answer.py", "content": "# INERT_QUEUE_FIXTURE\n"}]}
        events = [
            {"type": "thread.started", "thread_id": "fixture-queue-thread"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "reply", "type": "agent_message", "text": json.dumps(proposal)},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 1},
            },
        ]
        payload = "\n".join(json.dumps(event) for event in events) + "\n"
        program = "import sys;sys.stdout.write(" + repr(payload) + ");sys.stdout.flush()"
        if "Wait fixture" in stdin_text:
            program = "import time;time.sleep(60)"
        capture = await original_start(
            (sys.executable, "-I", "-c", program),
            cwd=cwd,
            stdin_text="",
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captures.append(capture)
        started.set()
        return capture

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
        "Return inert source.",
        ("answer.py",),
        10,
        True,
    )
    try:
        yield (
            ControlledRelay(core, source.parent, receipts),
            CodexProposalQueueItem(actor, spec),
            review_auth,
            approvals,
            captures,
            started,
        )
    finally:
        for capture in captures:
            await capture.cancel()
            assert (await capture.snapshot()).parent_ended is True


def cancel_fixture_load(world):
    core, _, _, auth, old, _, _ = world
    return core.execute(
        "update_task",
        {
            **auth,
            "task_id": old["task_id"],
            "lease_token": old["lease_token"],
            "expected_version": old["expected_version"],
            "status": "cancelled",
            "request_id": "cancel-original-fixture-task",
        },
    )


def accept_fixture_review(core, review_auth, task_id, version):
    return core.execute(
        "review_task",
        {
            **review_auth,
            "task_id": task_id,
            "expected_version": version,
            "accept": True,
            "evidence": "Independent review of the disposable fixture; unverified",
            "request_id": "accept-fixture-review-" + task_id,
        },
    )


async def test_proposal_queue_requires_current_heartbeat_before_launch(pilot, world, proposal_wave):
    core, owner, _, auth, _, _, _, _, _ = pilot
    relay, item, _, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    queue = RelayQueue(relay)
    token = owner["admin_token"]
    request_id = "heartbeat-wave"
    initial = queue.preview((item,), admin_token=token)
    assert initial.state == "selected" and initial.selection_sha256 is not None
    queued_task = relay._single_codex_task(
        item.first, item.task, token, wave_key=queue._key(item.first, request_id)
    )
    expected_plan = prepare_launch_review(
        item.first.profile, queued_task, environment=item.first.environment
    )

    with connect(core.db_path) as db:
        db.execute(
            "UPDATE sessions SET heartbeat_at=? WHERE id=?",
            (time.time() - 121, auth["session_id"]),
        )
    session = next(
        row
        for row in core.execute("get_project_state", auth)["sessions"]
        if row["id"] == auth["session_id"]
    )
    assert session["expires_at"] > time.time() and session["online"] is False
    assert queue.preview((item,), admin_token=token).state == "no_ready_tasks"
    with pytest.raises(AgentSyncError) as rejected:
        await queue.run_ready_once(
            (item,),
            request_id=request_id,
            admin_token=token,
            expected_selection_sha256=initial.selection_sha256,
        )
    assert rejected.value.code == "selection_changed"
    assert queue.observe(item.first, request_id).state == "not_started"
    assert not approvals and not captures

    core.execute("heartbeat", auth)
    assert queue.preview((item,), admin_token=token) == initial
    wave = await queue.run_ready_once(
        (item,),
        request_id=request_id,
        admin_token=token,
        expected_selection_sha256=initial.selection_sha256,
    )
    assert wave.state == "resolved" and wave.tasks[0].state == "ready_for_review"
    assert approvals == [expected_plan] and len(captures) == 1


async def test_proposal_queue_uses_load_capabilities_and_core_dependencies(
    pilot,
    world,
    proposal_wave,
):
    core, owner, _, auth, task, tree, source, _, _ = pilot
    relay, first, reviewer, approvals, captures, _ = proposal_wave
    queue = RelayQueue(relay)
    token = owner["admin_token"]
    dependent = core.execute(
        "create_task",
        {
            **auth,
            "title": "Dependent proposal",
            "priority": 5,
            "dependencies": [task["id"]],
            "request_id": "queue-dependent",
        },
    )
    dependent_tree = core.execute(
        "create_worktree",
        {
            **auth,
            "task_id": dependent["id"],
            "snapshot_id": tree["snapshot_id"],
            "request_id": "queue-dependent-tree",
        },
    )
    second_actor = replace(
        first.first,
        profile=replace(first.first.profile, root=Path(dependent_tree["path"])),
        worktree_id=dependent_tree["worktree_id"],
        expected_head=dependent_tree["head_sha"],
    )
    second = CodexProposalQueueItem(
        second_actor,
        replace(first.task, task_id=dependent["id"], expected_version=dependent["version"]),
    )
    with pytest.raises(AgentSyncError, match="Invalid controlled relay wave input"):
        replace(first, task=replace(first.task, submit_for_review=False))
    assert queue.preview((first, second), admin_token=token, parallel_limit=2).state == (
        "no_ready_tasks"
    )
    cancel_fixture_load(world)
    missing_cap = replace(first, first_capabilities=("not-declared",))
    assert queue.preview((missing_cap, second), admin_token=token, parallel_limit=2).state == (
        "no_ready_tasks"
    )
    preview = queue.preview((first, second), admin_token=token, parallel_limit=2)
    assert preview.tasks == (
        CodexProposalPreviewTask(task["id"], task["version"], first.first.agent_id),
    )
    changed = replace(first, task=replace(first.task, instruction="Changed inert instruction."))
    with pytest.raises(AgentSyncError) as stale:
        await queue.run_ready_once(
            (changed, second),
            request_id="first-wave",
            admin_token=token,
            parallel_limit=2,
            expected_selection_sha256=preview.selection_sha256,
        )
    assert stale.value.code == "selection_changed"
    assert not approvals and not captures
    fingerprints = [
        source_fingerprint(path)
        for path in (
            source,
            first.first.profile.root,
            second.first.profile.root,
        )
    ]
    wave = await queue.run_ready_once(
        (first, second),
        request_id="first-wave",
        admin_token=token,
        parallel_limit=2,
        expected_selection_sha256=preview.selection_sha256,
    )
    assert wave.state == "resolved" and wave.tasks[0].state == "ready_for_review"
    assert wave.verification == "unverified"
    assert len(approvals) == len(captures) == 1
    assert queue.preview((second,), admin_token=token).state == "no_ready_tasks"
    review = relay.observe_codex_proposal_review(first.first, task["id"])
    assert review.state == "submitted_for_review"
    completed = accept_fixture_review(core, reviewer, task["id"], review.review_task_version)
    assert completed["status"] == "completed" and completed["task_verification"] == "unverified"
    wave = await queue.run_ready_once((second,), request_id="next-wave", admin_token=token)
    assert wave.state == "resolved" and wave.tasks[0].task_id == dependent["id"]
    assert len(approvals) == len(captures) == 2
    assert counts(core) == {
        "context_revisions": 2,
        "merge_candidates": 0,
        "candidate_verification_jobs": 0,
    }
    assert [
        source_fingerprint(path)
        for path in (
            source,
            first.first.profile.root,
            second.first.profile.root,
        )
    ] == fingerprints


def test_mixed_wave_slots_exclude_shared_agent_and_root(pilot, world, proposal_wave):
    core, owner, proposer, auth, _, tree, _, _, _ = pilot
    relay, proposal, _, approvals, _, _ = proposal_wave
    queue = RelayQueue(relay)
    cancel_fixture_load(world)
    pair_task = core.execute(
        "create_task",
        {**auth, "title": "Fixed reply pair", "priority": -1, "request_id": "mixed-pair-task"},
    )

    def prepare(worker):
        pair_tree = core.execute(
            "create_worktree",
            {
                "project_id": owner["project_id"],
                "session_id": worker["session_id"],
                "session_token": worker["session_token"],
                "task_id": pair_task["id"],
                "snapshot_id": tree["snapshot_id"],
                "request_id": "pair-tree-" + worker["agent_id"],
            },
        )
        return replace(
            proposal.first,
            agent_id=worker["agent_id"],
            session_token=worker["session_token"],
            profile=replace(
                proposal.first.profile,
                session_id=worker["session_id"],
                root=Path(pair_tree["path"]),
            ),
            worktree_id=pair_tree["worktree_id"],
            expected_head=pair_tree["head_sha"],
        )

    workers = [core.execute("register_agent", {**owner, "name": name}) for name in ("A", "B")]
    for worker in workers:
        owner_grant(core, owner, worker, ("worker",))
    left, right = (prepare(worker) for worker in workers)
    pair = RelayQueueItem(
        left,
        right,
        RelayInput(
            pair_task["id"],
            pair_task["version"],
            "fixture-context",
            1,
            "a" * 64,
            "Return left",
            "Return right",
            "Left",
            "Right",
        ),
    )
    kwargs = {"admin_token": owner["admin_token"], "parallel_limit": 2}
    preview = queue.preview((pair, proposal), **kwargs)
    assert [type(task) for task in preview.tasks] == [CodexProposalPreviewTask, RelayPreviewTask]
    same_agent = replace(pair, first=prepare(proposer))
    same_root = replace(
        pair, first=replace(left, profile=replace(left.profile, root=proposal.first.profile.root))
    )
    for conflicting in (same_agent, same_root):
        assert queue.preview((conflicting, proposal), **kwargs).tasks == preview.tasks[:1]
    assert not approvals


@pytest.mark.parametrize("scenario", ["submitted", "completed", "cross-wave"])
async def test_proposal_wave_reconciles_saved_receipts(
    pilot, world, proposal_wave, monkeypatch, scenario
):
    core, owner, _, _, task, _, source, receipts, _ = pilot
    relay, item, reviewer, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    queue = RelayQueue(relay)
    token = owner["admin_token"]

    def interrupted(*args, **kwargs):
        raise AgentSyncError("storage_error", "Fixture stopped before wave result was saved.")

    monkeypatch.setattr(queue._journal, "record", interrupted)
    with pytest.raises(AgentSyncError) as failure:
        await queue.run_ready_once((item,), request_id="reopen-wave", admin_token=token)
    assert failure.value.code == "storage_error"
    review = relay.observe_codex_proposal_review(item.first, task["id"])
    assert review.state == "submitted_for_review"
    if scenario == "completed":
        accept_fixture_review(core, reviewer, task["id"], review.review_task_version)
        with connect(core.db_path) as db:
            db.execute(
                "UPDATE sessions SET expires_at=0 WHERE id=?", (item.first.profile.session_id,)
            )
    reopened = RelayQueue(ControlledRelay(Core(core.data_dir), source.parent, receipts))
    pending = reopened.owner_observe_pending(owner["project_id"], admin_token=token)
    assert pending is not None and pending.receipt_state == "admitted"
    if scenario == "cross-wave":
        key = relay._key(item.first, task["id"])
        path = receipts / relay._receipt_name(key, "proposal-review-intent")
        intent = json.loads(path.read_text(encoding="utf-8"))
        intent["wave_sha256"] = "f" * 64
        path.write_text(json.dumps(intent), encoding="utf-8")
        path = receipts / relay._receipt_name(key, "proposal-review-submitted")
        submitted = json.loads(path.read_text(encoding="utf-8"))
        submitted["review_intent_sha256"] = digest(intent)
        path.write_text(json.dumps(submitted), encoding="utf-8")
    reconciled = reopened.reconcile_pending_from_session(
        **reviewer,
        admin_token=token,
        expected_wave_id=pending.wave_id,
    )
    assert reconciled.verification == "unverified"
    if scenario == "cross-wave":
        assert reconciled.state == "incomplete"
        assert reopened.owner_observe_pending(owner["project_id"], admin_token=token) == pending
    else:
        assert reconciled.state == "resolved" and reconciled.tasks[0].state == "ready_for_review"
        assert reopened.owner_observe_pending(owner["project_id"], admin_token=token) is None
    assert len(approvals) == len(captures) == 1


@pytest.mark.parametrize("scenario", ["revoked", "stale-consent", "cancelled", "execution-limit"])
async def test_uncertain_proposal_wave_keeps_its_fence(
    pilot, world, proposal_wave, monkeypatch, scenario
):
    core, owner, member, _, task, _, source, receipts, _ = pilot
    relay, item, reviewer, _, captures, started = proposal_wave
    cancel_fixture_load(world)
    queue = RelayQueue(relay)
    token = owner["admin_token"]
    request = "interrupted-wave"
    if scenario in {"revoked", "stale-consent"}:
        authority = item.first.authority
        direct = relay.preview_codex_proposal(item.first, item.task, admin_token=token)

        async def authorize(plan):
            consent = await authority(plan)
            assert consent is not None and plan.plan_sha256 != direct.plan_sha256
            if scenario == "revoked":
                owner_grant(core, owner, member, ("viewer",))
                return consent
            return replace(consent, plan_sha256=direct.plan_sha256)

        item = replace(item, first=replace(item.first, authority=authorize))
        wave = await queue.run_ready_once((item,), request_id=request, admin_token=token)
        assert wave.state == "incomplete" and not captures
    elif scenario == "execution-limit":
        attempt = relay._attempt
        reached_publication = False
        check_deadline = controlled_relay._check_execution_deadline

        async def finish_capture(*args, **kwargs):
            nonlocal reached_publication
            result = await attempt(*args, **kwargs)
            reached_publication = True
            return result

        def expire_after_capture(deadline):
            assert deadline is not None
            check_deadline(asyncio.get_running_loop().time() if reached_publication else deadline)

        monkeypatch.setattr(relay, "_attempt", finish_capture)
        monkeypatch.setattr(controlled_relay, "_check_execution_deadline", expire_after_capture)
        sequence = await queue.drain_ready(
            (item,),
            request_id=request,
            admin_token=token,
            execution_budget_seconds=30,
        )
        assert sequence.reason == "execution_limit"
        assert sequence.waves[0].tasks[0].failure_code == "relay_execution_limit"
        assert reached_publication and len(captures) == 1
    else:
        item = replace(item, task=replace(item.task, instruction="Wait fixture"))
        execution = asyncio.create_task(
            queue.run_ready_once((item,), request_id=request, admin_token=token)
        )
        try:
            async with asyncio.timeout(10):
                await started.wait()
            with pytest.raises(AgentSyncError) as fenced:
                await queue.run_ready_once((item,), request_id="concurrent-wave", admin_token=token)
            assert fenced.value.code == "wave_incomplete"
        finally:
            execution.cancel()
            with pytest.raises(asyncio.CancelledError):
                await execution
        assert len(captures) == 1 and (await captures[0].snapshot()).parent_ended is True
    reopened = RelayQueue(ControlledRelay(Core(core.data_dir), source.parent, receipts))
    pending = reopened.owner_observe_pending(owner["project_id"], admin_token=token)
    assert pending is not None
    assert (
        reopened.reconcile_pending_from_session(
            **reviewer,
            admin_token=token,
            expected_wave_id=pending.wave_id,
        ).state
        == "incomplete"
    )
    assert reopened.owner_observe_pending(owner["project_id"], admin_token=token) == pending
    assert relay.observe_codex_proposal_review(item.first, task["id"]).state == "incomplete"
    assert counts(core)["context_revisions"] == 0

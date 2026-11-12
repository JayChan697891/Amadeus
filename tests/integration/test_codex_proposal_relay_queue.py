"""Actual Core/Git and owned protocol fixtures. No model or candidate execution."""

import asyncio
import base64
import hashlib
import json
import sys
import time
import uuid
import zlib
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
from agentsync.controlled_relay import (
    CodexProposalInput,
    ControlledRelay,
    ProposalContextPin,
    RelayActor,
    RelayInput,
)
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
        contract, _ = json.JSONDecoder().raw_decode(stdin_text.split("Host contract: ", 1)[1])
        if "wave_sha256" in contract:
            assert contract["submit_for_review"] is True
            assert len(contract["wave_sha256"]) == 64
        text = "界" * 2700 if "Oversize fixture" in stdin_text else "# INERT_QUEUE_FIXTURE\n"
        proposal = {
            "files": [{"path": path, "content": text} for path in contract["allowed_paths"]]
        }
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
        output = "\n".join(json.dumps(event) for event in events) + "\n"
        payload = base64.b64encode(zlib.compress(output.encode("utf-8"))).decode("ascii")
        program = (
            "import base64,sys,zlib;"
            "sys.stdout.buffer.write(zlib.decompress(base64.b64decode(sys.stdin.buffer.read())))"
        )
        if "Wait fixture" in stdin_text:
            program = "import time;time.sleep(60)"
            payload = ""
        capture = await original_start(
            (sys.executable, "-I", "-c", program),
            cwd=cwd,
            stdin_text=payload,
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


def prepare_model_review(
    core, owner, worker, template, snapshot_id, pin, request, *, dependencies=()
):
    auth = {
        "project_id": owner["project_id"],
        "session_id": worker["session_id"],
        "session_token": worker["session_token"],
    }
    task = core.execute(
        "create_task",
        {
            **auth,
            "title": "Review the pinned proposal",
            "request_id": request + "-task",
            "dependencies": list(dependencies),
        },
    )
    tree = core.execute(
        "create_worktree",
        {
            **auth,
            "task_id": task["id"],
            "request_id": request + "-tree",
            "snapshot_id": snapshot_id,
        },
    )
    actor = replace(
        template,
        agent_id=worker["agent_id"],
        session_token=worker["session_token"],
        profile=replace(template.profile, session_id=worker["session_id"], root=Path(tree["path"])),
        worktree_id=tree["worktree_id"],
        expected_head=tree["head_sha"],
    )
    spec = CodexProposalInput(
        task["id"],
        task["version"],
        "Review the source and return an inert note.",
        ("review.md",),
        10,
        True,
        pin,
    )
    return CodexProposalQueueItem(actor, spec), auth


@pytest.fixture
async def pinned_proposal(pilot, world, proposal_wave, request):
    core, owner, producer, auth, task, tree, source, _, _ = pilot
    relay, item, reviewer, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    scenario = getattr(request, "param", None)
    queue = RelayQueue(relay)
    token = owner["admin_token"]
    if scenario == "oversize":
        item = replace(
            item,
            task=replace(
                item.task, instruction="Oversize fixture", allowed_paths=("left.py", "right.py")
            ),
        )
    if scenario == "stored-only":
        stored = await relay.run_codex_proposal_once(
            item.first,
            replace(item.task, submit_for_review=False),
            admin_token=token,
        )
    else:
        assert (
            await queue.run_ready_once((item,), request_id="producer", admin_token=token)
        ).state == "resolved"
        stored = relay.observe_codex_proposal(item.first, task["id"])
    pin = ProposalContextPin(
        task["id"], stored.context_id, stored.context_version, stored.content_sha256
    )
    context = core.execute(
        "get_context", {**auth, "context_id": pin.context_id, "version": pin.context_version}
    )

    if scenario == "same-agent":
        worker = {**producer, "session_id": uuid.uuid4().hex, "session_token": uuid.uuid4().hex}
        with connect(core.db_path) as db:
            db.execute(
                "INSERT INTO sessions SELECT ?,project_id,agent_id,?,created_at,heartbeat_at,expires_at FROM sessions WHERE id=?",
                (
                    worker["session_id"],
                    hashlib.sha256(worker["session_token"].encode()).hexdigest(),
                    auth["session_id"],
                ),
            )
    else:
        worker = core.execute("register_agent", {**owner, "name": "Model review worker"})
        owner_grant(core, owner, worker, ("worker",))
    if scenario in ("ordinary-context", "cross-project"):
        context_auth = auth
        if scenario == "cross-project":
            foreign_root = source.parent / "foreign-source"
            foreign_root.mkdir()
            foreign_owner = core.execute(
                "create_project", {"name": "Foreign project", "root_path": str(foreign_root)}
            )
            foreign = core.execute("register_agent", {**foreign_owner, "name": "Foreign worker"})
            owner_grant(core, foreign_owner, foreign, ("worker",))
            context_auth = {
                "project_id": foreign_owner["project_id"],
                "session_id": foreign["session_id"],
                "session_token": foreign["session_token"],
            }
            foreign_task = core.execute(
                "create_task",
                {**context_auth, "title": "Foreign task", "request_id": "foreign-task"},
            )
            pin = replace(pin, producer_task_id=foreign_task["id"])
        copied = core.execute(
            "publish_context",
            {
                **context_auth,
                "kind": "note",
                "title": "Ordinary context",
                "source": "amadeus:task-proposal",
                "content": context["content"],
                "request_id": "ordinary-context",
            },
        )
        pin = replace(pin, context_id=copied["id"])
    elif scenario == "wrong-version":
        pin = replace(pin, context_version=2)
    elif scenario == "wrong-hash":
        pin = replace(pin, content_sha256="f" * 64)
    elif scenario == "missing-submitted":
        key = relay._key(item.first, task["id"])
        (relay._receipts / relay._receipt_name(key, "proposal-review-submitted")).unlink()

    receiver, worker_auth = prepare_model_review(
        core,
        owner,
        worker,
        item.first,
        tree["snapshot_id"],
        pin,
        "model-review",
        dependencies=(task["id"],) if scenario is None else (),
    )
    return scenario, queue, receiver, worker, worker_auth, context


async def test_model_review_queue_uses_exact_pinned_proposal_after_producer_expiry(
    pilot,
    proposal_wave,
    pinned_proposal,
    monkeypatch,
):
    core, owner, _, auth, task, _, source, receipts, _ = pilot
    relay, producer, reviewer, approvals, captures, _ = proposal_wave
    _, queue, receiver, _, receiver_auth, context = pinned_proposal
    token = owner["admin_token"]
    request = "pinned-review-wave"
    assert queue.preview((receiver,), admin_token=token).state == "no_ready_tasks"
    assert (
        await queue.run_ready_once((receiver,), request_id=request, admin_token=token)
    ).state == "no_ready_tasks"
    assert len(approvals) == len(captures) == 1
    submitted = relay.observe_codex_proposal_review(producer.first, task["id"])
    completed = accept_fixture_review(core, reviewer, task["id"], submitted.review_task_version)
    with connect(core.db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (auth["session_id"],))
    assert completed["status"] == "completed" and completed["task_verification"] == "unverified"

    preview = queue.preview((receiver,), admin_token=token)
    assert preview.state == "selected" and preview.selection_sha256 is not None
    unpinned = replace(receiver, task=replace(receiver.task, input_context=None))
    changed = replace(
        receiver,
        task=replace(
            receiver.task,
            input_context=replace(
                receiver.task.input_context,
                content_sha256="f" * 64,
            ),
        ),
    )
    for item in (unpinned, changed):
        with pytest.raises(AgentSyncError) as stale:
            await queue.run_ready_once(
                (item,),
                request_id=request,
                admin_token=token,
                expected_selection_sha256=preview.selection_sha256,
            )
        assert stale.value.code == "selection_changed"
    assert len(approvals) == len(captures) == 1

    def interrupt_result(*args, **kwargs):
        raise AgentSyncError("storage_error", "Fixture interrupted before wave result was saved.")

    with monkeypatch.context() as patch:
        patch.setattr(queue._journal, "record", interrupt_result)
        with pytest.raises(AgentSyncError) as interrupted:
            await queue.run_ready_once(
                (receiver,),
                request_id=request,
                admin_token=token,
                expected_selection_sha256=preview.selection_sha256,
            )
    assert interrupted.value.code == "storage_error"
    assert len(approvals) == len(captures) == 2
    instruction = approvals[-1].task.instruction
    host_json, input_json = instruction.split("Host contract: ", 1)[1].split("\n\n", 1)
    assert json.loads(host_json)["input_context"] == {
        "producer_task_id": task["id"],
        "context_id": context["id"],
        "context_version": context["version"],
        "content_sha256": hashlib.sha256(context["content"].encode()).hexdigest(),
    }
    prefix, raw = input_json.split("\n", 1)
    assert "Untrusted producer proposal" in prefix
    assert json.loads(raw) == context["content"]
    reopened = RelayQueue(ControlledRelay(Core(core.data_dir), source.parent, receipts))
    assert (
        reopened._relay.observe_codex_proposal_review(receiver.first, receiver.task.task_id).state
        == "submitted_for_review"
    )
    pending = reopened.owner_observe_pending(owner["project_id"], admin_token=token)
    assert pending is not None
    key = relay._key(receiver.first, receiver.task.task_id)
    path = receipts / relay._receipt_name(key, "incomplete")
    original = path.read_text(encoding="utf-8")
    for delete_pin in (True, False):
        data = json.loads(original)
        if delete_pin:
            del data["input_context"]
        else:
            data["input_context"]["content_sha256"] = "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
        assert (
            reopened._relay.observe_codex_proposal(receiver.first, receiver.task.task_id).state
            == "incomplete"
        )
        assert (
            reopened.reconcile_pending_from_session(
                **receiver_auth,
                admin_token=token,
                expected_wave_id=pending.wave_id,
            ).state
            == "incomplete"
        )
    path.write_text(original, encoding="utf-8")
    assert (
        reopened.reconcile_pending_from_session(
            **receiver_auth,
            admin_token=token,
            expected_wave_id=pending.wave_id,
        ).state
        == "resolved"
    )
    assert counts(core) == {
        "context_revisions": 2,
        "merge_candidates": 0,
        "candidate_verification_jobs": 0,
    }


@pytest.mark.parametrize(
    "pinned_proposal",
    [
        "same-agent",
        "cross-project",
        "wrong-version",
        "wrong-hash",
        "ordinary-context",
        "stored-only",
        "missing-submitted",
        "read-denied",
        "oversize",
    ],
    indirect=True,
)
async def test_invalid_model_review_source_prevents_claim_and_launch(
    pilot,
    proposal_wave,
    pinned_proposal,
    monkeypatch,
):
    core, owner, _, _, _, _, _, _, _ = pilot
    relay, _, reviewer, approvals, captures, _ = proposal_wave
    scenario, queue, receiver, worker, _, context = pinned_proposal
    if scenario == "oversize":
        assert len(context["content"]) < 16000 < len(context["content"].encode("utf-8"))
    if scenario == "read-denied":
        call = relay._call

        def revoke_before_context(actor, operation, **payload):
            if operation == "get_context" and payload["context_id"] == context["id"]:
                owner_grant(core, owner, worker, ())
            return call(actor, operation, **payload)

        monkeypatch.setattr(relay, "_call", revoke_before_context)
    expected = {"read-denied": "forbidden", "oversize": "validation_error"}.get(
        scenario, "relay_boundary"
    )
    with pytest.raises(AgentSyncError) as denied:
        await relay.run_codex_proposal_once(
            receiver.first, receiver.task, admin_token=owner["admin_token"]
        )
    assert denied.value.code == expected
    assert len(approvals) == len(captures) == 1
    state = next(
        row
        for row in core.execute("get_project_state", reviewer)["tasks"]
        if row["id"] == receiver.task.task_id
    )
    assert state["status"] == "pending" and state["version"] == receiver.task.expected_version
    assert (
        queue.owner_observe_pending(owner["project_id"], admin_token=owner["admin_token"]) is None
    )


@pytest.mark.parametrize("pinned_proposal", ["stale-consent"], indirect=True)
async def test_pinned_launch_rejects_consent_for_unpinned_plan(
    pilot, proposal_wave, pinned_proposal
):
    _, owner, _, _, _, _, _, _, _ = pilot
    relay, _, _, approvals, captures, _ = proposal_wave
    _, _, receiver, _, _, _ = pinned_proposal
    token = owner["admin_token"]
    unpinned = relay.preview_codex_proposal(
        receiver.first, replace(receiver.task, input_context=None), admin_token=token
    )
    original = receiver.first.authority

    async def stale_consent(plan):
        assert plan.plan_sha256 != unpinned.plan_sha256
        consent = await original(plan)
        return replace(consent, plan_sha256=unpinned.plan_sha256)

    actor = replace(receiver.first, authority=stale_consent)
    with pytest.raises(AgentSyncError):
        await relay.run_codex_proposal_once(actor, receiver.task, admin_token=token)
    assert len(approvals) == 2 and len(captures) == 1


@pytest.mark.parametrize("pinned_proposal", ["chain"], indirect=True)
async def test_model_review_source_does_not_expand_ancestor_contexts(
    pilot,
    proposal_wave,
    pinned_proposal,
    monkeypatch,
):
    core, owner, _, _, _, tree, _, receipts, _ = pilot
    relay, _, _, approvals, captures, _ = proposal_wave
    _, queue, middle, _, _, ancestor_context = pinned_proposal
    token = owner["admin_token"]
    assert (
        await queue.run_ready_once((middle,), request_id="middle", admin_token=token)
    ).state == "resolved"
    middle_stored = relay.observe_codex_proposal(middle.first, middle.task.task_id)
    third = core.execute("register_agent", {**owner, "name": "Follow-up worker"})
    owner_grant(core, owner, third, ("worker",))
    final, _ = prepare_model_review(
        core,
        owner,
        third,
        middle.first,
        tree["snapshot_id"],
        ProposalContextPin(
            middle.task.task_id,
            middle_stored.context_id,
            middle_stored.context_version,
            middle_stored.content_sha256,
        ),
        "follow-up",
    )
    call = relay._call
    reads = []

    def track_reads(actor, operation, **payload):
        if operation == "get_context":
            assert actor is final.first
            reads.append(payload["context_id"])
        return call(actor, operation, **payload)

    monkeypatch.setattr(relay, "_call", track_reads)
    plan = relay.preview_codex_proposal(final.first, final.task, admin_token=token)
    assert reads == [middle_stored.context_id]
    assert ancestor_context["id"] not in plan.task.instruction
    path = receipts / relay._receipt_name(
        relay._key(middle.first, middle.task.task_id), "incomplete"
    )
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["input_context"]["content_sha256"] = "f" * 64
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(AgentSyncError) as denied:
        await relay.run_codex_proposal_once(final.first, final.task, admin_token=token)
    assert denied.value.code == "relay_boundary"
    assert reads == [middle_stored.context_id, middle_stored.context_id]
    assert len(approvals) == len(captures) == 2


async def test_proposal_queue_requires_current_heartbeat_before_launch(pilot, world, proposal_wave):
    core, owner, _, auth, _, _, _, _, _ = pilot
    relay, item, _, approvals, captures, _ = proposal_wave
    cancel_fixture_load(world)
    queue = RelayQueue(relay)
    token = owner["admin_token"]
    request_id = "heartbeat-wave"
    initial = queue.preview((item,), admin_token=token)
    assert initial.state == "selected" and initial.selection_sha256 is not None
    actor, spec = item.first, item.task
    legacy_actor = [
        actor.profile.project_id,
        actor.profile.session_id,
        actor.agent_id,
        actor.worktree_id,
        actor.expected_head,
        "codex",
        actor.profile.expected_cli_version,
        actor.profile.expected_binary_sha256,
    ]
    legacy_row = [
        "codex-proposal",
        spec.task_id,
        spec.expected_version,
        digest(spec.instruction),
        spec.allowed_paths,
        spec.timeout_seconds,
        True,
        [legacy_actor],
        item.first_capabilities,
    ]
    assert initial.selection_sha256 == digest(["relay-queue-selection-v1", [legacy_row]])
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

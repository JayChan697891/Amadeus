"""Exercise automatic handoff with actual Core, Git and owned protocol fixtures."""

import asyncio
import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import owner_grant
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import (
    accept_fixture_review,
    cancel_fixture_load,
)
from test_codex_proposal_relay_queue import proposal_wave as proposal_wave
from test_task_proposals import world as world

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import (
    HandoffReceiver,
    ProposalHandoff,
    ProposalHandoffRequest,
)
from agentsync.storage.database import connect


@pytest.fixture
async def handoff(pilot, world, proposal_wave):
    core, owner, _, _, producer_task, _, source, receipts, _ = pilot
    relay, item, reviewer, approvals, captures, started = proposal_wave
    cancel_fixture_load(world)
    admin = owner["admin_token"]
    source_outcome = await relay.run_codex_proposal_once(item.first, item.task, admin_token=admin)
    worker = core.execute("register_agent", {**owner, "name": "Proposal receiver"})
    owner_grant(core, owner, worker, ("worker",))
    receiver = HandoffReceiver(
        project_id=owner["project_id"],
        agent_id=worker["agent_id"],
        session_id=worker["session_id"],
        session_token=worker["session_token"],
    )
    request = ProposalHandoffRequest(
        source_task_id=producer_task["id"],
        receiver=receiver,
        request_id="fixture-handoff",
        instruction="Read the pinned input and return an inert review.",
        allowed_paths=("review.md",),
    )

    def build_receiver(receiver, workspace):
        return replace(
            item.first,
            agent_id=receiver.agent_id,
            session_token=receiver.session_token,
            worktree_id=workspace.worktree_id,
            expected_head=workspace.head_sha,
            profile=replace(
                item.first.profile,
                session_id=receiver.session_id,
                root=Path(workspace.path),
            ),
        )

    def complete_producer():
        return accept_fixture_review(
            core, reviewer, producer_task["id"], source_outcome.task_version + 1
        )

    return (
        core,
        ProposalHandoff(core, source.parent, receipts),
        request,
        admin,
        build_receiver,
        complete_producer,
        source_outcome,
        approvals,
        captures,
        started,
    )


async def test_handoff_waits_for_independent_completion(handoff):
    _, coordinator, request, admin, build, complete, source, approvals, captures, _ = handoff
    waiting = asyncio.create_task(
        coordinator.run(
            request,
            admin_token=admin,
            build_receiver=build,
            source_outcome=source,
            wait_seconds=5,
            poll_seconds=0.01,
        )
    )
    await asyncio.sleep(0.05)
    assert not waiting.done()
    assert len(approvals) == len(captures) == 1
    assert complete()["task_verification"] == "unverified"
    result = await waiting
    assert result.wave.state == "resolved"
    assert result.wave.tasks[0].state == "ready_for_review"
    assert result.pin.content_sha256 == source.content_sha256
    assert len(approvals) == len(captures) == 2


def task_ids(core, request):
    return {t["id"] for t in core.execute("list_tasks", request.receiver.authentication())["tasks"]}


def reopened(pilot):
    core, _, _, _, _, _, source, receipts, _ = pilot
    return ProposalHandoff(Core(core.data_dir), source.parent, receipts)


async def test_wait_checkpoint_has_no_downstream_task_or_secrets(handoff, pilot):
    core, flow, request, admin, build, _, source, approvals, captures, _ = handoff
    before = task_ids(core, request)
    for current in (flow, reopened(pilot)):
        result = await current.run(
            request, admin_token=admin, build_receiver=build, source_outcome=source, wait_seconds=0
        )
        assert result.state == "waiting_for_review" and result.task_id is None
    assert task_ids(core, request) == before
    assert len(approvals) == len(captures) == 1
    receipts = "".join(p.read_text() for p in pilot[7].glob("handoff-*.json"))
    assert request.receiver.session_token not in receipts and admin not in receipts
    assert request.instruction not in receipts


async def test_saved_reference_survives_original_producer_expiry(handoff, pilot):
    core, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    await flow.run(
        request, admin_token=admin, build_receiver=build, source_outcome=source, wait_seconds=0
    )
    complete()
    with connect(core.db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (pilot[3]["session_id"],))
    result = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert result.state == "resolved" and result.pin.context_id == source.context_id
    assert len(approvals) == len(captures) == 2


async def test_uncached_expired_producer_is_not_impersonated(handoff, pilot, proposal_wave):
    core, flow, request, admin, build, complete, _, approvals, captures, _ = handoff
    complete()
    before = task_ids(core, request)
    with connect(core.db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (pilot[3]["session_id"],))
    with pytest.raises(AgentSyncError):
        await flow.run(
            request, admin_token=admin, build_receiver=build, source_actor=proposal_wave[1].first
        )
    assert task_ids(core, request) == before
    assert len(approvals) == len(captures) == 1


@pytest.mark.parametrize("operation", ["create_task", "create_worktree"])
async def test_reopen_after_committed_preparation_is_idempotent(
    handoff, pilot, monkeypatch, operation
):
    core, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    complete()
    before = task_ids(core, request)
    execute = core.execute

    def interrupted(name, payload):
        result = execute(name, payload)
        if name == operation:
            raise RuntimeError("Injected host exit after durable Core write")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(core, "execute", interrupted)
        with pytest.raises(RuntimeError):
            await flow.run(request, admin_token=admin, build_receiver=build, source_outcome=source)
    result = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert result.state == "resolved"
    assert task_ids(core, request) == before | {result.task_id}
    with connect(core.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM managed_worktrees WHERE task_id=?", (result.task_id,)
            ).fetchone()[0]
            == 1
        )
    assert len(approvals) == len(captures) == 2


async def test_concurrent_and_repeated_triggers_launch_only_once(handoff, pilot):
    core, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    complete()
    before = task_ids(core, request)
    results = await asyncio.gather(
        *(
            current.run(request, admin_token=admin, build_receiver=build, source_outcome=source)
            for current in (flow, reopened(pilot))
        )
    )
    final = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert final.state == "resolved" and any(r.state == "resolved" for r in results)
    assert task_ids(core, request) == before | {final.task_id}
    assert len(approvals) == len(captures) == 2


@pytest.mark.parametrize("same_agent", [False, True])
async def test_receiver_session_change_cannot_create_a_second_chain(handoff, pilot, same_agent):
    core, flow, request, admin, build, _, source, approvals, captures, _ = handoff
    await flow.run(
        request, admin_token=admin, build_receiver=build, source_outcome=source, wait_seconds=0
    )
    owner = pilot[1]
    member = core.execute("register_agent", {**owner, "name": "Replacement receiver"})
    owner_grant(core, owner, member, ("worker",))
    replacement = HandoffReceiver(
        owner["project_id"], member["agent_id"], member["session_id"], member["session_token"]
    )
    if same_agent:
        replacement = replace(
            request.receiver, session_id=uuid.uuid4().hex, session_token=uuid.uuid4().hex
        )
        with connect(core.db_path) as db:
            db.execute(
                "INSERT INTO sessions SELECT ?,project_id,agent_id,?,created_at,heartbeat_at,expires_at FROM sessions WHERE id=?",
                (
                    replacement.session_id,
                    hashlib.sha256(replacement.session_token.encode()).hexdigest(),
                    request.receiver.session_id,
                ),
            )
    before = task_ids(core, request)
    with pytest.raises(AgentSyncError, match="scope"):
        await reopened(pilot).run(
            replace(request, receiver=replacement),
            admin_token=admin,
            build_receiver=build,
            source_outcome=source,
            wait_seconds=0,
        )
    assert len(approvals) == len(captures) == 1
    assert task_ids(core, request) == before


async def test_wait_budget_expires_without_creating_a_receiver_task(handoff):
    core, flow, request, admin, build, _, source, approvals, captures, _ = handoff
    before = task_ids(core, request)
    with pytest.raises((TimeoutError, AgentSyncError)) as expired:
        await flow.run(
            request,
            admin_token=admin,
            build_receiver=build,
            source_outcome=source,
            wait_seconds=10,
            poll_seconds=0.01,
            budget=0.05,
        )
    if isinstance(expired.value, AgentSyncError):
        assert expired.value.code == "relay_execution_limit"
    assert task_ids(core, request) == before
    assert len(approvals) == len(captures) == 1


async def test_long_legal_paths_keep_bounded_configuration_and_bind_reentry(handoff, pilot):
    _, flow, request, admin, build, _, source, approvals, captures, _ = handoff
    paths = tuple(f"{i}/" + "界" * 140 + ".md" for i in range(8))
    assert len(json.dumps({"allowed_paths": paths}).encode()) > 4096
    request = replace(request, allowed_paths=paths)
    for current in (flow, reopened(pilot)):
        result = await current.run(
            request, admin_token=admin, build_receiver=build, source_outcome=source, wait_seconds=0
        )
        assert result.state == "waiting_for_review"
    assert all(p.stat().st_size < 4096 for p in pilot[7].glob("handoff-*.json"))
    with pytest.raises(AgentSyncError, match="scope"):
        await flow.run(
            replace(request, allowed_paths=("changed.md",)),
            admin_token=admin,
            build_receiver=build,
            wait_seconds=0,
        )
    assert len(approvals) == len(captures) == 1


async def test_dispatch_intent_without_wave_never_retries(handoff, pilot, monkeypatch):
    _, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    complete()

    async def interrupted(*args, **kwargs):
        raise RuntimeError("Injected host exit after dispatch intent")

    with monkeypatch.context() as patch:
        patch.setattr(flow._queue, "run_ready_once", interrupted)
        with pytest.raises(RuntimeError):
            await flow.run(request, admin_token=admin, build_receiver=build, source_outcome=source)
    result = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert result.state == "unknown" and result.wave.state == "not_started"
    assert len(approvals) == len(captures) == 1


async def test_exact_launch_authority_denial_stays_fenced(handoff, pilot):
    _, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    complete()
    decisions = []

    async def deny(plan):
        decisions.append(plan.plan_sha256)
        return None

    def denied_actor(receiver, workspace):
        return replace(build(receiver, workspace), authority=deny)

    first = await flow.run(
        request, admin_token=admin, build_receiver=denied_actor, source_outcome=source
    )
    second = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert first.state == second.state == "incomplete"
    assert len(decisions) == 1 and len(approvals) == len(captures) == 1


async def test_cancellation_after_receiver_start_is_not_retry_permission(handoff, pilot):
    _, flow, request, admin, build, complete, source, approvals, captures, started = handoff
    complete()
    started.clear()
    request = replace(request, instruction="Wait fixture", execution_seconds=10)
    pending = asyncio.create_task(
        flow.run(request, admin_token=admin, build_receiver=build, source_outcome=source)
    )
    await asyncio.wait_for(started.wait(), timeout=10)
    assert len(captures) == 2
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    result = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert result.state == "incomplete"
    assert len(approvals) == len(captures) == 2


async def test_missing_source_proof_cannot_launch_receiver(handoff, pilot, proposal_wave):
    _, flow, request, admin, build, complete, source, approvals, captures, _ = handoff
    complete()
    relay, item, *_ = proposal_wave
    key = relay._key(item.first, request.source_task_id)
    (pilot[7] / relay._receipt_name(key, "proposal-review-submitted")).unlink()
    with pytest.raises(AgentSyncError):
        await flow.run(request, admin_token=admin, build_receiver=build, source_outcome=source)
    result = await reopened(pilot).run(request, admin_token=admin, build_receiver=build)
    assert result.state == "unknown"
    assert len(approvals) == len(captures) == 1

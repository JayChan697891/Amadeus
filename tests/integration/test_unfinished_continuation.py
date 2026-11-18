"""Owned protocol processes and disposable Core/Git; never real clients or model calls."""

import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import owner_grant
from test_candidate_execution import synthetic_backend
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_m4b_workspaces import source_fingerprint
from test_proposal_docker_pipeline import assert_local_container_absent
from test_proposal_docker_pipeline import pipeline_image as pipeline_image
from test_task_proposals import world as world
from verified_flow_process_fixture import emit_proposal, receiver_profile

import agentsync
from agentsync.adapters.approved_launch import LaunchConsent, digest
from agentsync.adapters.codex_invocation import CodexHostProfile
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.continuation import ContinuationRequest, OwnerContinuation
from agentsync.controlled_relay import (
    CodexProposalInput,
    ContinuationPin,
    ControlledRelay,
    RelayActor,
    RelayInput,
)
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import HandoffReceiver, HandoffWorkspace
from agentsync.relay_queue import CodexProposalQueueItem, RelayQueue
from agentsync.storage.database import connect
from agentsync.verification import candidate_executor
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.owner_flow import OwnerCandidateFlow
from agentsync.verification.proposal_staging import OwnerProposalStaging

TOTAL_JSON_LINES = """
import json
import sys

for line in sys.stdin:
    print(json.dumps(total(json.loads(line))), flush=True)
"""


@pytest.fixture
async def unfinished(pilot, world, monkeypatch, request):
    selected = getattr(request, "param", "codex")
    live_checkpoint = selected == "checkpoint_codex"
    verifiable = selected == "verifiable_codex"
    if verifiable or live_checkpoint:
        selected = "codex"
    client, fault = selected if isinstance(selected, tuple) else (selected, None)
    proposal_path = "solution.py" if verifiable else "answer.py"
    core, owner, member, auth, task, tree, source, receipts, profile = pilot
    cancel_fixture_load(world)
    calls, approvals, captures, published = [], [], [], []
    original_start = CapturedProcess.start
    relay = ControlledRelay(core, source.parent, receipts)
    key = relay._task_receipt_key(owner["project_id"], task["id"])
    partial = "def total(values):\n    # UNFINISHED_CONTEXT_SENTINEL\n    return None\n"
    final = "def total(values):\n    return sum(values)\n"
    if verifiable:
        partial += TOTAL_JSON_LINES
        final += TOTAL_JSON_LINES

    async def approve(plan):
        approvals.append(plan)
        return LaunchConsent(
            "fixture-" + str(len(approvals)), plan.plan_sha256, time.time() + 30, True, True
        )

    async def capture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        prompt = argv[-1] if "--mode" in argv else stdin_text
        calls.append(prompt)
        contract, _ = json.JSONDecoder().raw_decode(prompt.split("Host contract: ", 1)[1])
        if Path(cwd) == Path(tree["path"]):
            if live_checkpoint:
                # Owned Python emits a complete protocol draft before exiting;
                # it is not a real client/model fixture.
                events = [
                    {"type": "thread.started", "thread_id": "live-unfinished-fixture"},
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "draft",
                            "type": "agent_message",
                            "text": json.dumps(
                                {
                                    "phase": "checkpoint",
                                    "files": [{"path": proposal_path, "content": partial}],
                                }
                            ),
                        },
                    },
                ]
                process = await original_start(
                    (
                        sys.executable,
                        "-I",
                        "-B",
                        "-c",
                        "import sys,time;print(sys.stdin.read(),flush=True,end='');time.sleep(0.5);sys.exit(17)",
                    ),
                    cwd=cwd,
                    stdin_text="\n".join(map(json.dumps, events)) + "\n",
                    timeout_seconds=timeout_seconds,
                    output_limit=output_limit,
                    env=env,
                )
                captures.append(process)
                return process
            current = next(
                row for row in core.execute("list_tasks", auth)["tasks"] if row["id"] == task["id"]
            )
            published.append(
                relay.publish_progress_checkpoint(
                    actor,
                    task["id"],
                    expected_version=current["version"],
                    allowed_paths=(proposal_path,),
                    proposal_json=json.dumps(
                        {"files": [{"path": proposal_path, "content": partial}]}
                    ),
                    request_id="unfinished-checkpoint",
                )
            )
            program, payload = "raise SystemExit(17)", ""
        else:
            assert contract["mode"] == "proposal_continuation"
            assert "UNFINISHED_CONTEXT_SENTINEL" in prompt
            assert contract["continuation"]["content_sha256"] == published[0]["content_sha256"]
            process = await emit_proposal(
                original_start,
                proposal_path,
                final,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                output_limit=output_limit,
                env=env,
                client=client,
                fault=fault,
            )
            captures.append(process)
            return process
        process = await original_start(
            (sys.executable, "-I", "-c", program),
            cwd=cwd,
            stdin_text=payload,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captures.append(process)
        return process

    monkeypatch.setattr(CapturedProcess, "start", classmethod(capture))
    actor = RelayActor(
        member["agent_id"],
        member["session_token"],
        profile,
        tree["worktree_id"],
        tree["head_sha"],
        {},
        approve,
    )
    item = CodexProposalQueueItem(
        actor,
        CodexProposalInput(
            task["id"],
            task["version"],
            "Continue the implementation.",
            (proposal_path,),
            10,
            True,
            checkpoint_completed_proposal=live_checkpoint,
        ),
    )
    queue = RelayQueue(relay)
    outcome = await queue.run_ready_once(
        (item,), request_id="failed-source", admin_token=owner["admin_token"]
    )
    assert outcome.state == "incomplete"
    if live_checkpoint:
        published.append(relay._read_receipt(key, "proposal-progress", durable=True))
    observed = relay.owner_inspect_attempts(
        owner["project_id"], task["id"], admin_token=owner["admin_token"]
    )[0]
    assert observed.parent_ended is True and observed.exit_code == 17
    failed = relay._confirmed_failure(owner["project_id"], task["id"])
    assert failed is not None
    child = core.execute(
        "create_task",
        {
            **auth,
            "title": "After unfinished implementation",
            "dependencies": [task["id"]],
            "request_id": "dependent",
        },
    )
    worker = core.execute(
        "register_agent", {**owner, "name": "Continuation receiver", "capabilities": ["code"]}
    )
    owner_grant(core, owner, worker, ("worker",))
    receiver = HandoffReceiver(
        owner["project_id"], worker["agent_id"], worker["session_id"], worker["session_token"]
    )
    progress = published[0]
    flow = OwnerContinuation(core, source.parent, receipts)
    pin = flow.pin_failed_progress(
        owner["project_id"],
        task["id"],
        context_id=progress["context_id"],
        context_version=progress["context_version"],
        content_sha256=progress["content_sha256"],
        admin_token=owner["admin_token"],
    )
    request = ContinuationRequest(
        receiver,
        pin,
        "Finish the pinned unfinished total implementation.",
        (proposal_path,),
        required_capabilities=("code",),
        execution_seconds=10,
    )

    def build(receiver, workspace):
        return replace(
            actor,
            agent_id=receiver.agent_id,
            session_token=receiver.session_token,
            worktree_id=workspace.worktree_id,
            expected_head=workspace.head_sha,
            profile=receiver_profile(client, profile, receiver, workspace),
        )

    try:
        yield flow, request, build, child, calls, approvals, published[0], key
    finally:
        for process in captures:
            await process.cancel()
            assert (await process.snapshot()).parent_ended is True


@pytest.mark.parametrize(
    "unfinished", ["codex", "claude", "cursor", "checkpoint_codex"], indirect=True
)
async def test_confirmed_failure_continues_real_progress_and_transfers_graph(unfinished, pilot):
    flow, request, build, child, calls, approvals, progress, key = unfinished
    core, owner, _, auth, task, tree, source, receipts, _ = pilot
    before = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    source_receipts = {p.name: p.read_bytes() for p in receipts.glob("relay-" + key + "*.json")}
    plan = flow.preview(request, admin_token=owner["admin_token"])
    # Recovery authenticates the owner and receiver, never the expired producer.
    with connect(core.db_path) as db:
        db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (auth["session_id"],))
    result = await flow.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    assert result["state"] == "resolved" and result["task_status"] == "review"
    assert result["publication"]["verification"] == "unverified"
    state = {
        row["id"]: row
        for row in core.execute("list_tasks", request.receiver.authentication())["tasks"]
    }
    assert state[task["id"]]["status"] == "failed"
    assert state[child["id"]]["dependencies"] == [result["task_id"]]
    assert state[child["id"]]["version"] == child["version"] + 1
    assert state[result["task_id"]]["dependencies"] == []
    stored = core.execute(
        "get_context",
        {
            **request.receiver.authentication(),
            "context_id": result["publication"]["context_id"],
            "version": 1,
        },
    )
    assert (
        "return sum(values)" in stored["content"]
        and stored["author_agent_id"] == request.receiver.agent_id
    )
    assert len(calls) == len(approvals) == 2
    restarted = OwnerContinuation(Core(core.data_dir), source.parent, receipts)
    again = await restarted.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    assert again == result and len(calls) == 2
    assert {name: (receipts / name).read_bytes() for name in source_receipts} == source_receipts
    assert [source_fingerprint(path) for path in (source, Path(tree["path"]))] == before
    public = json.dumps(result) + "".join(
        p.read_text() for p in receipts.glob("continuation-*.json")
    )
    assert owner["admin_token"] not in public and request.receiver.session_token not in public
    assert progress["content_sha256"] == request.source.content_sha256


async def run_to_continuation_review(unfinished, owner):
    flow, request, build, *_ = unfinished
    actors = []

    def capture_receiver(receiver, workspace):
        actor = build(receiver, workspace)
        actors.append(actor)
        return actor

    plan = flow.preview(request, admin_token=owner["admin_token"])
    continuation = await flow.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=capture_receiver,
    )
    assert continuation["state"] == "resolved" and continuation["task_status"] == "review"
    (actor,) = actors
    return continuation, actor


@pytest.mark.parametrize("verification", ["synthetic", "docker"])
@pytest.mark.parametrize("unfinished", ["verifiable_codex"], indirect=True)
async def test_continued_task_completes_with_distinct_reviewer(
    unfinished, pilot, monkeypatch, request, verification
):
    image = (
        request.getfixturevalue("pipeline_image")
        if verification == "docker"
        else "sha256:" + "b" * 64
    )
    flow, continuation_request, _, dependent, calls, approvals, _, _ = unfinished
    core, owner, _, auth, source_task, _, source, receipts, _ = pilot
    continuation, actor = await run_to_continuation_review(unfinished, owner)
    receiver_id = continuation["task_id"]
    reopened = Core(core.data_dir)
    relay = ControlledRelay(reopened, source.parent, receipts)
    observed = relay.observe_continuation_proposal_review(
        actor,
        receiver_id,
        continuation=continuation_request,
        admin_token=owner["admin_token"],
    )
    assert observed.state == "submitted_for_review"
    assert observed.review_task_version == continuation["task_version"]
    assert observed.context_id == continuation["publication"]["context_id"]
    assert observed.verification == "unverified"
    assert relay.observe_codex_proposal_review(actor, receiver_id).state == "incomplete"

    stager = reopened.execute("register_agent", {**owner, "name": "Staging worker"})
    owner_grant(reopened, owner, stager, ("worker",))
    staging = {
        "continuation": continuation_request,
        "admin_token": owner["admin_token"],
        "staging_session_id": stager["session_id"],
        "staging_session_token": stager["session_token"],
    }
    preview = relay.preview_continuation_proposal_staging(actor, receiver_id, **staging)
    assert preview["plan"]["task_id"] == receiver_id
    with pytest.raises(AgentSyncError):
        relay.stage_continuation_proposal_once(
            actor,
            receiver_id,
            **staging,
            expected_plan_sha256="0" * 64,
        )
    staged = relay.stage_continuation_proposal_once(
        actor,
        receiver_id,
        **staging,
        expected_plan_sha256=preview["plan_sha256"],
    )
    assert staged["task_id"] == receiver_id and staged["execution_started"] is False
    with pytest.raises(AgentSyncError) as staging_replay:
        relay.stage_continuation_proposal_once(
            actor,
            receiver_id,
            **staging,
            expected_plan_sha256=preview["plan_sha256"],
        )
    assert staging_replay.value.code == "proposal_staging_exists"

    executions = []

    def fixture_verifier(source_bytes, **options):
        # This deterministic substitute checks the exported bytes and the Core wiring.
        # It does not run the candidate or use Docker.
        expected = "def total(values):\n    return sum(values)\n" + TOTAL_JSON_LINES
        assert source_bytes == expected.encode()
        executions.append(options["commit_sha"])
        return synthetic_backend(source_bytes, **options)

    if verification == "synthetic":
        monkeypatch.setattr(candidate_executor, "verify_python_json_lines", fixture_verifier)
    policy = DockerProfile(image, (JsonCase([2, 3], 5), JsonCase([-4, 1], -3)))
    jobs = CandidateVerificationJobs(reopened)
    job = jobs.enqueue(
        **owner,
        candidate_id=staged["candidate_id"],
        expected_candidate_sha=staged["candidate_sha"],
        profile=policy,
        request_id="continued-candidate",
    )
    candidate = OwnerCandidateFlow(reopened)
    execution = candidate.start_once(
        **owner,
        job_id=job["id"],
        expected_job_version=job["version"],
        expected_metadata_sha256=job["metadata_sha256"],
        profile=policy,
    )
    assert execution["execution_assessment"] == "passed"
    result = execution["execution"]["result"]
    if verification == "docker":
        assert result["backend"] == "local-linux-docker" and result["passed_case_count"] == 2
        assert result["cleanup_confirmed"] is True
        assert result["isolation"]["checks"] and all(result["isolation"]["checks"].values())
        assert_local_container_absent(result["container_id"])
    assert [row["id"] for row in reopened.execute("list_tasks", auth)["tasks"]].count(
        receiver_id
    ) == 1
    claim = {
        **auth,
        "task_id": dependent["id"],
        "expected_version": dependent["version"] + 1,
        "request_id": "claim-after-continuation",
    }
    with pytest.raises(AgentSyncError) as waiting:
        reopened.execute("claim_task", claim)
    assert waiting.value.code == "dependencies_incomplete"

    reviewer = reopened.execute("register_agent", {**owner, "name": "Independent reviewer"})
    owner_grant(reopened, owner, reviewer, ("reviewer",))
    assert reviewer["agent_id"] not in {actor.agent_id, stager["agent_id"]}
    completion = {
        **owner,
        "session_id": reviewer["session_id"],
        "session_token": reviewer["session_token"],
        "task_id": receiver_id,
        "expected_version": observed.review_task_version,
        "job_id": job["id"],
        "execution_id": execution["execution_id"],
        "expected_execution_revision": execution["execution"]["revision"],
        "request_id": "complete-continued-work",
        "profile": policy,
    }
    completed = candidate.complete_once(**completion)
    assert completed["task_id"] == receiver_id and completed["task_verification"] == "verified"

    fresh = Core(core.data_dir)
    assert OwnerCandidateFlow(fresh).complete_once(**completion) == completed
    states = {row["id"]: row for row in fresh.execute("list_tasks", auth)["tasks"]}
    assert states[receiver_id]["status"] == "completed"
    assert states[receiver_id]["task_verification"] == "verified"
    assert states[source_task["id"]]["status"] == "failed"
    assert states[source_task["id"]]["task_verification"] == "unverified"
    assert states[dependent["id"]]["dependencies"] == [receiver_id]
    assert fresh.execute("claim_task", claim)["status"] == "claimed"
    assert CandidateVerificationJobs(fresh).get(**owner, job_id=job["id"])["status"] != "queued"
    with connect(fresh.db_path) as db:
        assert (
            db.execute(
                "SELECT count(*) FROM candidate_executions WHERE project_id=? AND job_id=?",
                (owner["project_id"], job["id"]),
            ).fetchone()[0]
            == 1
        )
    assert len(executions) == (1 if verification == "synthetic" else 0)
    assert len(calls) == len(approvals) == 2
    reopened_continuation = flow.status(
        owner["project_id"],
        continuation_request.source.launch_sha256,
        admin_token=owner["admin_token"],
    )
    assert reopened_continuation["task_id"] == receiver_id
    assert reopened_continuation["publication"]["verification"] == "unverified"

    evidence = os.environ.get("AGENTSYNC_PROPOSAL_PIPELINE_EVIDENCE_DIR")
    if verification == "docker" and evidence:
        output = Path(evidence)
        assert output.is_absolute() and not output.is_symlink()
        output.mkdir(parents=True, exist_ok=True)
        with (output / "continuation-verified.json").open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "model_boundary": "known local Python protocol fixture; zero model calls",
                    "model_calls": 0,
                    "same_core": True,
                    "receiver_task_id": receiver_id,
                    "source_task_status": states[source_task["id"]]["status"],
                    "receiver_task_status": states[receiver_id]["status"],
                    "receiver_task_verification": states[receiver_id]["task_verification"],
                    "publication_verification": reopened_continuation["publication"][
                        "verification"
                    ],
                    "candidate_sha": staged["candidate_sha"],
                    "execution": execution,
                    "completion": completed,
                },
                stream,
                indent=2,
            )


@pytest.mark.parametrize("unfinished", ["verifiable_codex"], indirect=True)
@pytest.mark.parametrize(
    "fault",
    [
        "publisher",
        "version",
        "marker",
        "mode",
        "terminal_launch",
        "selection",
        "unknown_wave",
        "unknown_source",
        "foreign_request",
    ],
)
async def test_continuation_staging_rechecks_approved_binding(unfinished, pilot, fault):
    _, continuation_request, _, _, calls, approvals, _, source_key = unfinished
    core, owner, source_actor, _, _, _, source, receipts, _ = pilot
    continuation, actor = await run_to_continuation_review(unfinished, owner)
    task_id = continuation["task_id"]
    relay = ControlledRelay(core, source.parent, receipts)
    stager = core.execute("register_agent", {**owner, "name": "Staging worker"})
    owner_grant(core, owner, stager, ("worker",))
    staging = {
        "continuation": continuation_request,
        "admin_token": owner["admin_token"],
        "staging_session_id": stager["session_id"],
        "staging_session_token": stager["session_token"],
    }
    preview = relay.preview_continuation_proposal_staging(actor, task_id, **staging)
    prefix = "continuation-" + digest(
        [owner["project_id"], continuation_request.source.launch_sha256]
    )

    if fault in {"publisher", "version", "marker"}:
        with connect(core.db_path) as db:
            if fault == "publisher":
                db.execute(
                    "UPDATE context_revisions SET author_agent_id=? WHERE context_id=? AND version=1",
                    (source_actor["agent_id"], continuation["publication"]["context_id"]),
                )
            elif fault == "version":
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (task_id,))
            else:
                db.execute(
                    "UPDATE tasks SET result=? WHERE id=?",
                    (
                        "Controlled Codex proposal stored as inert data. Owner staging and independent verification pending.",
                        task_id,
                    ),
                )
    elif fault == "unknown_wave":
        queue = RelayQueue(relay)
        wave_key = queue._key(actor, prefix + "-wave")
        with connect(queue._journal._path) as db:
            row = db.execute(
                "UPDATE relay_waves SET state='admitted',results_json=NULL WHERE request_key=?",
                (wave_key,),
            )
            assert row.rowcount == 1
    elif fault == "foreign_request":
        other = core.execute(
            "create_project", {"name": "Foreign project", "root_path": str(source)}
        )
        staging["continuation"] = replace(
            continuation_request,
            receiver=replace(continuation_request.receiver, project_id=other["project_id"]),
        )
    else:
        terminal_key = relay._key(actor, task_id)
        file, field, value = {
            "mode": (f"relay-{terminal_key}-incomplete.json", "mode", "codex_proposal"),
            "terminal_launch": (
                f"relay-{terminal_key}-first-observed.json",
                "launch_request_sha256",
                "f" * 64,
            ),
            "selection": (prefix + "-dispatch.json", "selection_sha256", "f" * 64),
            "unknown_source": (f"relay-{source_key}-first-stopped.json", "parent_ended", False),
        }[fault]
        receipt = receipts / file
        record = json.loads(receipt.read_bytes())
        record[field] = value
        receipt.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(AgentSyncError) as rejected:
        relay.stage_continuation_proposal_once(
            actor,
            task_id,
            **staging,
            expected_plan_sha256=preview["plan_sha256"],
        )
    assert rejected.value.code == "relay_boundary"
    assert OwnerProposalStaging(core).status(**owner, task_id=task_id)["state"] == "not_started"
    with connect(core.db_path) as db:
        for table in ("merge_candidates", "candidate_verification_jobs", "candidate_executions"):
            assert db.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    assert len(calls) == len(approvals) == 2


async def test_continued_proposal_without_solution_is_review_only(unfinished, pilot):
    _, continuation_request, _, _, calls, _, _, _ = unfinished
    core, owner, _, _, _, _, source, receipts, _ = pilot
    continuation, actor = await run_to_continuation_review(unfinished, owner)
    task_id = continuation["task_id"]
    relay = ControlledRelay(core, source.parent, receipts)
    state = relay.observe_continuation_proposal_review(
        actor,
        task_id,
        continuation=continuation_request,
        admin_token=owner["admin_token"],
    )
    assert state.state == "submitted_for_review" and state.verification == "unverified"
    with pytest.raises(AgentSyncError) as rejected:
        relay.preview_continuation_proposal_staging(
            actor,
            task_id,
            continuation=continuation_request,
            admin_token=owner["admin_token"],
            staging_session_id=actor.profile.session_id,
            staging_session_token=actor.session_token,
        )
    assert rejected.value.code == "verification_input_invalid"
    assert OwnerProposalStaging(core).status(**owner, task_id=task_id)["state"] == "not_started"
    assert len(calls) == 2


@pytest.mark.parametrize(
    "fault",
    [
        "parent_unknown",
        "missing_capture",
        "wrong_launch",
        "wrong_progress",
        "wrong_author",
        "wrong_version",
        "wrong_owner",
    ],
)
async def test_untrusted_or_uncertain_source_cannot_dispatch(unfinished, pilot, fault):
    flow, request, build, _, calls, _, _, key = unfinished
    core, owner, _, _, task, _, _, receipts, _ = pilot
    if fault in ("parent_unknown", "wrong_launch"):
        path = receipts / f"relay-{key}-first-stopped.json"
        data = json.loads(path.read_bytes())
        data["parent_ended" if fault == "parent_unknown" else "launch_request_sha256"] = (
            False if fault == "parent_unknown" else "f" * 64
        )
        path.write_text(json.dumps(data))
    elif fault == "missing_capture":
        with connect(core.db_path) as db:
            db.execute(
                "DELETE FROM idempotency WHERE operation='renew_lease' AND request_id=?",
                (f"relay:{key}:first:capture",),
            )
    elif fault == "wrong_author":
        with connect(core.db_path) as db:
            db.execute(
                "UPDATE context_revisions SET author_agent_id=? WHERE context_id=?",
                (request.receiver.agent_id, request.source.context_id),
            )
    elif fault in ("wrong_progress", "wrong_version"):
        source = replace(
            request.source,
            **(
                {"content_sha256": "f" * 64}
                if fault == "wrong_progress"
                else {"source_task_version": request.source.source_task_version + 1}
            ),
        )
        request = replace(request, source=source)
    token = "wrong" if fault == "wrong_owner" else owner["admin_token"]
    with pytest.raises(AgentSyncError):
        flow.preview(request, admin_token=token)
    assert len(calls) == 1
    if fault in ("parent_unknown", "missing_capture", "wrong_launch"):
        pending = flow._queue.owner_observe_pending(
            owner["project_id"], admin_token=owner["admin_token"]
        )
        outcome = flow._queue.reconcile_pending_from_session(
            owner["project_id"],
            session_id=request.receiver.session_id,
            session_token=request.receiver.session_token,
            admin_token=owner["admin_token"],
            expected_wave_id=pending.wave_id,
        )
        assert outcome.state == "incomplete"
    with connect(core.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM owner_idempotency WHERE operation='continue_failed_task'"
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute("SELECT status FROM tasks WHERE id=?", (task["id"],)).fetchone()[0]
            == "running"
        )


async def test_dispatch_intent_without_wave_remains_unknown(unfinished, pilot, monkeypatch):
    flow, request, build, _, calls, _, _, _ = unfinished
    core, owner, _, _, _, _, source, receipts, _ = pilot
    plan = flow.preview(request, admin_token=owner["admin_token"])
    dispatch = []

    async def interrupted(*args, **kwargs):
        dispatch.append((args, kwargs))
        raise RuntimeError("Owned interruption after permanent dispatch intent")

    monkeypatch.setattr(flow._queue, "run_ready_once", interrupted)
    with pytest.raises(RuntimeError):
        await flow.run_once(
            request,
            admin_token=owner["admin_token"],
            expected_plan_sha256=plan["plan_sha256"],
            build_receiver=build,
        )
    restarted = OwnerContinuation(Core(core.data_dir), source.parent, receipts)
    result = await restarted.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    assert result["state"] == "unknown" and len(calls) == 1
    item = dispatch[0][0][0][0]
    canonical = dispatch[0][1]["request_id"]
    for wave_request in (canonical, "alternate-continuation-wave"):
        with pytest.raises(AgentSyncError):
            await restarted._queue.run_ready_once(
                (item,), request_id=wave_request, admin_token=owner["admin_token"]
            )
        with pytest.raises(AgentSyncError):
            await restarted._relay.run_continuation_once(
                item.first,
                item.task,
                admin_token=owner["admin_token"],
                _wave_key=restarted._queue._key(item.first, wave_request),
            )
    ordinary = CodexProposalInput(
        item.task.task_id, item.task.expected_version, "ordinary bypass", item.task.allowed_paths
    )
    with pytest.raises(AgentSyncError):
        await restarted._queue.run_ready_once(
            (CodexProposalQueueItem(item.first, ordinary),),
            request_id="ordinary-bypass",
            admin_token=owner["admin_token"],
        )
    with pytest.raises(AgentSyncError):
        await restarted._relay.run_codex_proposal_once(
            item.first, ordinary, admin_token=owner["admin_token"]
        )
    member, tree, profile = pilot[2], pilot[5], pilot[8]
    other = replace(
        item.first,
        agent_id=member["agent_id"],
        session_token=member["session_token"],
        profile=profile,
        worktree_id=tree["worktree_id"],
        expected_head=tree["head_sha"],
    )
    two_leg = RelayInput(
        item.task.task_id,
        item.task.expected_version,
        request.source.context_id,
        request.source.context_version,
        request.source.content_sha256,
        "one",
        "two",
        "one",
        "two",
    )
    with pytest.raises(AgentSyncError) as denied:
        await restarted._relay.run_once(
            item.first, other, two_leg, admin_token=owner["admin_token"]
        )
    assert denied.value.code == "continuation_boundary"
    empty = receipts.parent / "empty-continuation-receipts"
    empty.mkdir()
    wrong_root = OwnerContinuation(Core(core.data_dir), source.parent, empty)
    with pytest.raises(AgentSyncError):
        wrong_root.status(
            owner["project_id"], request.source.launch_sha256, admin_token=owner["admin_token"]
        )
    assert flow._relay._continuation_start is None
    assert (
        restarted._queue.owner_observe_pending(
            owner["project_id"], admin_token=owner["admin_token"]
        )
        is None
    )
    assert len(calls) == 1


async def test_exact_plan_and_approval_time_source_recheck(unfinished, pilot):
    flow, request, build, _, calls, approvals, _, _ = unfinished
    core, owner, _, _, _, _, _, _, _ = pilot
    plan = flow.preview(request, admin_token=owner["admin_token"])
    with pytest.raises(AgentSyncError):
        await flow.run_once(
            request,
            admin_token=owner["admin_token"],
            expected_plan_sha256="f" * 64,
            build_receiver=build,
        )
    assert len(calls) == 1

    def changed_build(receiver, workspace):
        actor = build(receiver, workspace)

        async def approval(plan):
            consent = await actor.authority(plan)
            with connect(core.db_path) as db:
                db.execute(
                    "UPDATE context_revisions SET content='changed' WHERE context_id=?",
                    (request.source.context_id,),
                )
            return consent

        return replace(actor, authority=approval)

    result = await flow.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=changed_build,
    )
    assert result["state"] == "incomplete" and len(calls) == 1 and len(approvals) == 2


async def test_concurrent_requests_consume_one_new_dispatch(unfinished, pilot):
    flow, request, build, _, calls, _, _, _ = unfinished
    owner = pilot[1]
    plan = flow.preview(request, admin_token=owner["admin_token"])
    kwargs = dict(
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    results = await asyncio.gather(
        flow.run_once(request, **kwargs), flow.run_once(request, **kwargs)
    )
    assert any(row["state"] == "resolved" for row in results)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "unfinished", [("codex", "codex-tool"), ("claude", "tool-block")], indirect=True
)
async def test_continuation_keeps_known_tool_event_rejection(unfinished, pilot):
    flow, request, build, _, calls, _, _, _ = unfinished
    owner = pilot[1]
    plan = flow.preview(request, admin_token=owner["admin_token"])
    result = await flow.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    assert result["state"] == "incomplete" and result["publication"] is None
    assert len(calls) == 2


async def test_changed_graph_rejects_previously_approved_plan(unfinished, pilot):
    flow, request, build, child, calls, _, _, _ = unfinished
    core, owner, _, auth, task, _, _, _, _ = pilot
    plan = flow.preview(request, admin_token=owner["admin_token"])
    added = core.execute(
        "create_task",
        {
            **auth,
            "title": "Another pending consumer",
            "dependencies": [task["id"]],
            "request_id": "extra-dependent",
        },
    )
    with pytest.raises(AgentSyncError):
        await flow.run_once(
            request,
            admin_token=owner["admin_token"],
            expected_plan_sha256=plan["plan_sha256"],
            build_receiver=build,
        )
    state = {row["id"]: row for row in core.execute("list_tasks", auth)["tasks"]}
    assert state[child["id"]]["dependencies"] == state[added["id"]]["dependencies"] == [task["id"]]
    assert len(calls) == 1


async def test_preparation_checkpoint_resumes_without_second_source_attempt(
    unfinished, pilot, monkeypatch
):
    flow, request, build, _, calls, _, _, _ = unfinished
    core, owner, _, _, _, _, source, receipts, _ = pilot
    plan = flow.preview(request, admin_token=owner["admin_token"])
    execute = core.execute

    def interrupted(operation, payload):
        value = execute(operation, payload)
        if operation == "create_worktree":
            raise RuntimeError("Owned interruption after committed worktree")
        return value

    with monkeypatch.context() as patch:
        patch.setattr(core, "execute", interrupted)
        with pytest.raises(RuntimeError):
            await flow.run_once(
                request,
                admin_token=owner["admin_token"],
                expected_plan_sha256=plan["plan_sha256"],
                build_receiver=build,
            )
    restarted = OwnerContinuation(Core(core.data_dir), source.parent, receipts)
    result = await restarted.run_once(
        request,
        admin_token=owner["admin_token"],
        expected_plan_sha256=plan["plan_sha256"],
        build_receiver=build,
    )
    assert result["state"] == "resolved" and len(calls) == 2


async def _continuation_host(phase, fixture):
    """Child-only driver that uses the same installed package and durable fixture."""
    assert Path(agentsync.__file__).resolve() == Path(fixture["import_origin"])
    request = fixture["request"]
    request["receiver"] = HandoffReceiver(**request["receiver"])
    request["source"] = ContinuationPin(**request["source"])
    for key in ("allowed_paths", "required_capabilities"):
        request[key] = tuple(request[key])
    request = ContinuationRequest(**request)
    core = Core(fixture["data_dir"])
    flow = OwnerContinuation(core, Path(fixture["scratch"]), Path(fixture["receipts"]))
    execute = core.execute
    original_start = CapturedProcess.start
    run_receiver = flow._relay.run_continuation_once
    record_wave = flow._queue._journal.record
    worktree = None
    receiver_wave = None
    receiver_snapshot = None
    builds, approvals, captures = [], [], []

    def exit_at_checkpoint():
        assert worktree is not None and not captures and not approvals
        print(json.dumps({"pid": os.getpid(), "worktree": worktree}), flush=True)
        os._exit(73)

    def observe_worktree(operation, payload):
        nonlocal worktree
        value = execute(operation, payload)
        if operation == "create_worktree":
            worktree = [payload["task_id"], value["worktree_id"], value["head_sha"]]
            if phase == "prepared":
                exit_at_checkpoint()
        return value

    async def exit_after_intent(*_args, **_kwargs):
        exit_at_checkpoint()

    async def approve(plan):
        assert phase in {"resume", "review-submitted"}
        approvals.append(plan.plan_sha256)
        return LaunchConsent(
            "continuation-host-fixture-" + plan.plan_sha256,
            plan.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    def build(receiver, workspace):
        nonlocal receiver_wave
        assert phase != "prepared" and receiver == request.receiver
        builds.append([workspace.task_id, workspace.worktree_id, workspace.head_sha])
        profile = CodexHostProfile(
            receiver.project_id,
            receiver.session_id,
            Path(fixture["executable"]),
            workspace.path,
            fixture["binary_sha256"],
            expected_cli_version=fixture["cli_version"],
        )
        actor = RelayActor(
            receiver.agent_id,
            receiver.session_token,
            profile,
            workspace.worktree_id,
            workspace.head_sha,
            {},
            approve,
        )
        if phase == "review-submitted":
            prefix = "continuation-" + digest([receiver.project_id, request.source.launch_sha256])
            receiver_wave = flow._queue._key(actor, prefix + "-wave")
        return actor

    async def capture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert phase in {"resume", "review-submitted"}
        assert str(cwd) != fixture["source_worktree"] and env == {}
        contract, _ = json.JSONDecoder().raw_decode(stdin_text.split("Host contract: ", 1)[1])
        assert contract["mode"] == "proposal_continuation"
        assert contract["continuation"]["content_sha256"] == request.source.content_sha256
        assert "UNFINISHED_CONTEXT_SENTINEL" in stdin_text
        (path,) = request.allowed_paths
        content = "def total(values):\n    return sum(values)\n"
        if path == "solution.py":
            content += TOTAL_JSON_LINES
        process = await emit_proposal(
            original_start,
            path,
            content,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captures.append(process)
        return process

    async def observe_receiver_end(*args, **kwargs):
        nonlocal receiver_snapshot
        outcome = await run_receiver(*args, **kwargs)
        (process,) = captures
        receiver_snapshot = await process.snapshot()
        return outcome

    def exit_before_receiver_wave_result(project_key, wave_id, **result):
        if wave_id != receiver_wave:
            return record_wave(project_key, wave_id, **result)
        assert worktree is not None and receiver_snapshot is not None
        assert project_key == digest(request.receiver.project_id)
        task_id = worktree[0]
        assert result == {
            "incomplete": False,
            "results": [{"task_id": task_id, "state": "ready_for_review"}],
        }
        assert receiver_snapshot.parent_ended is True and receiver_snapshot.exit_code == 0
        assert receiver_snapshot.state == "exited" and len(approvals) == len(captures) == 1
        attempt, _ = flow._relay.owner_inspect_attempts(
            request.receiver.project_id, task_id, admin_token=fixture["admin_token"]
        )
        assert (
            attempt.state == "terminal_recorded"
            and attempt.status == "continuation_proposal_received"
        )
        assert attempt.parent_ended is True and attempt.exit_code == 0
        saved = flow.status(
            request.receiver.project_id,
            request.source.launch_sha256,
            admin_token=fixture["admin_token"],
        )
        assert saved["task_id"] == task_id and saved["task_status"] == "review"
        assert (
            saved["state"] == "incomplete" and saved["publication"]["verification"] == "unverified"
        )
        print(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "worktree": worktree,
                    "wave_id": wave_id,
                    "approvals": len(approvals),
                    "launches": len(captures),
                    "receiver_terminal": {
                        "state": attempt.state,
                        "status": attempt.status,
                        "parent_ended": attempt.parent_ended,
                        "exit_code": attempt.exit_code,
                    },
                }
            ),
            flush=True,
        )
        os._exit(73)

    args = dict(
        admin_token=fixture["admin_token"],
        expected_plan_sha256=fixture["plan_sha256"],
        build_receiver=build,
    )
    with (
        patch.object(core, "execute", observe_worktree),
        patch.object(CapturedProcess, "start", classmethod(capture)),
    ):
        if phase == "dispatch-intent":
            with patch.object(flow._queue, "run_ready_once", exit_after_intent):
                await flow.run_once(request, **args)
            raise AssertionError("The durable dispatch checkpoint was not reached")
        try:
            if phase == "review-submitted":
                with (
                    patch.object(flow._relay, "run_continuation_once", observe_receiver_end),
                    patch.object(flow._queue._journal, "record", exit_before_receiver_wave_result),
                ):
                    await flow.run_once(request, **args)
                raise AssertionError("The durable receiver review checkpoint was not reached")
            outcome = await flow.run_once(request, **args)
        finally:
            for process in captures:
                await process.cancel()
                assert (await process.snapshot()).parent_ended is True
    assert phase == "resume", "The prepared checkpoint was not reached"
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "outcome": outcome,
                "builds": builds,
                "approvals": len(approvals),
                "launches": len(captures),
            }
        )
    )


def _continuation_host_launcher(flow, request, pilot):
    core, owner, _, _, _, tree, source, receipts, profile = pilot
    plan = flow.preview(request, admin_token=owner["admin_token"])
    fixture = {
        "data_dir": str(core.data_dir),
        "scratch": str(source.parent),
        "receipts": str(receipts),
        "admin_token": owner["admin_token"],
        "plan_sha256": plan["plan_sha256"],
        "request": asdict(request),
        "executable": str(profile.executable),
        "binary_sha256": profile.expected_binary_sha256,
        "cli_version": profile.expected_cli_version,
        "source_worktree": tree["path"],
        "import_origin": str(Path(agentsync.__file__).resolve()),
    }
    driver = (
        "import asyncio,json,runpy,sys; from pathlib import Path; "
        "path=Path(sys.argv[1]); sys.path[:0]=[str(path.parent),str(path.parent.parent)]; "
        "start=runpy.run_path(str(path))['_continuation_host']; "
        "asyncio.run(start(sys.argv[2],json.load(sys.stdin)))"
    )

    def host(phase, expected_exit):
        process = subprocess.run(
            [sys.executable, "-I", "-B", "-c", driver, str(Path(__file__).resolve()), phase],
            cwd=source.parent,
            input=json.dumps(fixture),
            capture_output=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        for secret in (owner["admin_token"], request.receiver.session_token):
            assert secret not in process.stdout + process.stderr
        assert process.returncode == expected_exit, process.stderr
        return json.loads(process.stdout)

    return host


@pytest.mark.parametrize("checkpoint", ["prepared", "dispatch-intent"])
async def test_host_exit_preserves_continuation_recovery(unfinished, pilot, checkpoint):
    flow, request, _, child, calls, _, _, key = unfinished
    core, owner, _, _, source_task, tree, source, receipts, _ = pilot
    host = _continuation_host_launcher(flow, request, pilot)

    def source_observations():
        return (
            flow._relay.owner_inspect_attempts(
                owner["project_id"], source_task["id"], admin_token=owner["admin_token"]
            ),
            {file.name: file.read_bytes() for file in receipts.glob("relay-" + key + "*.json")},
        )

    original = source_observations()
    before = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    auth = request.receiver.authentication()
    initial_tasks = {row["id"] for row in core.execute("list_tasks", auth)["tasks"]}
    exited = host(checkpoint, 73)
    task_id, worktree_id, head_sha = exited["worktree"]
    saved_tree = core.execute(
        "inspect_owned_worktree", {**auth, "task_id": task_id, "worktree_id": worktree_id}
    )
    assert saved_tree["head_sha"] == head_sha
    pending_intent = checkpoint == "dispatch-intent"
    saved = flow.status(
        owner["project_id"], request.source.launch_sha256, admin_token=owner["admin_token"]
    )
    assert saved["task_id"] == task_id
    assert saved["state"] == ("unknown" if pending_intent else "prepared")
    recovered = host("resume", 0)
    replayed = host("resume", 0)
    assert all(run["pid"] != os.getpid() for run in (exited, recovered, replayed))
    assert recovered["outcome"] == replayed["outcome"]
    assert recovered["outcome"]["task_id"] == task_id
    assert recovered["outcome"]["source_task_id"] == source_task["id"]
    assert replayed["builds"] == [] and replayed["approvals"] == replayed["launches"] == 0

    if pending_intent:
        assert recovered["outcome"]["state"] == "unknown"
        assert recovered["outcome"]["wave"] is None and recovered["outcome"]["publication"] is None
        assert recovered["builds"] == [] and recovered["approvals"] == recovered["launches"] == 0
    else:
        assert recovered["outcome"]["state"] == "resolved"
        assert recovered["outcome"]["task_status"] == "review"
        assert recovered["outcome"]["publication"]["verification"] == "unverified"
        assert recovered["builds"] == [exited["worktree"]]
        assert recovered["approvals"] == recovered["launches"] == 1

    tasks = {row["id"]: row for row in core.execute("list_tasks", auth)["tasks"]}
    assert task_id not in initial_tasks and set(tasks) == initial_tasks | {task_id}
    assert tasks[source_task["id"]]["status"] == "failed"
    assert tasks[child["id"]]["dependencies"] == [task_id]
    assert tasks[child["id"]]["version"] == child["version"] + 1
    assert (
        core.execute(
            "inspect_owned_worktree", {**auth, "task_id": task_id, "worktree_id": worktree_id}
        )
        == saved_tree
    )
    assert source_observations() == original and len(calls) == 1
    assert [source_fingerprint(path) for path in (source, Path(tree["path"]))] == before


@pytest.mark.parametrize("unfinished", ["verifiable_codex"], indirect=True)
async def test_host_exit_after_receiver_review_reconciles_existing_wave(unfinished, pilot):
    flow, request, build, child, calls, approvals, _, _ = unfinished
    core, owner, _, _, source_task, tree, source, receipts, _ = pilot
    host = _continuation_host_launcher(flow, request, pilot)
    project_id = owner["project_id"]
    admin_token = owner["admin_token"]
    auth = request.receiver.authentication()

    def tasks():
        return {row["id"]: row for row in core.execute("list_tasks", auth)["tasks"]}

    original = {path.name: path.read_bytes() for path in receipts.glob("*.json")}
    original_workspaces = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    initial_tasks = tasks()
    exited = host("review-submitted", 73)
    assert exited["pid"] != os.getpid() and exited["approvals"] == exited["launches"] == 1
    task_id, worktree_id, head_sha = exited["worktree"]
    saved = flow.status(project_id, request.source.launch_sha256, admin_token=admin_token)
    assert saved["task_id"] == task_id and saved["task_status"] == "review"
    assert saved["state"] == "incomplete" and saved["publication"]["verification"] == "unverified"
    pending = flow._queue.owner_observe_pending(project_id, admin_token=admin_token)
    assert pending.wave_id == exited["wave_id"] and pending.receipt_state == "admitted"

    saved_tree = core.execute(
        "inspect_owned_worktree", {**auth, "task_id": task_id, "worktree_id": worktree_id}
    )
    actor = build(
        request.receiver,
        HandoffWorkspace(
            task_id, saved["task_version"], worktree_id, head_sha, Path(saved_tree["path"])
        ),
    )
    stager = core.execute("register_agent", {**owner, "name": "Recovered receiver staging worker"})
    owner_grant(core, owner, stager, ("worker",))
    staging = {
        "continuation": request,
        "admin_token": admin_token,
        "staging_session_id": stager["session_id"],
        "staging_session_token": stager["session_token"],
    }
    with pytest.raises(AgentSyncError) as denied:
        flow._relay.preview_continuation_proposal_staging(actor, task_id, **staging)
    assert denied.value.code == "relay_boundary"

    graph = tasks()
    assert task_id not in initial_tasks and set(graph) == initial_tasks.keys() | {task_id}
    assert graph[source_task["id"]]["status"] == "failed"
    assert graph[child["id"]]["dependencies"] == [task_id]
    assert graph[child["id"]]["version"] == child["version"] + 1
    recorded = {path.name: path.read_bytes() for path in receipts.glob("*.json")}
    assert all(recorded[name] == content for name, content in original.items())

    before_reconcile = host("resume", 0)
    assert before_reconcile["outcome"]["state"] == "incomplete"
    assert before_reconcile["builds"] == []
    assert before_reconcile["approvals"] == before_reconcile["launches"] == 0
    # Reconciliation runs in a clean CLI process and can only consume the exact saved wave.
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "agentsync",
            "--data-dir",
            str(core.data_dir),
            "relay-reconcile",
            pending.wave_id,
            "--scratch-root",
            str(source.parent),
            "--receipts",
            str(receipts),
        ],
        cwd=source.parent,
        input=json.dumps({**auth, "admin_token": admin_token}),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    for secret in (admin_token, request.receiver.session_token):
        assert secret not in process.stdout + process.stderr
    assert process.returncode == 0, process.stderr
    outcome = json.loads(process.stdout)["data"]
    assert outcome["state"] == "resolved" and outcome["verification"] == "unverified"
    assert outcome["tasks"] == [
        {"task_id": task_id, "state": "ready_for_review", "failure_code": None}
    ]
    assert flow._queue.owner_observe_pending(project_id, admin_token=admin_token) is None

    preview = flow._relay.preview_continuation_proposal_staging(actor, task_id, **staging)["plan"]
    assert preview["task_id"] == task_id and preview["task_version"] == saved["task_version"]
    assert preview["context_id"] == saved["publication"]["context_id"]
    assert preview["content_sha256"] == saved["publication"]["content_sha256"]
    assert [file["path"] for file in preview["files"]] == ["solution.py"]
    replayed = host("resume", 0)
    assert replayed["outcome"]["state"] == "resolved" and replayed["outcome"]["wave"] == outcome
    assert replayed["outcome"]["publication"] == saved["publication"]
    assert replayed["builds"] == [] and replayed["approvals"] == replayed["launches"] == 0
    assert tasks() == graph and len(calls) == len(approvals) == 1
    assert {path.name: path.read_bytes() for path in receipts.glob("*.json")} == recorded
    assert [
        source_fingerprint(path) for path in (source, Path(tree["path"]))
    ] == original_workspaces
    print(
        json.dumps(
            {
                "protocol_fixture": True,
                "checkpoint_exit_code": 73,
                "checkpoint": exited,
                "before_reconcile": {
                    key: before_reconcile[key] for key in ("pid", "approvals", "launches")
                },
                "reconcile_exit_code": process.returncode,
                "reconciled_wave": outcome,
                "staging_preview_task_id": preview["task_id"],
                "replay": {key: replayed[key] for key in ("pid", "approvals", "launches")},
                "source_task_status": graph[source_task["id"]]["status"],
                "dependent_task_id": child["id"],
                "dependent_version": graph[child["id"]]["version"],
                "receipts_unchanged": True,
            }
        ),
        flush=True,
    )


async def test_old_failed_receipt_cannot_cancel_reclaimed_same_session(unfinished, pilot):
    flow, request, _, _, calls, _, _, _ = unfinished
    core, owner, _, auth, task, _, _, _, _ = pilot
    with connect(core.db_path) as db:
        db.execute("UPDATE tasks SET lease_expires_at=0 WHERE id=?", (task["id"],))
    core.execute("reclaim_expired", auth)
    current = next(
        row for row in core.execute("list_tasks", auth)["tasks"] if row["id"] == task["id"]
    )
    claim = core.execute(
        "claim_task",
        {
            **auth,
            "task_id": task["id"],
            "expected_version": current["version"],
            "request_id": "fresh-claim",
        },
    )
    core.execute(
        "update_task",
        {
            **auth,
            "task_id": task["id"],
            "expected_version": claim["version"],
            "lease_token": claim["lease_token"],
            "status": "running",
            "request_id": "fresh-running",
        },
    )
    before = core.execute("list_tasks", auth)
    with pytest.raises(AgentSyncError):
        flow.pin_failed_progress(
            owner["project_id"],
            task["id"],
            context_id=request.source.context_id,
            context_version=request.source.context_version,
            content_sha256=request.source.content_sha256,
            admin_token=owner["admin_token"],
        )
    with pytest.raises(AgentSyncError):
        flow.preview(request, admin_token=owner["admin_token"])
    assert core.execute("list_tasks", auth) == before and len(calls) == 1

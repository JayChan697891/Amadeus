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
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_m4b_workspaces import source_fingerprint
from test_task_proposals import world as world
from verified_flow_process_fixture import emit_proposal, receiver_profile

import agentsync
from agentsync.adapters.approved_launch import LaunchConsent
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
from agentsync.proposal_handoff import HandoffReceiver
from agentsync.relay_queue import CodexProposalQueueItem, RelayQueue
from agentsync.storage.database import connect


@pytest.fixture
async def unfinished(pilot, world, monkeypatch, request):
    selected = getattr(request, "param", "codex")
    client, fault = selected if isinstance(selected, tuple) else (selected, None)
    core, owner, member, auth, task, tree, source, receipts, profile = pilot
    cancel_fixture_load(world)
    calls, approvals, captures, published = [], [], [], []
    original_start = CapturedProcess.start
    relay = ControlledRelay(core, source.parent, receipts)
    key = relay._task_receipt_key(owner["project_id"], task["id"])
    partial = "def total(values):\n    # UNFINISHED_CONTEXT_SENTINEL\n    return None\n"
    final = "def total(values):\n    return sum(values)\n"

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
            current = next(
                row for row in core.execute("list_tasks", auth)["tasks"] if row["id"] == task["id"]
            )
            published.append(
                relay.publish_progress_checkpoint(
                    actor,
                    task["id"],
                    expected_version=current["version"],
                    allowed_paths=("answer.py",),
                    proposal_json=json.dumps(
                        {"files": [{"path": "answer.py", "content": partial}]}
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
                "answer.py",
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
            task["id"], task["version"], "Continue the implementation.", ("answer.py",), 10, True
        ),
    )
    queue = RelayQueue(relay)
    outcome = await queue.run_ready_once(
        (item,), request_id="failed-source", admin_token=owner["admin_token"]
    )
    assert outcome.state == "incomplete"
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
        ("answer.py",),
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


@pytest.mark.parametrize("unfinished", ["codex", "claude", "cursor"], indirect=True)
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
    worktree = None
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
        assert phase == "resume"
        approvals.append(plan.plan_sha256)
        return LaunchConsent(
            "continuation-host-fixture-" + plan.plan_sha256,
            plan.plan_sha256,
            time.time() + 30,
            True,
            True,
        )

    def build(receiver, workspace):
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
        return RelayActor(
            receiver.agent_id,
            receiver.session_token,
            profile,
            workspace.worktree_id,
            workspace.head_sha,
            {},
            approve,
        )

    async def capture(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert phase == "resume" and str(cwd) != fixture["source_worktree"] and env == {}
        contract, _ = json.JSONDecoder().raw_decode(stdin_text.split("Host contract: ", 1)[1])
        assert contract["mode"] == "proposal_continuation"
        assert contract["continuation"]["content_sha256"] == request.source.content_sha256
        assert "UNFINISHED_CONTEXT_SENTINEL" in stdin_text
        process = await emit_proposal(
            original_start,
            "answer.py",
            "def total(values):\n    return sum(values)\n",
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captures.append(process)
        return process

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


@pytest.mark.parametrize("checkpoint", ["prepared", "dispatch-intent"])
async def test_host_exit_preserves_continuation_recovery(unfinished, pilot, checkpoint):
    flow, request, _, child, calls, _, _, key = unfinished
    core, owner, _, _, source_task, tree, source, receipts, profile = pilot
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

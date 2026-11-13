"""Owned protocol emitters plus actual local Docker, never real model acceptance."""

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import owner_grant
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_relay_queue import cancel_fixture_load
from test_codex_proposal_review import captured_processes as captured_processes
from test_m4b_workspaces import source_fingerprint
from test_proposal_docker_pipeline import assert_local_container_absent
from test_proposal_docker_pipeline import pipeline_image as pipeline_image
from test_task_proposals import world as world

from agentsync.adapters.approved_launch import LaunchConsent
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import CodexProposalInput, RelayActor, RelayReviewer
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.proposal_handoff import HandoffReceiver, ProposalHandoffRequest
from agentsync.verification.candidate_executor import OwnerCandidateExecutor
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verified_proposal_flow import VerifiedProposalFlow


class VerifiedCheckpoint(Exception):
    pass


@pytest.mark.parametrize(
    "scenario",
    ["verified", "wrong-result", "reopen", "deny-staging", "deny-execution", "deny-completion"],
)
async def test_verified_flow_gates_and_reopen(
    pilot, world, pipeline_image, captured_processes, monkeypatch, scenario
):
    core, owner, member, auth, task, tree, source, receipts, host_profile = pilot
    cancel_fixture_load(world)
    before = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    initial_tasks = core.execute("list_tasks", auth)["tasks"]

    def register(name, role):
        who = core.execute("register_agent", {**owner, "name": name})
        owner_grant(core, owner, who, (role,))
        return who

    staging = register("Independent staging worker", "worker")
    reviewing = register("Independent result reviewer", "reviewer")
    receiving = register("Downstream receiver", "worker")
    request = ProposalHandoffRequest(
        task["id"],
        HandoffReceiver(
            owner["project_id"],
            receiving["agent_id"],
            receiving["session_id"],
            receiving["session_token"],
        ),
        "verified-fixture-handoff",
        "Review the independently verified source.",
        ("review.md",),
        10,
    )
    expression = "sum(value) + 1" if scenario == "wrong-result" else "sum(value)"
    code = (
        "import json,sys\nfor line in sys.stdin:\n value=json.loads(line)\n print(json.dumps("
        + expression
        + "),flush=True)\n"
    )
    launched = []
    original_start = CapturedProcess.start

    def current_task():
        return next(t for t in core.execute("list_tasks", auth)["tasks"] if t["id"] == task["id"])

    async def fixture_start(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert env == {}
        contract, _ = json.JSONDecoder().raw_decode(stdin_text.split("Host contract: ", 1)[1])
        paths = contract["allowed_paths"]
        if paths == ["solution.py"]:
            assert cwd == Path(tree["path"])
            content = code
        else:
            assert (
                paths == ["review.md"]
                and contract["input_context"]["producer_task_id"] == task["id"]
            )
            assert current_task()["status"] == "completed"
            assert current_task()["task_verification"] == "verified"
            content = "Owned receiver protocol fixture, not a model review.\n"
        launched.append(paths[0])
        message = json.dumps({"files": [{"path": paths[0], "content": content}]})
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
        payload = "\n".join(json.dumps(event) for event in events) + "\n"
        process = await original_start(
            (sys.executable, "-I", "-c", "import sys;sys.stdout.write(" + repr(payload) + ")"),
            cwd=cwd,
            stdin_text="",
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )
        captured_processes.append(process)
        return process

    async def approve_launch(plan):
        return LaunchConsent(
            "owned-protocol-fixture", plan.plan_sha256, time.time() + 30, True, True
        )

    monkeypatch.setattr(CapturedProcess, "start", classmethod(fixture_start))
    actor = RelayActor(
        member["agent_id"],
        member["session_token"],
        host_profile,
        tree["worktree_id"],
        tree["head_sha"],
        {},
        approve_launch,
    )
    proposal = CodexProposalInput(
        task["id"],
        task["version"],
        "Return owned fixture source.",
        ("solution.py",),
        10,
        submit_for_review=True,
    )
    profile = DockerProfile(
        pipeline_image,
        (
            JsonCase([2, 3], 5),
            JsonCase([-7, 4], -3),
            JsonCase([2**63 - 1, 1], 2**63),
        ),
    )
    stages = []

    async def decide(stage, decision, key):
        stages.append(stage)
        assert launched == ["solution.py"]
        assert (
            current_task()["status"] == "review"
            and current_task()["task_verification"] == "unverified"
        )
        return "wrong-exact-pin" if scenario == "deny-" + stage else decision[key]

    async def approve_staging(plan):
        return await decide("staging", plan, "plan_sha256")

    async def approve_execution(job):
        return await decide("execution", job, "metadata_sha256")

    async def approve_completion(decision):
        result = decision["execution"]["execution"]["result"]
        assert result["backend"] == "local-linux-docker" and result["cleanup_confirmed"]
        assert result["passed_case_count"] == result["expected_case_count"] == 3
        assert_local_container_absent(result["container_id"])
        return await decide("completion", decision, "decision_sha256")

    builds = 0

    def build_receiver(receiver, workspace):
        nonlocal builds
        builds += 1
        assert current_task()["task_verification"] == "verified"
        if scenario == "reopen" and builds == 1:
            raise VerifiedCheckpoint
        return replace(
            actor,
            agent_id=receiver.agent_id,
            session_token=receiver.session_token,
            worktree_id=workspace.worktree_id,
            expected_head=workspace.head_sha,
            profile=replace(host_profile, session_id=receiver.session_id, root=workspace.path),
        )

    flow = VerifiedProposalFlow(core, source.parent, receipts)
    args = dict(
        admin_token=owner["admin_token"],
        stager=RelayReviewer(owner["project_id"], staging["session_id"], staging["session_token"]),
        reviewer=RelayReviewer(
            owner["project_id"], reviewing["session_id"], reviewing["session_token"]
        ),
        profile=profile,
        approve_staging=approve_staging,
        approve_execution=approve_execution,
        approve_completion=approve_completion,
        build_receiver=build_receiver,
    )
    if scenario == "reopen":
        with pytest.raises(VerifiedCheckpoint):
            await flow.run_once(actor, proposal, request, **args)
        assert launched == ["solution.py"]
        flow = VerifiedProposalFlow(Core(core.data_dir), source.parent, receipts)
        first = await flow.resume_receiver(
            request, admin_token=owner["admin_token"], build_receiver=build_receiver
        )
        assert first.state == "resolved"
        again = await VerifiedProposalFlow(
            Core(core.data_dir), source.parent, receipts
        ).resume_receiver(request, admin_token=owner["admin_token"], build_receiver=build_receiver)
        assert again == first
    else:
        result = await flow.run_once(actor, proposal, request, **args)
        expected = {
            "verified": "handoff",
            "wrong-result": "verification_failed",
            "deny-staging": "staging_denied",
            "deny-execution": "execution_denied",
            "deny-completion": "completion_denied",
        }[scenario]
        assert result.state == expected
        if scenario == "verified":
            assert result.handoff.state == "resolved"
        else:
            with pytest.raises(AgentSyncError) as denied:
                await flow.resume_receiver(
                    request, admin_token=owner["admin_token"], build_receiver=build_receiver
                )
            assert denied.value.code == "verification_required"

    successful = scenario in {"verified", "reopen"}
    assert launched == (["solution.py", "review.md"] if successful else ["solution.py"])
    final = current_task()
    assert final["status"] == ("completed" if successful else "review")
    assert final["task_verification"] == ("verified" if successful else "unverified")
    assert len(core.execute("list_tasks", auth)["tasks"]) == len(initial_tasks) + int(successful)
    jobs = CandidateVerificationJobs(core).list(**owner)["jobs"]
    assert len(jobs) == (0 if scenario == "deny-staging" else 1)
    if scenario not in {"deny-staging", "deny-execution"}:
        execution = OwnerCandidateExecutor(core).get(**owner, job_id=jobs[0]["id"])
        result = execution["execution"]["result"]
        assert result["backend"] == "local-linux-docker" and result["cleanup_confirmed"]
        assert execution["execution_assessment"] == (
            "failed" if scenario == "wrong-result" else "passed"
        )
        assert_local_container_absent(result["container_id"])
    assert [source_fingerprint(path) for path in (source, Path(tree["path"]))] == before

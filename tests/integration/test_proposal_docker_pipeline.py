"""Same-Core proposal pipeline with real Docker and a labeled local client fixture.

The model boundary emits fixed JSONL from an owned Python process. Only the
existing Docker verifier executes proposal bytes. This is not real-client proof.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import owner_grant
from test_codex_proposal_capture import pilot as pilot
from test_codex_proposal_review import captured_processes as captured_processes
from test_m4b_workspaces import source_fingerprint
from test_task_proposals import world as world

from agentsync.adapters.approved_launch import LaunchConsent
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.controlled_relay import CodexProposalInput, ControlledRelay, RelayActor
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.owner_flow import OwnerCandidateFlow


@pytest.fixture
def pipeline_image():
    image = os.environ.get("AGENTSYNC_DOCKER_TEST_IMAGE")
    if not image:
        if os.environ.get("AGENTSYNC_REQUIRE_DOCKER_TESTS") == "1":
            pytest.fail("Required proposal pipeline has no pinned local Docker image")
        pytest.skip("Proposal execution requires an explicitly pinned local Linux Docker image")
    assert sys.platform == "linux"
    return image


@pytest.mark.parametrize("correct", [True, False], ids=["verified", "wrong-result"])
async def test_same_core_proposal_to_independent_docker_acceptance(
    pipeline_image, pilot, monkeypatch, captured_processes, correct
):
    core, owner, member, auth, task, tree, source, receipts, host_profile = pilot
    before = [source_fingerprint(path) for path in (source, Path(tree["path"]))]
    expression = "sum(value)" if correct else "sum(value) + 1"
    code = (
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " value=json.loads(line)\n"
        f" print(json.dumps({expression}),flush=True)\n"
    )
    message = json.dumps({"files": [{"path": "solution.py", "content": code}]})
    events = [
        {"type": "thread.started", "thread_id": "local-protocol-fixture"},
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
    original_start = CapturedProcess.start
    launches = []

    async def fixture_start(_cls, argv, *, cwd, stdin_text, timeout_seconds, output_limit, env):
        assert cwd == Path(tree["path"]) and env == {}
        contract = json.loads(stdin_text.split("Host contract: ", 1)[1])
        assert contract["submit_for_review"] is True
        assert contract["allowed_paths"] == ["solution.py"]
        launches.append(argv)
        payload = "\n".join(json.dumps(event) for event in events) + "\n"
        # Execute only this trusted data emitter, never the proposal source.
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

    async def approve(review):
        return LaunchConsent("local-fixture-only", review.plan_sha256, time.time() + 30, True, True)

    monkeypatch.setattr(CapturedProcess, "start", classmethod(fixture_start))
    actor = RelayActor(
        member["agent_id"],
        member["session_token"],
        host_profile,
        tree["worktree_id"],
        tree["head_sha"],
        {},
        approve,
    )
    spec = CodexProposalInput(
        task["id"],
        task["version"],
        "Return fixed local fixture source.",
        ("solution.py",),
        10,
        submit_for_review=True,
    )
    relay = ControlledRelay(core, source.parent, receipts)
    stored = await relay.run_codex_proposal_once(actor, spec, admin_token=owner["admin_token"])
    assert stored.state == "proposal_stored"
    reviewed = relay.observe_codex_proposal_review(actor, task["id"])
    assert reviewed.state == "submitted_for_review" and reviewed.verification == "unverified"
    stager = core.execute("register_agent", {**owner, "name": "Separate staging worker"})
    owner_grant(core, owner, stager, ("worker",))
    staging_auth = {
        "admin_token": owner["admin_token"],
        "staging_session_id": stager["session_id"],
        "staging_session_token": stager["session_token"],
    }
    preview = relay.preview_codex_proposal_staging(actor, task["id"], **staging_auth)
    staged = relay.stage_codex_proposal_once(
        actor, task["id"], **staging_auth, expected_plan_sha256=preview["plan_sha256"]
    )
    pins = {
        **owner,
        "candidate_id": staged["candidate_id"],
        "expected_candidate_sha": staged["candidate_sha"],
    }
    exported = OwnerCandidateExporter(core).export(**pins)
    assert exported.snapshot.source == code.encode()
    profile = DockerProfile(
        pipeline_image,
        (JsonCase([2, 3], 5), JsonCase([-7, 4], -3), JsonCase([2**63 - 1, 1], 2**63)),
    )
    job = CandidateVerificationJobs(core).enqueue(**pins, profile=profile, request_id="queue")
    flow = OwnerCandidateFlow(core)
    execution = flow.start_once(
        **owner,
        job_id=job["id"],
        expected_job_version=job["version"],
        expected_metadata_sha256=job["metadata_sha256"],
        profile=profile,
    )
    detail = execution["execution"]
    result = detail["result"]
    assert result["backend"] == "local-linux-docker"
    assert result["source_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    assert result["cleanup_confirmed"] is True
    assert result["isolation"]["checks"] and all(result["isolation"]["checks"].values())
    containers = subprocess.run(
        ["docker", "container", "ls", "--all", "--no-trunc", "--format", "{{.ID}}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result["container_id"] not in containers.stdout.splitlines()
    reviewer = core.execute("register_agent", {**owner, "name": "Independent reviewer"})
    owner_grant(core, owner, reviewer, ("reviewer",))
    completion_args = {
        **owner,
        "task_id": task["id"],
        "expected_version": reviewed.review_task_version,
        "job_id": job["id"],
        "execution_id": execution["execution_id"],
        "expected_execution_revision": detail["revision"],
        "profile": profile,
    }
    if correct:
        assert execution["execution_assessment"] == "passed"
        assert result["passed_case_count"] == result["expected_case_count"] == 3
        # Even after granting reviewer authority, the producer cannot accept itself.
        owner_grant(core, owner, member, ("worker", "reviewer"))
        with pytest.raises(AgentSyncError) as denied:
            flow.complete_once(
                **completion_args,
                session_id=member["session_id"],
                session_token=member["session_token"],
                request_id="self-review",
            )
        assert denied.value.code == "separate_reviewer_required"
        completed = flow.complete_once(
            **completion_args,
            session_id=reviewer["session_id"],
            session_token=reviewer["session_token"],
            request_id="independent-completion",
        )
        assert completed["task_verification"] == "verified"
    else:
        assert execution["execution_assessment"] == "failed"
        with pytest.raises(AgentSyncError):
            flow.complete_once(
                **completion_args,
                session_id=reviewer["session_id"],
                session_token=reviewer["session_token"],
                request_id="failed-completion",
            )
    reopened = Core(core.data_dir)
    current = next(
        item for item in reopened.execute("list_tasks", auth)["tasks"] if item["id"] == task["id"]
    )
    assert current["status"] == ("completed" if correct else "review")
    assert current["task_verification"] == ("verified" if correct else "unverified")
    with pytest.raises(AgentSyncError):
        await relay.run_codex_proposal_once(actor, spec, admin_token=owner["admin_token"])
    with pytest.raises(AgentSyncError):
        flow.start_once(
            **owner,
            job_id=job["id"],
            expected_job_version=job["version"],
            expected_metadata_sha256=job["metadata_sha256"],
            profile=profile,
        )
    assert len(launches) == 1
    assert [source_fingerprint(path) for path in (source, Path(tree["path"]))] == before
    evidence = os.environ.get("AGENTSYNC_PROPOSAL_PIPELINE_EVIDENCE_DIR")
    if evidence:
        directory = Path(evidence)
        assert directory.is_absolute() and not directory.is_symlink()
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / ("verified.json" if correct else "wrong-result.json")).open(
            "x", encoding="utf-8"
        ) as output:
            json.dump(
                {
                    "model_boundary": "known local Python JSONL fixture; no real model",
                    "model_calls": 0,
                    "same_core": True,
                    "proposal_sha256": hashlib.sha256(code.encode()).hexdigest(),
                    "candidate_sha": staged["candidate_sha"],
                    "execution": execution,
                    "final_status": current["status"],
                    "task_verification": current["task_verification"],
                    "source_and_producer_unchanged": True,
                    "container_absent": True,
                    "formal_release": "BLOCKED",
                },
                output,
                indent=2,
            )

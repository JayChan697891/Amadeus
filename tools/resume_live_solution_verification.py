"""Use fresh verification identities for the saved a122 receiver proposal.

Place this separately reviewed tool beside the unchanged guest verify.py. Give
`prepare` the already-enrolled stager and reviewer session credentials as JSON
on private stdin. Each subsequent action takes its own reviewed plan SHA-256.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from agentsync.continuation import OwnerContinuation
from agentsync.controlled_relay import ControlledRelay
from agentsync.errors import AgentSyncError
from agentsync.verification.candidate import OwnerCandidateExporter
from agentsync.verification.candidate_executor import OwnerCandidateExecutor
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.owner_flow import OwnerCandidateFlow
from agentsync.verification.proposal_staging import OwnerProposalStaging

BASE = Path("/root/amadeus-m122-composed-recovery")
ORIGINAL_STAGE = "28969e1168f5514a02776db6f5f5fee700d265f71707f5024e2dd45f1f24e2da"
ACTORS = "resume-actors.private.json"
COMPLETION_REQUEST = "complete-recovered-a122-receiver-with-fresh-reviewer"


def actor_binding(core, owner, original, credentials):
    assert set(credentials) == {"stager", "reviewer"}
    existing = {
        original[role]["agent_id"] for role in ("producer", "receiver", "stager", "reviewer")
    }
    actors = {}
    for name, role in (("stager", "worker"), ("reviewer", "reviewer")):
        identity = credentials[name]
        assert set(identity) == {"session_id", "session_token"}
        auth = {"project_id": owner["project_id"], **identity}
        view = core.execute("get_project_state", auth)
        (session,) = [row for row in view["sessions"] if row["id"] == identity["session_id"]]
        agent = session["agent_id"]
        assert agent not in existing
        existing.add(agent)
        (member,) = core.execute_owner("list_selected_members", {**owner, "agent_ids": [agent]})[
            "members"
        ]
        assert role in member["roles"]
        actors[name] = {"session_id": session["id"], "agent_id": agent}
    return actors


def stage_preview(service, owner, old, publication, stager, actor):
    previous = old["staging"]["plan"]
    binding = old["binding"]
    request = {
        **owner,
        **stager,
        "task_id": binding["task_id"],
        "expected_task_version": binding["review_task_version"],
        "context_id": binding["context_id"],
        "expected_content_sha256": binding["publication_sha256"],
        "publication_session_id": publication["publication_session_id"],
        "publication_request_id": publication["publication_request_id"],
    }
    stage = service.preview(**request)
    assert stage["plan"] == previous | {
        "staging_session_id": actor["session_id"],
        "staging_agent_id": actor["agent_id"],
    }
    return stage, request


def prepare_result(live, verify, recovery, core, state, grant, credentials):
    assert live.sha(BASE / "stage-plan.json") == ORIGINAL_STAGE
    assert not any(
        live.present(f"{action}-entry.json") for action in ("stage", "execution", "completion")
    )
    old = live.read("stage-plan.json")
    binding = old["binding"]
    for actor in ("producer", "receiver"):
        assert live.sha(BASE / f"{actor}-capture.json") == binding[f"{actor}_capture_record_sha256"]
    owner = state["owner"]
    born = live.read("continuation-result.json")
    replay = live.read("replay.json")
    request, continuation = live.load_continuation(state, grant)
    assert recovery.approval_binding(live, born) == {
        key: binding[key]
        for key in ("controller_exit_checkpoint_sha256", "controller_reconcile_sha256")
    }
    assert born["outcome"] == replay["outcome"] and replay["tasks_and_receipts_unchanged"] is True
    assert replay["receiver_callbacks"] == replay["model_calls"] == 0
    assert born["authorization_sha256"] == binding["authorization_sha256"] == grant
    assert born["plan_sha256"] == binding["continuation_plan_sha256"] == continuation["plan_sha256"]
    status = OwnerContinuation(core, BASE, live.RECEIPTS).status(
        owner["project_id"], request.source.launch_sha256, admin_token=owner["admin_token"]
    )
    assert json.loads(json.dumps(status)) == born["outcome"]
    assert status["state"] == "resolved" and status["task_status"] == "review"
    assert status["task_id"] == binding["task_id"]
    assert status["task_version"] == binding["review_task_version"]
    publication = status["publication"]
    assert publication["verification"] == "unverified" and publication["context_version"] == 1
    assert publication["publication_session_id"] == state["receiver"]["session_id"]
    assert publication["content_sha256"] == binding["publication_sha256"]
    assert publication["context_id"] == binding["context_id"]
    actors = actor_binding(core, owner, state, credentials)
    reader = {"project_id": owner["project_id"], **credentials["reviewer"]}
    context = core.execute(
        "get_context",
        {
            **reader,
            "context_id": publication["context_id"],
            "version": publication["context_version"],
        },
    )
    assert context["author_agent_id"] == state["receiver"]["agent_id"]
    assert verify.sha(context["content"].encode()) == publication["content_sha256"]
    _, producer = verify.captured_proposal(live, "producer")
    files, receiver = verify.captured_proposal(live, "receiver")
    assert producer == binding["producer_stdout_sha256"]
    assert receiver == binding["receiver_stdout_sha256"]
    assert json.loads(context["content"])["files"] == files
    (file,) = files
    source = file["content"].encode()
    assert len(source) == 149 and verify.sha(source) == binding["source_sha256"]
    graph = task_graph(core, reader)
    assert graph == born["tasks"] and graph[binding["source_task_id"]]["status"] == "failed"
    relay = ControlledRelay(core, BASE, live.RECEIPTS)
    assert (
        live.source_receipts(relay, state, request.source.launch_sha256)
        == continuation["source_receipt_sha256"]
    )
    binding |= {
        "original_stage_plan_sha256": ORIGINAL_STAGE,
        "resume_driver_sha256": live.sha(Path(__file__)),
        "actors": actors,
    }
    return old, binding, publication, source, graph, reader


def task_graph(core, reader):
    return {
        row["id"]: {
            key: row[key]
            for key in ("id", "status", "version", "dependencies", "task_verification")
        }
        for row in core.execute("list_tasks", reader)["tasks"]
    }


def drive(live, verify, recovery, grant, action, expected, credentials):
    core, state = live.core_state()
    old, binding, publication, source, graph, reader = prepare_result(
        live, verify, recovery, core, state, grant, credentials
    )
    owner, task_id = state["owner"], binding["task_id"]
    profile = DockerProfile(
        verify.IMAGE, tuple(JsonCase(values, total) for values, total in verify.CASES)
    )
    policy = {"profile_sha256": profile.sha256, "image_id": verify.IMAGE, "cases": verify.CASES}
    assert old["policy"] == policy
    jobs = CandidateVerificationJobs(core)
    flow = OwnerCandidateFlow(core)

    if action in ("prepare", "stage-once"):
        service = OwnerProposalStaging(core)
        stage, request = stage_preview(
            service, owner, old, publication, credentials["stager"], binding["actors"]["stager"]
        )
        plan = {
            "action": "stage-and-enqueue-once",
            "binding": binding,
            "staging": stage,
            "policy": policy,
        }
        if action == "prepare":
            live.cleanup.save(ACTORS, credentials)
            verify.publish_plan(live, state, "resume-stage-plan.json", plan)
            return
        verify.approve(live, state, "resume-stage", expected, plan)
        staged = service.stage_once(**request, expected_plan_sha256=stage["plan_sha256"])
        live.write("resume-stage-result.json", staged, state)
        assert staged["state"] == "staged" and staged["task_id"] == task_id
        assert staged["execution_started"] is False and staged["verification"] == "unverified"
        candidate = {
            "candidate_id": staged["candidate_id"],
            "expected_candidate_sha": staged["candidate_sha"],
        }
        assert OwnerCandidateExporter(core).export(**owner, **candidate).snapshot.source == source
        enqueued = jobs.enqueue(
            **owner, **candidate, profile=profile, request_id="enqueue-recovered-a122-receiver"
        )
        live.write("resume-enqueue-result.json", enqueued, state)
        job = jobs.get(**owner, job_id=enqueued["id"])
        assert job["status"] == "queued" and job["source_sha256"] == binding["source_sha256"]
        verify.publish_plan(
            live,
            state,
            "resume-execution-plan.json",
            {
                "action": "execute-once",
                "binding": binding,
                "policy": policy,
                "job": job,
                "stage_approval_sha256": expected,
            },
        )
        return

    execution_plan = live.read("resume-execution-plan.json")
    assert execution_plan["binding"] == binding and execution_plan["policy"] == policy
    assert live.read("resume-stage-entry.json") == {
        "action": "resume-stage",
        "plan_sha256": live.sha(BASE / "resume-stage-plan.json"),
    }
    assert (
        execution_plan["stage_approval_sha256"]
        == live.read("resume-stage-entry.json")["plan_sha256"]
    )
    job = jobs.get(**owner, job_id=execution_plan["job"]["id"])
    if action == "execute-once":
        assert job == execution_plan["job"] and job["status"] == "queued"
        verify.approve(live, state, "resume-execution", expected, execution_plan)
        execution = flow.start_once(
            **owner,
            job_id=job["id"],
            expected_job_version=job["version"],
            expected_metadata_sha256=job["metadata_sha256"],
            profile=profile,
        )
        live.write("resume-execution-result.json", execution, state)
    else:
        assert live.read("resume-execution-entry.json") == {
            "action": "resume-execution",
            "plan_sha256": live.sha(BASE / "resume-execution-plan.json"),
        }
        execution = OwnerCandidateExecutor(core).get(**owner, job_id=job["id"])
        assert execution["execution"] == live.read("resume-execution-result.json")["execution"]
    result = verify.docker_result(execution, binding["source_sha256"])
    plan = {
        "action": "complete-once",
        "binding": binding,
        "policy": policy,
        "job_id": job["id"],
        "execution_approval_sha256": live.sha(BASE / "resume-execution-plan.json"),
        "execution_result_sha256": live.sha(BASE / "resume-execution-result.json"),
        "execution_id": execution["execution_id"],
        "execution_revision": execution["execution"]["revision"],
        "container_id": result["container_id"],
        "request_id": COMPLETION_REQUEST,
    }
    if action == "execute-once":
        verify.publish_plan(live, state, "resume-completion-plan.json", plan)
        return
    assert action == "complete-once"
    verify.approve(live, state, "resume-completion", expected, plan)
    response = flow.complete_once(
        **owner,
        **credentials["reviewer"],
        task_id=task_id,
        expected_version=binding["review_task_version"],
        job_id=job["id"],
        execution_id=plan["execution_id"],
        expected_execution_revision=plan["execution_revision"],
        request_id=COMPLETION_REQUEST,
        profile=profile,
    )
    live.write("resume-completion-result.json", response, state)
    assert response["task_id"] == task_id and response["task_verification"] == "verified"
    current = task_graph(core, reader)
    assert current == graph | {
        task_id: graph[task_id]
        | {
            "status": "completed",
            "task_verification": "verified",
            "version": response["version"],
        }
    }
    live.prep.require_fixtures(state)
    live.prep.runtime()
    live.write("resume-completion-postcheck.json", {"tasks": current, "model_calls": 0}, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest="action", required=True)
    stages.add_parser("prepare")
    for action in ("stage-once", "execute-once", "complete-once"):
        stages.add_parser(action).add_argument("expected_plan_sha256")
    args = parser.parse_args()
    if (
        sys.platform != "linux"
        or os.geteuid() != 0
        or not sys.flags.isolated
        or not sys.dont_write_bytecode
        or not __debug__
        or Path(__file__).resolve().parent != BASE
    ):
        parser.error("Use the existing guest fixture and its installed Python with -I -B.")
    os.umask(0o077)
    sys.path.insert(0, str(BASE))
    import cleanup
    import live
    import prepare
    import recovery
    import verify

    live.prep, live.cleanup = prepare, cleanup
    with cleanup.stage_lock(allow_closing=True):
        _, grant = cleanup.validate_authorization(allow_expired=True)
        verify.require_closed(cleanup, grant)
        if args.action == "prepare":
            assert not live.present(ACTORS) and not live.present("resume-stage-plan.json")
            raw = sys.stdin.buffer.read(16385)
            assert 0 < len(raw) <= 16384
            credentials = json.loads(raw)
        else:
            credentials = live.read(ACTORS)
        drive(
            live,
            verify,
            recovery,
            grant,
            args.action,
            getattr(args, "expected_plan_sha256", None),
            credentials,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = error.code if isinstance(error, AgentSyncError) else type(error).__name__
        print(
            json.dumps({"status": "stopped", "error_code": code, "retry_allowed": False}),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

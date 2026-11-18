"""Checkpoint one real receiver's completed proposal and reconcile its saved wave."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from agentsync.adapters.approved_launch import digest
from agentsync.continuation import OwnerContinuation

CHECKPOINT = "controller-exit-checkpoint.json"
RECONCILE = "controller-reconcile.json"


def receiver_wave(request):
    project = request.receiver.project_id
    prefix = "continuation-" + digest([project, request.source.launch_sha256])
    return digest(["relay-queue-v1", project, prefix + "-wave"])


def review_status(flow, request, owner, wave):
    project = request.receiver.project_id
    current = flow.status(project, request.source.launch_sha256, **owner)
    pending = flow._queue.owner_observe_pending(project, **owner)
    assert current["state"] == "incomplete" and current["task_status"] == "review"
    assert current["verification"] == current["publication"]["verification"] == "unverified"
    assert pending is not None and pending.wave_id == wave and pending.receipt_state == "admitted"
    return json.loads(json.dumps(current))


async def run_to_checkpoint(live, flow, request, core, state, entry, retain, **approved):
    project = request.receiver.project_id
    wave = receiver_wave(request)
    original_receiver = flow._relay.run_continuation_once
    original_record = flow._queue._journal.record
    diagnostic = publication = None

    async def observe_receiver(*args, **kwargs):
        nonlocal diagnostic, publication
        result = await original_receiver(*args, **kwargs)
        assert kwargs["_wave_key"] == wave and diagnostic is None
        diagnostic = await retain(result)
        publication = result
        return result

    def exit_before_record(project_key, wave_id, **result):
        if wave_id != wave:
            return original_record(project_key, wave_id, **result)
        assert project_key == digest(project) and diagnostic is not None
        actor, exact, snapshot, terminal, capture = diagnostic
        task_id = actor["task_id"]
        assert result == {
            "incomplete": False,
            "results": [{"task_id": task_id, "state": "ready_for_review"}],
        }
        assert exact and live.stopped(actor) and actor["exact_authorizations"] == 1
        attempt = actor["attempts"][0]
        assert attempt["status"] == "continuation_proposal_received" and not attempt["timed_out"]
        assert snapshot["state"] == "exited" and snapshot["parent_ended"] is True
        assert attempt["exit_code"] == snapshot["exit_code"] == 0 and terminal == "terminal"
        assert capture["saved"] is True and not any(
            snapshot[key] or capture[key] for key in ("stdout_truncated", "stderr_truncated")
        )
        current = review_status(flow, request, live.owner_args(state), wave)
        assert current["task_id"] == task_id
        assert current["source_task_id"] == request.source.source_task_id
        for field in ("context_id", "context_version", "content_sha256"):
            assert current["publication"][field] == getattr(publication, field)
        graph = live.task_graph(core, state)
        source_id, dependent_id = request.source.source_task_id, state["dependent"]["id"]
        assert set(graph) == {source_id, dependent_id, task_id}
        assert graph[source_id]["status"] == "failed"
        assert graph[source_id]["version"] == request.source.source_task_version + 1
        assert graph[dependent_id]["dependencies"] == [task_id]
        assert graph[dependent_id]["version"] == state["dependent"]["version"] + 1
        assert graph[task_id]["task_verification"] == "unverified"
        live.write(
            CHECKPOINT,
            {
                "identity": live.native_identity(),
                "authorization_sha256": entry["authorization_sha256"],
                "plan_sha256": entry["plan_sha256"],
                "wave_id": wave,
                "continuation": current,
                "tasks": graph,
                "receiver_observation_sha256": live.sha(
                    live.BASE / "receiver-dispatch-observation.json"
                ),
                "receipt_sha256": live.receipt_hashes("*.json"),
                "expected_exit_code": 73,
            },
            state,
        )
        print(
            json.dumps({"checkpoint": CHECKPOINT, "wave_id": wave, "task_id": task_id}), flush=True
        )
        os._exit(73)

    with (
        patch.object(flow._relay, "run_continuation_once", observe_receiver),
        patch.object(flow._queue._journal, "record", exit_before_record),
    ):
        return await flow.run_once(request, **approved)


def reconcile_cli(live, core, request, owner, state, wave):
    argv = [
        sys.executable,
        "-I",
        "-B",
        "-m",
        "agentsync",
        "--data-dir",
        str(core.data_dir),
        "relay-reconcile",
        wave,
        "--scratch-root",
        str(live.BASE),
        "--receipts",
        str(live.RECEIPTS),
    ]
    live.write("controller-reconcile-entry.json", {"argv": argv, "retry_allowed": False}, state)
    credentials = request.receiver.authentication() | owner
    result = subprocess.run(
        argv,
        input=json.dumps(credentials),
        cwd=live.BASE,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    for secret in (credentials["admin_token"], credentials["session_token"]):
        assert secret not in result.stdout + result.stderr
    live.write("controller-reconcile-exit.json", {"exit_code": result.returncode}, state)
    assert result.returncode == 0 and not result.stderr
    response = json.loads(result.stdout)
    assert response["ok"] is True
    return response["data"]


def recover(live, grant):
    """Run once in the fresh guest controller holding the existing lifecycle lock."""
    live.prep.runtime()
    core, state = live.core_state()
    request, approved = live.load_continuation(state, grant)
    checkpoint = live.read(CHECKPOINT)
    identity, prior = live.native_identity(), checkpoint["identity"]
    assert prior["boot_id"] == identity["boot_id"] and prior["pid"] != identity["pid"]
    assert not Path(f"/proc/{prior['pid']}").exists(), "Original controller exit unconfirmed."
    assert checkpoint["expected_exit_code"] == 73 and checkpoint["authorization_sha256"] == grant
    assert checkpoint["plan_sha256"] == approved["plan_sha256"]
    assert checkpoint["receiver_observation_sha256"] == live.sha(
        live.BASE / "receiver-dispatch-observation.json"
    )
    stopped = {"producer": "terminal_recorded", "receiver": "terminal_recorded"}
    assert live.cleanup.require_stopped(grant) == stopped
    owner = live.owner_args(state)
    flow = OwnerContinuation(core, live.BASE, live.RECEIPTS)
    before = checkpoint["continuation"]
    wave = receiver_wave(request)
    assert checkpoint["wave_id"] == wave and review_status(flow, request, owner, wave) == before
    callbacks = 0

    def forbid_receiver(*_):
        nonlocal callbacks
        callbacks += 1
        raise AssertionError("Recovery cannot launch a receiver.")

    def observe_saved():
        result = asyncio.run(
            flow.run_once(
                request,
                **owner,
                expected_plan_sha256=approved["plan_sha256"],
                build_receiver=forbid_receiver,
            )
        )
        assert callbacks == 0
        return json.loads(json.dumps(result))

    def unchanged():
        assert live.task_graph(core, state) == checkpoint["tasks"]
        assert live.receipt_hashes("*.json") == checkpoint["receipt_sha256"]
        assert (
            live.source_receipts(flow._relay, state, request.source.launch_sha256)
            == approved["source_receipt_sha256"]
        )

    unchanged()
    assert observe_saved() == json.loads(json.dumps(before))
    unchanged()
    outcome = reconcile_cli(live, core, request, owner, state, wave)
    live.write(
        RECONCILE,
        {
            "identity": identity,
            "checkpoint_sha256": live.sha(live.BASE / CHECKPOINT),
            "wave_id": wave,
            "outcome": outcome,
            "receiver_callbacks": callbacks,
            "model_calls": 0,
        },
        state,
    )
    assert outcome == {
        "state": "resolved",
        "verification": "unverified",
        "tasks": [
            {
                "task_id": before["task_id"],
                "state": "ready_for_review",
                "failure_code": None,
            }
        ],
    }
    current = observe_saved()
    assert current == before | {"state": "resolved", "wave": outcome}
    assert flow._queue.owner_observe_pending(request.receiver.project_id, **owner) is None
    unchanged()
    live.prep.require_fixtures(state)
    live.prep.runtime()
    actors = {
        actor: live.read(f"{actor}-dispatch-observation.json")["actors"][actor]
        for actor in ("producer", "receiver")
    }
    live.write(
        "dispatch-observation.json",
        {"timestamp": live.timestamp(), "actors": actors, "error_code": None, "outcome": current},
        state,
    )
    live.write(
        "continuation-result.json",
        {
            "status": "resolved",
            "error_code": None,
            "authorization_sha256": grant,
            "identity": identity,
            "plan_sha256": approved["plan_sha256"],
            "outcome": current,
            "tasks": checkpoint["tasks"],
            "publication_sha256": current["publication"]["content_sha256"],
            "retry_allowed": False,
        },
        state,
    )
    print(
        json.dumps({"state": current["state"], "task_id": current["task_id"], "model_calls": 0}),
        flush=True,
    )
    return 0


def approval_binding(live, original):
    checkpoint, reconciled = live.read(CHECKPOINT), live.read(RECONCILE)
    checkpoint_sha = live.sha(live.BASE / CHECKPOINT)
    assert reconciled["checkpoint_sha256"] == checkpoint_sha
    assert reconciled["identity"] == original["identity"] != checkpoint["identity"]
    assert checkpoint["plan_sha256"] == original["plan_sha256"]
    assert checkpoint["authorization_sha256"] == original["authorization_sha256"]
    assert reconciled["wave_id"] == checkpoint["wave_id"]
    assert reconciled["receiver_callbacks"] == reconciled["model_calls"] == 0
    assert original["outcome"] == checkpoint["continuation"] | {
        "state": "resolved",
        "wave": reconciled["outcome"],
    }
    return {
        "controller_exit_checkpoint_sha256": checkpoint_sha,
        "controller_reconcile_sha256": live.sha(live.BASE / RECONCILE),
    }

"""Disposable Core projects, Mock execution and actual host-process interruption."""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from conftest import owner_grant

import agentsync
import agentsync.durable_mock_workflow as workflow
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.mock_run_manager import MockRunManager
from agentsync.sdk import AgentSyncClient
from agentsync.storage import database


@pytest.fixture
def dedicated(tmp_path):
    client = AgentSyncClient(tmp_path / "state")
    auth = client.call("create_project", name="Dedicated Mock", root_path=str(tmp_path))["data"]
    return client, auth


def config(*tasks, **limits):
    return {
        "tasks": list(tasks) or [{"label": "build", "priority": 1, "capability": "build"}],
        "budget": {
            "steps": 8,
            "calls": 8,
            "requested_output": 4096,
            "estimated_tokens": 50000,
            "estimated_cost": 500000,
            "concurrency": 2,
        }
        | limits,
        "deadline_seconds": 25,
    }


def start(client, auth, settings):
    response = client.owner_call("start_mock_workflow", **auth, request_id="start", config=settings)
    assert response["ok"], response
    return response["data"]


def action(client, auth, operation, version, request_id):
    return client.owner_call(
        f"{operation}_mock_workflow", **auth, expected_version=version, request_id=request_id
    )


def status(client, auth):
    return client.owner_call("status_mock_workflow", **auth)["data"]


def cli_command(data, operation):
    return [
        sys.executable,
        "-s",
        "-B",
        "-m",
        "agentsync",
        "--data-dir",
        str(data),
        "workflow",
        operation,
    ]


def child_env():
    return os.environ | {"PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1])}


def cli(data, operation, payload):
    process = subprocess.run(
        cli_command(data, operation),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=20,
        env=child_env(),
        check=False,
        cwd=data.parent,
    )
    assert process.returncode in {0, 1}, process.stderr
    assert payload["admin_token"] not in process.stdout + process.stderr
    return json.loads(process.stdout)


def ordinary_worker(client, owner):
    actor = client.call("register_agent", **owner, name="Ordinary worker")["data"]
    owner_grant(client.core, owner, actor)
    return {
        "project_id": owner["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }


def test_durable_cli_decomposes_hands_off_and_independently_reviews(dedicated):
    client, auth = dedicated
    data = client.core.data_dir
    task = {"label": "build", "priority": 1, "capability": "build", "handoff_on_success": True}
    settings = config()
    settings.pop("tasks")
    settings["workers"] = [
        {"label": name, "capabilities": ["build"]} for name in ("one", "two", "peer")
    ]
    settings["decomposition"] = {
        "goal": "simulation only",
        "mock_response": json.dumps(
            {"tasks": [{"id": "build", "title": "Build", "summary": "Example", "depends_on": []}]}
        ),
        "task_options": [task],
    }
    result = cli(data, "start", auth | {"request_id": "start", "config": settings})["data"]
    assert result["state"] == "completed" and result["tasks"][0]["status"] == "completed"
    assert result["reserved"] == {
        "steps": 3,
        "calls": 3,
        "requested_output": 1088,
        "estimated_tokens": 17600,
        "estimated_cost": 176000,
    }
    assert result["cost_usd"] is None and result["billing_verified"] is False
    assert result["verification"] == "unverified"
    assert all(len(row["evidence_sha256"]) == 64 for row in result["attempts"])
    assert cli(data, "status", auth)["data"] == result
    assert start(client, auth, settings) == result
    assert action(client, auth, "resume", result["version"], "terminal-resume")["data"] == result
    with database.connect(client.core.db_path) as db:
        handoff = db.execute(
            "SELECT id,sender_agent_id,recipient_agent_id FROM handoffs"
        ).fetchone()
        review = db.execute("SELECT reviewer_agent_id,evidence FROM reviews").fetchone()
        assert review[0] not in tuple(handoff)[1:] and review[1] == "simulation_only/unverified"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert auth["admin_token"] not in "\n".join(db.iterdump())
    worker = ordinary_worker(client, auth)
    for operation, fields in (
        ("resolve_handoff", {"accept": True}),
        ("withdraw_handoff", {"reason": "fixture"}),
    ):
        denied = client.call(
            operation,
            **worker,
            handoff_id=handoff["id"],
            expected_version=1,
            request_id=operation,
            **fields,
        )
        assert denied["error"]["code"] == "workflow_managed_task"
    assert status(client, auth) == result


@pytest.mark.parametrize(
    "dimension",
    ["steps", "calls", "requested_output", "estimated_tokens", "estimated_cost", "concurrency"],
)
def test_budget_dimensions_refuse_before_mock_start(dedicated, dimension, monkeypatch):
    client, auth = dedicated

    async def unexpected(*args, **kwargs):
        pytest.fail("An unreserved Mock execution was started")

    monkeypatch.setattr(MockRunManager, "start_task", unexpected)
    result = start(client, auth, config(**{dimension: 0}))
    assert result["state"] == "stopped" and result["reason"] == dimension + "_budget_exhausted"
    assert not any(result["reserved"].values())


@pytest.mark.parametrize("checkpoint", ["scheduled", "reserved", "dispatch_intent"])
def test_host_exit_recovery_preserves_retry_reservation_and_uncertainty(dedicated, checkpoint):
    client, auth = dedicated
    data = client.core.data_dir
    payload = auth | {
        "request_id": "start",
        "config": config(
            {
                "label": "build",
                "priority": 1,
                "capability": "build",
                "first_retry_after_seconds": 1,
            },
            steps=2,
            calls=2,
        ),
    }
    driver = r"""
import json, os, sys
from agentsync.durable_mock_workflow import OwnerMockWorkflow
from agentsync.sdk import AgentSyncClient

stage, data = sys.argv[1:]
if stage == "scheduled":
    original = OwnerMockWorkflow._terminal
    def stop(self, *args, **kwargs):
        original(self, *args, **kwargs)
        os._exit(73)
    OwnerMockWorkflow._terminal = stop
else:
    method = "_next_batch" if stage == "reserved" else "_dispatch"
    original = getattr(OwnerMockWorkflow, method)
    def stop(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        assert result
        os._exit(73)
    setattr(OwnerMockWorkflow, method, stop)
AgentSyncClient(data).owner_call("start_mock_workflow", **json.load(sys.stdin))
"""
    process = subprocess.run(
        [sys.executable, "-s", "-B", "-c", driver, checkpoint, str(data)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        env=child_env(),
        cwd=data.parent,
        check=False,
    )
    assert process.returncode == 73 and process.stdout == "", process.stderr
    before = status(client, auth)
    assert before["reserved"]["steps"] == 1
    assert before["driver_until"] is not None
    assert (
        action(client, auth, "resume", before["version"], "too-soon")["error"]["code"]
        == "workflow_driver_active"
    )
    time.sleep(max(0, before["driver_until"] - time.time()) + 0.05)
    payload = auth | {"expected_version": before["version"]}
    with ThreadPoolExecutor(2) as pool:
        replies = list(
            pool.map(lambda n: cli(data, "resume", payload | {"request_id": f"resume-{n}"}), (1, 2))
        )
    assert sum(reply["ok"] for reply in replies) == 1
    after = cli(data, "status", auth)["data"]
    if checkpoint == "dispatch_intent":
        assert after["state"] == "unknown" and after["reserved"] == before["reserved"]
        assert [row["state"] for row in after["attempts"]] == ["unknown"]
        assert after["tasks"][0]["status"] == "running"
        worker = ordinary_worker(client, auth)
        managed = after["tasks"][0]
        ordinary = client.call(
            "create_task", **worker, title="Ordinary task", request_id="ordinary"
        )["data"]
        assert client.call(
            "claim_task",
            **worker,
            task_id=ordinary["id"],
            expected_version=1,
            lease_seconds=1,
            request_id="ordinary-claim",
        )["ok"]
        with database.connect(client.core.db_path) as db:
            # Force both leases into the past to exercise the actual reclaim
            # predicate without waiting on the independent 60-second task lease.
            db.execute(
                "UPDATE tasks SET lease_expires_at=0 WHERE id IN (?,?)",
                (ordinary["id"], managed["id"]),
            )
        assert client.call("reclaim_expired", **worker)["data"]["reclaimed_task_ids"] == [
            ordinary["id"]
        ]
        for operation, fields in (
            ("update_task", {"lease_token": "fixture", "status": "failed"}),
            ("review_task", {"accept": True, "evidence": "fixture"}),
            ("renew_lease", {"lease_token": "fixture"}),
        ):
            denied = client.call(
                operation,
                **worker,
                task_id=managed["id"],
                expected_version=managed["version"],
                request_id=operation,
                **fields,
            )
            assert denied["error"]["code"] == "workflow_managed_task"
        assert status(client, auth)["tasks"][0] == managed
        with database.connect(client.core.db_path) as db:
            assert (
                db.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE code='workflow_managed_task' AND outcome='denied'"
                ).fetchone()[0]
                == 3
            )
    elif checkpoint == "reserved":
        assert after["state"] == "waiting" and after["reserved"]["steps"] == 1
        assert [row["state"] for row in after["attempts"]] == ["failed", "scheduled"]
    else:
        assert after["state"] == "completed" and after["reserved"]["steps"] == 2
        assert [row["state"] for row in after["attempts"]] == ["failed", "succeeded"]


def test_cancel_pending_retry_and_reopen_does_not_refund(dedicated):
    client, auth = dedicated
    before = start(
        client,
        auth,
        config(
            {"label": "build", "priority": 1, "capability": "build", "first_retry_after_seconds": 4}
        ),
    )
    assert before["state"] == "waiting"
    cancelled = action(client, auth, "cancel", before["version"], "cancel")["data"]
    assert cancelled["state"] == "cancelled" and cancelled["reserved"] == before["reserved"]
    reopened = AgentSyncClient(client.core.data_dir)
    assert action(reopened, auth, "resume", cancelled["version"], "resume")["data"] == cancelled


def test_cancel_running_mock_persists_before_owned_cancellation(dedicated, monkeypatch):
    client, auth = dedicated
    started, proceed = Event(), Event()
    original = MockRunManager.start_task

    async def paused(self, *args, **kwargs):
        result = await original(self, *args, **kwargs)
        started.set()
        assert proceed.wait(3)
        return result

    monkeypatch.setattr(MockRunManager, "start_task", paused)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(start, client, auth, config())
        try:
            assert started.wait(3)
            before = status(client, auth)
            assert before["attempts"][0]["state"] == "dispatch_intent"
            assert action(client, auth, "cancel", before["version"], "cancel")["data"]["cancelled"]
        finally:
            proceed.set()
        final = future.result(timeout=10)
    assert final["state"] == "cancelled" and final["reserved"]["steps"] == 1
    assert final["attempts"][0]["state"] == final["tasks"][0]["status"] == "cancelled"


def test_cancel_after_mock_terminal_preserves_actual_outcome(dedicated, monkeypatch):
    client, auth = dedicated
    original = MockRunManager.finish_mock_run

    async def cancel_after_finish(self, *args, **kwargs):
        terminal = await original(self, *args, **kwargs)
        current = status(client, auth)
        assert action(client, auth, "cancel", current["version"], "late-cancel")["ok"]
        return terminal

    monkeypatch.setattr(MockRunManager, "finish_mock_run", cancel_after_finish)
    result = start(client, auth, config())
    assert result["state"] == "cancelled"
    assert result["attempts"][0]["state"] == "succeeded"
    assert result["tasks"][0]["status"] == "cancelled"


def test_batch_budget_limits_and_cross_project_scope(dedicated, tmp_path, monkeypatch):
    client, auth = dedicated
    starts = []
    original = MockRunManager.start_task

    async def count(self, actor, task):
        starts.append(task.task_id)
        return await original(self, actor, task)

    monkeypatch.setattr(MockRunManager, "start_task", count)
    result = start(
        client,
        auth,
        config(
            {"label": "high", "priority": 2, "capability": "build"},
            {"label": "low", "priority": 1, "capability": "test"},
            steps=1,
        ),
    )
    high, low = result["tasks"]
    assert starts == [high["id"]] and high["status"] == "completed" and low["status"] == "pending"
    assert result["reserved"]["steps"] == 1 and result["reason"] == "steps_budget_exhausted"
    foreign = client.call("create_project", name="Other project", root_path=str(tmp_path))["data"]
    actor = client.call("register_agent", **foreign, name="Foreign worker")["data"]
    assert client.owner_call(
        "set_agent_roles",
        **foreign,
        agent_id=actor["agent_id"],
        roles=["worker"],
        expected_version=1,
        request_id="grant",
    )["ok"]
    credentials = {
        "project_id": foreign["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    assert (
        client.call(
            "claim_task",
            **credentials,
            task_id=low["id"],
            expected_version=1,
            request_id="cross-project",
        )["error"]["code"]
        == "not_found"
    )


def test_deadline_and_clock_regression_survive_reopen(dedicated, monkeypatch):
    client, auth = dedicated
    now = time.time()
    monkeypatch.setattr(
        workflow, "time", type("Clock", (), {"time": lambda: now, "monotonic": time.monotonic})
    )
    before = start(
        client,
        auth,
        config(
            {"label": "build", "priority": 1, "capability": "build", "first_retry_after_seconds": 4}
        ),
    )
    assert before["state"] == "waiting"
    now -= 1
    reopened = AgentSyncClient(client.core.data_dir)
    assert (
        action(reopened, auth, "resume", before["version"], "rollback")["error"]["code"]
        == "clock_regressed"
    )
    now = before["deadline"] + 1
    final = action(reopened, auth, "resume", before["version"], "after-deadline")["data"]
    assert final["state"] == "stopped" and final["reason"] == "deadline_exhausted"
    assert final["reserved"] == before["reserved"]


def test_clock_rollback_does_not_block_owner_cancellation(dedicated, monkeypatch):
    client, auth = dedicated
    now = time.time()
    monkeypatch.setattr(
        workflow, "time", type("Clock", (), {"time": lambda: now, "monotonic": time.monotonic})
    )
    before = start(
        client,
        auth,
        config(
            {"label": "build", "priority": 1, "capability": "build", "first_retry_after_seconds": 4}
        ),
    )
    now -= 1
    after = action(client, auth, "cancel", before["version"], "rollback-cancel")["data"]
    assert after["state"] == "cancelled" and after["clock_regressed"]
    assert after["reserved"] == before["reserved"]


def test_resume_rotates_only_run_members_and_rejects_revoked_authority(dedicated, monkeypatch):
    client, auth = dedicated
    observed = []
    original = workflow.OwnerMockWorkflow._take_driver

    def capture(*args, **kwargs):
        driver = original(*args, **kwargs)
        observed.append(driver)
        return driver

    monkeypatch.setattr(workflow.OwnerMockWorkflow, "_take_driver", capture)
    before = start(
        client,
        auth,
        config(
            {"label": "build", "priority": 1, "capability": "build", "first_retry_after_seconds": 4}
        ),
    )
    agent = before["agent_ids"][0]
    revoked = client.owner_call(
        "set_agent_roles",
        **auth,
        agent_id=agent,
        roles=["reviewer"],
        expected_version=2,
        request_id="revoke",
    )
    assert revoked["ok"]
    assert (
        action(client, auth, "resume", before["version"], "revoked")["error"]["code"]
        == "workflow_membership_changed"
    )
    assert len(observed) == 1
    assert client.owner_call(
        "set_agent_roles",
        **auth,
        agent_id=agent,
        roles=["worker", "reviewer"],
        expected_version=3,
        request_id="restore",
    )["ok"]
    drive = workflow.OwnerMockWorkflow._drive
    checked = []

    def check_active_generation(runner, payload, current, configuration):
        previous, latest = observed
        assert current is latest and previous.generation + 1 == current.generation
        with runner._transaction(payload, write=False) as (db, now):
            run = runner._driver_run(db, payload, current, now)
            assert run["driver_until"] > now
            retry = db.execute(
                "SELECT request_id,task_id,sequence FROM mock_workflow_attempts WHERE state='scheduled'"
            ).fetchone()
        frozen = status(client, auth)
        with pytest.raises(AgentSyncError) as stale_dispatch:
            runner._dispatch(payload, previous, configuration, retry["request_id"])
        assert stale_dispatch.value.code == "workflow_driver_lost"
        with pytest.raises(AgentSyncError) as stale_terminal:
            runner._terminal(
                payload, previous, configuration, workflow._Effect(*tuple(retry)), "succeeded"
            )
        assert stale_terminal.value.code == "workflow_driver_lost"
        assert status(client, auth) == frozen
        checked.append(current.generation)
        return drive(runner, payload, current, configuration)

    monkeypatch.setattr(workflow.OwnerMockWorkflow, "_drive", check_active_generation)
    assert action(client, auth, "resume", before["version"], "rotate")["ok"]
    previous, latest = observed
    assert checked == [latest.generation]
    assert previous.credentials.keys() == latest.credentials.keys()
    old = previous.credentials[agent]
    assert client.call("list_tasks", **old)["error"]["code"] == "unauthorized"
    current = latest.credentials[agent]
    task = before["tasks"][0]
    assert (
        client.call(
            "claim_task",
            **current,
            task_id=task["id"],
            expected_version=task["version"],
            request_id="ordinary-claim",
        )["error"]["code"]
        == "workflow_managed_task"
    )
    with database.connect(client.core.db_path) as db:
        stored = "\n".join(db.iterdump())
    assert all(
        creds["session_token"] not in stored
        for driver in observed
        for creds in driver.credentials.values()
    )


def test_v15_upgrade_keeps_existing_core_data(tmp_path):
    data = tmp_path / "v15"
    data.mkdir()
    path = data / "agentsync.db"
    with database.connect(path) as db:
        db.executescript(database.SCHEMA)
        for version in range(2, 16):
            db.executescript(getattr(database, f"MIGRATION_V{version}"))
        db.execute("INSERT INTO projects VALUES('old','Old',?,'not-a-secret',0)", (str(tmp_path),))
    assert Core(data).db_path == path
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 16
        assert db.execute("SELECT name FROM projects WHERE id='old'").fetchone()[0] == "Old"
        assert db.execute("SELECT COUNT(*) FROM mock_workflows").fetchone()[0] == 0

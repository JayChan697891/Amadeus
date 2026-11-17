"""Owner recovery of abandoned handoff metadata in isolated Core databases."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import owner_grant

import agentsync
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient
from agentsync.storage.database import connect


@pytest.fixture
def abandoned(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: clock[0])
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "handoff", "root_path": str(tmp_path)})
    actors = [core.execute("register_agent", {**project, "name": name}) for name in ("a", "b")]
    for actor in actors:
        owner_grant(core, project, actor)
    sender = {
        "project_id": project["project_id"],
        "session_id": actors[0]["session_id"],
        "session_token": actors[0]["session_token"],
    }
    context = core.execute(
        "publish_context",
        {
            **sender,
            "kind": "note",
            "title": "Checkpoint",
            "content": "Keep this",
            "request_id": "ctx",
        },
    )
    task = core.execute("create_task", {**sender, "title": "unfinished", "request_id": "task"})
    lease = core.execute(
        "claim_task",
        {
            **sender,
            "task_id": task["id"],
            "expected_version": task["version"],
            "request_id": "claim",
        },
    )
    handoff = core.execute(
        "submit_handoff",
        {
            **sender,
            "task_id": task["id"],
            "lease_token": lease["lease_token"],
            "expected_version": lease["version"],
            "target_agent_id": actors[1]["agent_id"],
            "package": {
                "summary": "Continue the pending implementation",
                "completed_work": "Unverified partial work",
                "context_refs": [{"context_id": context["id"], "version": context["version"]}],
            },
            "request_id": "handoff",
        },
    )
    request = {
        **project,
        "task_id": task["id"],
        "handoff_id": handoff["id"],
        "expected_version": handoff["task_version"],
        "reason": "Both old sessions expired; recover coordination only",
        "request_id": "owner-recovery",
    }
    return core, project, actors, sender, handoff, request, clock


def test_owner_recovery_reports_unicode_reason_with_legacy_stdout(abandoned):
    core, _, _, _, original, request, _ = abandoned
    reason = "原会话已结束"
    source = Path(agentsync.__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            "-s",
            "-B",
            "-m",
            "agentsync",
            "--data-dir",
            str(core.data_dir),
            "owner",
            "recover_handoff",
        ],
        input=json.dumps(request | {"reason": reason}).encode("ascii"),
        env=os.environ | {"PYTHONIOENCODING": "cp1252", "PYTHONPATH": str(source)},
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert process.returncode == 0, process.stderr.decode("ascii", errors="replace")
    response = json.loads(process.stdout.decode("ascii"))
    assert response["ok"] is True
    result = response["data"]
    assert result["id"] == original["id"] and result["status"] == "recovered"
    assert result["reason"] == reason and result["execution_restarted"] is False


def test_owner_recovery_preserves_package_and_new_worker_can_continue(abandoned):
    core, project, _, sender, original, request, clock = abandoned
    clock[0] = 5000.0
    pending = core.execute_owner("list_handoffs", project)
    assert [item["id"] for item in pending["handoffs"]] == [original["id"]]
    assert not {"package", "contexts", "reason"} & pending["handoffs"][0].keys()
    reply = core.execute_owner("recover_handoff", request)
    assert reply["status"] == "recovered"
    assert reply["package"] == original["package"]
    assert reply["contexts"] == original["contexts"]
    assert reply["sender_agent_id"] == original["sender_agent_id"]
    assert reply["recipient_agent_id"] == original["recipient_agent_id"]
    assert reply["assigned_agent_id"] is None and reply["assignment_expires_at"] is None
    assert reply["version"] == original["task_version"] + 1
    assert reply["execution_restarted"] is False
    assert core.execute_owner("list_handoffs", project)["handoffs"] == []
    history = core.execute_owner("list_handoffs", {**project, "status": "recovered"})
    assert history["handoffs"][0]["id"] == original["id"]
    replacement = core.execute("register_agent", {**project, "name": "replacement"})
    owner_grant(core, project, replacement)
    auth = {
        "project_id": project["project_id"],
        "session_id": replacement["session_id"],
        "session_token": replacement["session_token"],
    }
    saved = core.execute("get_handoff", {**auth, "handoff_id": original["id"]})
    assert saved["contexts"] == original["contexts"]
    claimed = core.execute(
        "claim_task",
        {
            **auth,
            "task_id": original["task_id"],
            "expected_version": reply["version"],
            "request_id": "continue",
        },
    )
    reopened = Core(core.data_dir)
    assert reopened.execute_owner("recover_handoff", request) == reply
    current = reopened.execute("list_tasks", auth)["tasks"][0]
    assert current["status"] == "claimed" and current["version"] == claimed["version"]
    with pytest.raises(AgentSyncError):
        reopened.execute(
            "withdraw_handoff",
            {
                **sender,
                "handoff_id": original["id"],
                "expected_version": reply["version"],
                "reason": "old",
                "request_id": "old",
            },
        )
    audit = reopened.execute_owner("list_audit", project)["events"]
    successful = [
        item
        for item in audit
        if item["operation"] == "recover_handoff" and item["outcome"] == "success"
    ]
    assert len(successful) == 1
    assert successful[0]["post_version"] == reply["version"]


@pytest.mark.parametrize("expired", [(), (0,), (1,)])
def test_recovery_requires_both_participants_to_have_no_live_sessions(abandoned, expired):
    core, _, actors, _, original, request, _ = abandoned
    with connect(core.db_path) as db:
        for index in expired:
            db.execute(
                "UPDATE sessions SET expires_at=999 WHERE id=?", (actors[index]["session_id"],)
            )
    with pytest.raises(AgentSyncError) as failure:
        core.execute_owner("recover_handoff", request)
    assert failure.value.code == "handoff_participant_active"
    with connect(core.db_path) as db:
        stored = db.execute("SELECT status FROM handoffs WHERE id=?", (original["id"],)).fetchone()
        assert stored[0] == "pending"


def test_recovery_rejects_wrong_owner_task_version_and_changed_replay(abandoned):
    core, _, _, _, original, request, clock = abandoned
    clock[0] = 5000.0
    for change in (
        {"admin_token": "wrong"},
        {"task_id": "wrong"},
        {"expected_version": 1},
        {"reason": "   "},
    ):
        with pytest.raises(AgentSyncError):
            core.execute_owner("recover_handoff", request | change)
    reply = core.execute_owner("recover_handoff", request)
    with pytest.raises(AgentSyncError) as conflict:
        core.execute_owner("recover_handoff", request | {"reason": "changed"})
    assert conflict.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError):
        core.execute_owner(
            "recover_handoff",
            request | {"request_id": "again", "expected_version": reply["version"]},
        )
    client = AgentSyncClient(core.data_dir)
    assert client.owner_call("recover_handoff", **request)["data"] == reply
    assert original["task_version"] + 1 == reply["task_version"]


@pytest.mark.parametrize("participant", [0, 1])
def test_another_live_session_of_either_identity_still_blocks_recovery(abandoned, participant):
    core, _, actors, _, _, request, clock = abandoned
    clock[0] = 5000.0
    with connect(core.db_path) as db:
        db.execute(
            "INSERT INTO sessions SELECT ?,project_id,agent_id,token_hash,?,?,? "
            "FROM sessions WHERE id=?",
            (
                "additional-session",
                clock[0],
                clock[0],
                clock[0] + 600,
                actors[participant]["session_id"],
            ),
        )
    with pytest.raises(AgentSyncError) as failure:
        core.execute_owner("recover_handoff", request)
    assert failure.value.code == "handoff_participant_active"


def test_owner_handoff_listing_is_project_scoped(abandoned, tmp_path):
    core, _, _, _, _, request, clock = abandoned
    clock[0] = 5000.0
    other = core.execute("create_project", {"name": "other", "root_path": str(tmp_path)})
    assert core.execute_owner("list_handoffs", other)["handoffs"] == []
    with pytest.raises(AgentSyncError) as failure:
        core.execute_owner("recover_handoff", request | other)
    assert failure.value.code == "not_found"


def test_recovery_never_changes_durable_workflow_tasks(abandoned):
    core, project, _, _, original, request, clock = abandoned
    clock[0] = 5000.0
    with connect(core.db_path) as db:
        db.execute(
            "INSERT INTO mock_workflows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "owned-workflow",
                project["project_id"],
                "a" * 64,
                "{}",
                "b" * 64,
                "unknown",
                None,
                1,
                0,
                None,
                9000,
                1000,
                "{}",
                0,
            ),
        )
        db.execute(
            "INSERT INTO mock_workflow_tasks VALUES(?,?,?)",
            ("owned-workflow", original["task_id"], "task"),
        )
    with pytest.raises(AgentSyncError) as failure:
        core.execute_owner("recover_handoff", request)
    assert failure.value.code == "workflow_managed_task"
    with connect(core.db_path) as db:
        row = db.execute(
            "SELECT status,version FROM tasks WHERE id=?", (original["task_id"],)
        ).fetchone()
        assert (row["status"], row["version"]) == ("handoff", original["task_version"])

import io
import json
import sys

import pytest

from agentsync.adapters.approved_launch import digest
from agentsync.cli import main
from agentsync.controlled_relay import ControlledRelay
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue


def test_owner_recovers_pending_wave_identity_without_an_agent_session(tmp_path, monkeypatch, capsys):
    scratch = tmp_path.resolve()
    data = scratch / "core"
    receipts = scratch / "receipts"
    receipts.mkdir()
    core = Core(data)
    owner = core.execute("create_project", {"name": "Pilot", "root_path": str(scratch)})
    other = core.execute("create_project", {"name": "Other", "root_path": str(scratch)})
    queue = RelayQueue(ControlledRelay(core, scratch, receipts))
    project_id = owner["project_id"]
    project_key = digest(project_id)
    wave_id = digest("pending")
    queue._relay._check_receipt_anchor(project_id, bind=True)
    queue._check_journal_anchor(project_key, bind=True)
    queue._journal.admit(project_key, wave_id, ("isolated-task",))

    reopened = RelayQueue(ControlledRelay(Core(data), scratch, receipts))
    with pytest.raises(AgentSyncError) as rejected:
        reopened.owner_history(project_id, admin_token=other["admin_token"])
    assert rejected.value.code == "unauthorized"
    assert reopened.owner_observe_pending(
        other["project_id"], admin_token=other["admin_token"]
    ) is None

    credentials = {"project_id": project_id, "admin_token": owner["admin_token"]}
    payload = json.dumps(credentials).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))
    assert main([
        "--data-dir", str(data), "relay-status", "--scratch-root", str(scratch),
        "--receipts", str(receipts),
    ]) == 0
    output = capsys.readouterr().out
    assert owner["admin_token"] not in output
    pending = json.loads(output)["data"]
    assert pending["wave_id"] == wave_id
    assert pending["receipt_state"] == "admitted"
    assert pending["outcome"]["verification"] == "unverified"
    assert reopened.owner_history(**credentials).waves[0].wave_id == wave_id

    task_id = "isolated-task"
    queue._relay._record(
        digest([project_id, task_id]), "first-dispatched", client="codex",
        launch_request_sha256=digest("fixture request"),
    )
    other_attempts = reopened._relay.owner_inspect_attempts(
        other["project_id"], task_id, admin_token=other["admin_token"],
    )
    assert all(attempt.state == "not_dispatched" for attempt in other_attempts)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))
    assert main([
        "--data-dir", str(data), "relay-status", "--scratch-root", str(scratch),
        "--receipts", str(receipts), "--task-id", task_id,
    ]) == 0
    output = capsys.readouterr().out
    assert owner["admin_token"] not in output
    first, second = json.loads(output)["data"]["attempts"]
    assert first["state"] == "outcome_unknown"
    assert second["state"] == "not_dispatched"

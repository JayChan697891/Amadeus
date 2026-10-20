"""Audit persistence failures cannot commit business or permission changes."""

import sqlite3

import pytest

from agentsync.core.permissions import PermissionsMixin
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def world(tmp_path):
    core = Core(tmp_path / "state")
    owner = core.execute("create_project", {"name": "audit", "root_path": str(tmp_path)})
    agent = core.execute("register_agent", {**owner, "name": "member"})
    auth = {key: agent[key] for key in ("session_id", "session_token")}
    return core, owner, agent, {**auth, "project_id": owner["project_id"]}


def fail_audit(*_args, **_kwargs):
    raise sqlite3.OperationalError("Injected audit storage failure")


def grant(core, owner, agent, roles, version=1):
    return core.execute_owner(
        "set_agent_roles",
        {
            **owner,
            "agent_id": agent["agent_id"],
            "roles": roles,
            "expected_version": version,
            "request_id": f"roles-{version}",
        },
    )


def test_audit_failure_rolls_back_successful_task_mutation_and_cached_response(world, monkeypatch):
    core, owner, agent, auth = world
    grant(core, owner, agent, ["worker"])
    monkeypatch.setattr(PermissionsMixin, "_audit_event", staticmethod(fail_audit))
    with pytest.raises(AgentSyncError) as error:
        core.execute("create_task", {**auth, "title": "must roll back", "request_id": "task"})
    assert error.value.code == "storage_error"
    assert core.execute("list_tasks", auth)["tasks"] == []
    with sqlite3.connect(core.db_path) as db:
        assert (
            db.execute("SELECT count(*) FROM idempotency WHERE operation='create_task'").fetchone()[
                0
            ]
            == 0
        )


def test_audit_failure_rolls_back_owner_permission_grant(world, monkeypatch):
    core, owner, agent, auth = world
    monkeypatch.setattr(PermissionsMixin, "_audit_event", staticmethod(fail_audit))
    with pytest.raises(AgentSyncError) as error:
        grant(core, owner, agent, ["worker"])
    assert error.value.code == "storage_error"
    member = core.execute_owner("list_members", owner)["members"][0]
    assert member["roles"] == ["viewer"] and member["version"] == 1
    with pytest.raises(AgentSyncError) as denied:
        core.execute("create_task", {**auth, "title": "still denied", "request_id": "task"})
    assert denied.value.code == "forbidden"


def test_denial_audit_failure_never_restores_revoked_cached_write(world, monkeypatch):
    core, owner, agent, auth = world
    grant(core, owner, agent, ["worker"])
    payload = {**auth, "title": "original", "request_id": "task"}
    created = core.execute("create_task", payload)
    grant(core, owner, agent, [], version=2)
    monkeypatch.setattr(PermissionsMixin, "_audit_event", staticmethod(fail_audit))
    with pytest.raises(AgentSyncError) as error:
        core.execute("create_task", payload)
    assert error.value.code == "forbidden"
    with sqlite3.connect(core.db_path) as db:
        assert db.execute("SELECT id,title FROM tasks").fetchall() == [(created["id"], "original")]

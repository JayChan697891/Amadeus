"""Upgrade the exact v4 structures without losing physical locks or context."""

import sqlite3

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def test_repository_capture_rejects_nested_state_before_creating_managed_directories(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    core = Core(root / "private-state")
    project = core.execute("create_project", {"name": "overlap", "root_path": str(root)})
    agent = core.execute("register_agent", {**project, "name": "owner"})
    owner_grant(core, project, agent)
    auth = {key: agent[key] for key in ("session_id", "session_token")}
    with pytest.raises(AgentSyncError) as error:
        core.execute(
            "capture_repository",
            {**auth, "project_id": project["project_id"], "request_id": "capture"},
        )
    assert error.value.code == "workspace_boundary"
    assert not (core.data_dir / "managed-git").exists()


def test_v4_upgrade_preserves_resource_roots_locks_and_context(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    state = tmp_path / "state"
    core = Core(state)
    project = core.execute("create_project", {"name": "v4", "root_path": str(root)})
    agent = core.execute("register_agent", {**project, "name": "owner"})
    owner_grant(core, project, agent)
    auth = {key: agent[key] for key in ("session_id", "session_token")}
    auth["project_id"] = project["project_id"]
    task = core.execute("create_task", {**auth, "title": "keep", "request_id": "task"})
    context = core.execute(
        "publish_context",
        {**auth, "kind": "decision", "title": "keep", "content": "preserve", "request_id": "ctx"},
    )
    lock = core.execute("acquire_file_lock", {**auth, "path": "file", "request_id": "lock"})
    with sqlite3.connect(core.db_path) as db:
        roots_before = db.execute("SELECT * FROM project_resource_roots").fetchall()
        locks_before = db.execute("SELECT * FROM file_locks").fetchall()
        for table in (
            "verification_requests",
            "verification_attempts",
            "verification_jobs",
            "audit_events",
            "owner_idempotency",
            "approvals",
            "agent_memberships",
            "merge_candidates",
            "managed_worktrees",
            "repository_snapshots",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=4")
    upgraded = Core(state)
    owner_grant(upgraded, project, agent)
    assert upgraded.execute("list_tasks", auth)["tasks"][0]["id"] == task["id"]
    assert upgraded.execute("get_context", {**auth, "context_id": context["id"]}) == context
    assert (
        upgraded.execute("acquire_file_lock", {**auth, "path": "file", "request_id": "lock"})
        == lock
    )
    with sqlite3.connect(upgraded.db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        assert db.execute("SELECT * FROM project_resource_roots").fetchall() == roots_before
        assert db.execute("SELECT * FROM file_locks").fetchall() == locks_before
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

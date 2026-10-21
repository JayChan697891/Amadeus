"""Legacy history survives the deliberate default-viewer security migration."""

import json
import sqlite3

import pytest

from agentsync.core.service import Core, digest
from agentsync.errors import AgentSyncError
from agentsync.storage import database


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5])
def test_all_legacy_versions_preserve_history_and_require_explicit_write_regrant(tmp_path, version):
    root = tmp_path / "legacy-project"
    root.mkdir()
    (root / "unchanged.txt").write_text("historical user content", encoding="utf-8")
    data = tmp_path / "legacy-state"
    data.mkdir()
    path = data / "agentsync.db"
    with sqlite3.connect(path) as db:
        db.executescript(database.SCHEMA)
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?)",
            ("p", "legacy", str(root), digest("owner-secret"), 1.0),
        )
        for agent in ("a", "b"):
            db.execute(
                "INSERT INTO agents VALUES(?,?,?,?,?)",
                (agent, "p", "legacy-" + agent, '["worker"]', 1.0),
            )
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                (agent + "-session", "p", agent, digest("session-secret"), 1.0, 1.0, 99999999999.0),
            )
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "t",
                "p",
                "legacy task",
                "preserve description",
                7,
                "completed",
                5,
                "a-session",
                "preserve result",
                "[]",
                1.0,
                2.0,
                None,
                None,
                "preserve legacy asserted evidence",
            ),
        )
        for migration in range(2, version + 1):
            db.executescript(getattr(database, "MIGRATION_V" + str(migration)))
        tables = ["projects", "agents", "sessions", "tasks"]
        if version >= 2:
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)",
                ("t", "p", "b", "b-session", "preserve attributed evidence", 1, 2.0, 5),
            )
            tables.append("reviews")
        if version >= 3:
            db.execute(
                "INSERT INTO context_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "context",
                    "p",
                    1,
                    "decision",
                    "legacy decision",
                    "historical content",
                    "summary",
                    "source",
                    "a",
                    "a-session",
                    1.0,
                    2.0,
                ),
            )
            db.execute(
                "INSERT INTO context_search VALUES(?,?,?,?,?,?,?)",
                (
                    "context",
                    "p",
                    "decision",
                    "legacy decision",
                    "historical content",
                    "summary",
                    "source",
                ),
            )
            tables.append("context_revisions")
        if version >= 4:
            db.execute(
                "INSERT INTO file_locks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "lock",
                    "p",
                    "unchanged.txt",
                    str(root / "unchanged.txt"),
                    "file",
                    "a",
                    "a-session",
                    1,
                    "released",
                    1.0,
                    2.0,
                    3.0,
                    digest("lease-secret"),
                ),
            )
            tables.append("file_locks")
        if version >= 5:
            db.execute(
                "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
                (
                    "snapshot",
                    "p",
                    "a-session",
                    1.0,
                    json.dumps({"historical": "receipt preserved"}),
                ),
            )
            tables.append("repository_snapshots")
        before = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
    core = Core(data)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 9
        for table, rows in before.items():
            assert db.execute("SELECT * FROM " + table).fetchall() == rows, table
    owner = {"project_id": "p", "admin_token": "owner-secret"}
    members = core.execute_owner("list_members", owner)["members"]
    assert {member["agent_id"] for member in members} == {"a", "b"}
    assert all(member["roles"] == ["viewer"] and member["version"] == 1 for member in members)
    auth = {"project_id": "p", "session_id": "a-session", "session_token": "session-secret"}
    task = core.execute("list_tasks", auth)["tasks"][0]
    assert task["result"] == "preserve result" and task["version"] == 5
    with pytest.raises(AgentSyncError) as error:
        core.execute(
            "create_task", {**auth, "title": "must be denied", "request_id": "legacy-write"}
        )
    assert error.value.code == "forbidden"
    core.execute_owner(
        "set_agent_roles",
        {
            **owner,
            "agent_id": "a",
            "roles": ["worker", "reviewer"],
            "expected_version": 1,
            "request_id": "explicit-regrant",
        },
    )
    assert (
        core.execute(
            "create_task",
            {**auth, "title": "explicitly authorized", "request_id": "authorized-write"},
        )["title"]
        == "explicitly authorized"
    )
    reopened = Core(data)
    assert (
        next(item for item in reopened.execute("list_tasks", auth)["tasks"] if item["id"] == "t")
        == task
    )
    assert (root / "unchanged.txt").read_text() == "historical user content"

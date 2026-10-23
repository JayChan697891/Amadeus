"""M4 upgrades preserve legacy tasks, attributed reviews and FTS context."""

import sqlite3

import pytest
from conftest import owner_grant

from agentsync.core.service import Core, digest
from agentsync.storage.database import MIGRATION_V2, MIGRATION_V3, SCHEMA


@pytest.mark.parametrize("version", [1, 2, 3])
def test_m4_upgrade_preserves_data_and_reopened_resource_locks(tmp_path, version):
    root = tmp_path / "resources"
    root.mkdir()
    (root / "file").write_text("keep file")
    data_dir = tmp_path / f"v{version}"
    data_dir.mkdir()
    path = data_dir / "agentsync.db"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?)",
            ("p", "Legacy", str(root), digest("admin"), 1.0),
        )
        for agent in ("a", "b"):
            db.execute("INSERT INTO agents VALUES(?,?,?,?,?)", (agent, "p", agent, "[]", 1.0))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                (agent + "-session", "p", agent, digest("token"), 1.0, 1.0, 99999999999.0),
            )
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "t",
                "p",
                "Keep task",
                "Keep description",
                7,
                "completed",
                5,
                "a-session",
                "Keep result",
                "[]",
                1.0,
                2.0,
                None,
                None,
                "Keep evidence",
            ),
        )
        if version >= 2:
            db.executescript(MIGRATION_V2)
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)",
                ("t", "p", "b", "b-session", "Attributed evidence", 1, 2.0, 5),
            )
        if version >= 3:
            db.executescript(MIGRATION_V3)
            db.execute(
                "INSERT INTO context_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "context",
                    "p",
                    1,
                    "decision",
                    "Keep context",
                    "Historical content",
                    "summary",
                    "source",
                    "a",
                    "a-session",
                    1.0,
                    1.0,
                ),
            )
            db.execute(
                "INSERT INTO context_search VALUES(?,?,?,?,?,?,?)",
                (
                    "context",
                    "p",
                    "decision",
                    "Keep context",
                    "Historical content",
                    "summary",
                    "source",
                ),
            )
    core = Core(data_dir)
    owner_grant(core, {"project_id": "p", "admin_token": "admin"}, {"agent_id": "a"}, ("worker",))
    auth = {"project_id": "p", "session_id": "a-session", "session_token": "token"}
    original_task = core.execute("list_tasks", auth)["tasks"][0]
    assert original_task["description"] == "Keep description"
    assert original_task["result"] == "Keep result"
    if version >= 2:
        assert original_task["latest_review"]["evidence"] == "Attributed evidence"
    else:
        assert original_task["latest_review"] is None
    lock = core.execute("acquire_file_lock", {**auth, "path": "file", "request_id": "lock"})
    reopened = Core(data_dir)
    assert reopened.execute("list_file_locks", auth)["locks"] == [
        {key: value for key, value in lock.items() if key != "lease_token"}
    ]
    assert reopened.execute("list_tasks", auth)["tasks"][0] == original_task
    assert (root / "file").read_text() == "keep file"
    if version >= 3:
        context = reopened.execute("get_context", {**auth, "context_id": "context", "version": 1})
        assert context["content"] == "Historical content"
        assert reopened.execute("search_context", {**auth, "query": "Historical"})["entries"] == [
            context
        ]
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 10
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT review_evidence FROM tasks WHERE id='t'").fetchone()[0]
            == "Keep evidence"
        )
        assert db.execute(
            "SELECT typeof(device),typeof(inode) FROM project_resource_roots"
        ).fetchone() == ("text", "text")

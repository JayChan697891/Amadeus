"""Upgrade actual legacy rows, retaining task/review and new context data."""

import sqlite3

import pytest
from conftest import owner_grant

from agentsync.core.service import Core, digest
from agentsync.storage.database import MIGRATION_V2, SCHEMA


@pytest.mark.parametrize("version", [1, 2])
def test_m3_migration_preserves_legacy_rows_and_reopens(tmp_path, version):
    data_dir = tmp_path / f"v{version}"
    data_dir.mkdir()
    path = data_dir / "agentsync.db"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?)",
            ("p", "Legacy", str(tmp_path), digest("admin"), 1.0),
        )
        db.execute("INSERT INTO agents VALUES(?,?,?,?,?)", ("a", "p", "Legacy author", "[]", 1.0))
        db.execute("INSERT INTO agents VALUES(?,?,?,?,?)", ("b", "p", "Legacy reviewer", "[]", 1.0))
        for session, agent in (("s", "a"), ("r", "b")):
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                (session, "p", agent, digest("token"), 1.0, 1.0, 99999999999.0),
            )
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "t",
                "p",
                "Keep title",
                "Keep description",
                7,
                "completed",
                5,
                "s",
                "Keep result",
                "[]",
                1.0,
                2.0,
                None,
                None,
                "Keep evidence",
            ),
        )
        if version == 2:
            db.executescript(MIGRATION_V2)
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)",
                ("t", "p", "b", "r", "Keep evidence", 1, 2.0, 5),
            )
    core = Core(data_dir)
    owner_grant(core, {"project_id": "p", "admin_token": "admin"}, {"agent_id": "a"}, ("worker",))
    auth = {"project_id": "p", "session_id": "s", "session_token": "token"}
    task = core.execute("list_tasks", auth)["tasks"][0]
    assert (task["title"], task["description"], task["result"], task["version"]) == (
        "Keep title",
        "Keep description",
        "Keep result",
        5,
    )
    if version == 2:
        assert task["latest_review"]["reviewer_agent_id"] == "b"
        assert task["latest_review"]["evidence"] == "Keep evidence"
    else:
        assert task["latest_review"] is None
    context = core.execute(
        "publish_context",
        {
            **auth,
            "kind": "progress",
            "title": "迁移",
            "content": "Migration searchable",
            "request_id": "context",
        },
    )
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute("SELECT review_evidence FROM tasks WHERE id='t'").fetchone()[0]
            == "Keep evidence"
        )
    reopened = Core(data_dir)
    assert reopened.execute("list_tasks", auth)["tasks"][0] == task
    assert reopened.execute("search_context", {**auth, "query": "迁移"})["entries"] == [context]
    assert (
        reopened.execute("get_context", {**auth, "context_id": context["id"], "version": 1})
        == context
    )


def test_future_schema_is_rejected_without_downgrade(tmp_path):
    data_dir = tmp_path / "future"
    data_dir.mkdir()
    path = data_dir / "agentsync.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
        db.execute("CREATE TABLE future_payload(value TEXT)")
        db.execute("INSERT INTO future_payload VALUES('preserve')")
    with pytest.raises(RuntimeError):
        Core(data_dir)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999
        assert db.execute("SELECT value FROM future_payload").fetchone()[0] == "preserve"

"""Real SQLite history migration; reused Docker policy fixture is simulated."""

import sqlite3

import pytest
from conftest import drop_candidate_queue_schema
from test_verification_reconciliation import pending as pending
from test_verification_reconciliation import request
from test_verification_reconciliation import transport as transport

from agentsync.storage import database


def history(db):
    names = [
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    ]
    return {
        name: [tuple(row) for row in db.execute('SELECT * FROM "' + name + '"')] for name in names
    }


def schema(db):
    return [
        tuple(row)
        for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")
    ]


def legacy(pending):
    core = pending[0]
    request(pending)
    with database.connect(core.db_path) as db:
        drop_candidate_queue_schema(db)
        db.execute("PRAGMA user_version=9")
        before = history(db)
        for name in (
            "verification_jobs",
            "verification_attempts",
            "verification_executions",
            "verification_reconciliations",
        ):
            assert before[name], name
        return core.db_path, before, schema(db)


def test_v9_populated_execution_history_survives_v10_and_reopen(pending, transport):
    path, before, _ = legacy(pending)
    database.migrate(path)
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        after = history(db)
        assert all(after[name] == rows for name, rows in before.items())
        assert after["candidate_verification_jobs"] == []
        assert after["candidate_verification_requests"] == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_v10_failure_rolls_back_schema_indexes_version_and_rows(pending, transport, monkeypatch):
    path, before, old_schema = legacy(pending)
    migration = database.MIGRATION_V10
    monkeypatch.setattr(database, "MIGRATION_V10", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 9
        assert history(db) == before
        assert schema(db) == old_schema
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    monkeypatch.setattr(database, "MIGRATION_V10", migration)
    database.migrate(path)


def test_future_schema15_rejected_without_mutating_existing_database(tmp_path):
    path = tmp_path / "future.db"
    database.migrate(path)
    with database.connect(path) as db:
        db.execute("PRAGMA user_version=15")
        before, old_schema = history(db), schema(db)
    with pytest.raises(RuntimeError, match="Unsupported"):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 15
        assert history(db) == before and schema(db) == old_schema


def test_fresh_schema10_starts_with_empty_candidate_queue(tmp_path):
    path = tmp_path / "new.db"
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert db.execute("SELECT count(*) FROM candidate_verification_jobs").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM candidate_verification_requests").fetchone()[0] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

"""Real SQLite v10 schema with copied disposable queued/cancelled history."""

import sqlite3

import pytest
from test_candidate_jobs import cancel, enqueue, owner
from test_candidate_jobs import prepared as prepared
from test_candidate_jobs import world as world

from agentsync.core.service import Core
from agentsync.storage import database
from agentsync.verification.candidate_jobs import CandidateVerificationJobs


def tables(db):
    return [
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'context_search%' ORDER BY name"
        )
    ]


def history(db):
    return {
        name: [tuple(row) for row in db.execute('SELECT * FROM "' + name + '"')]
        for name in tables(db)
    }


def schema(db):
    return [
        tuple(row)
        for row in db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name")
    ]


@pytest.fixture
def v10(prepared, tmp_path):
    first = enqueue(prepared, request_id="keep-queued")
    second = enqueue(prepared, request_id="keep-cancelled")
    cancel(prepared, second)
    path = tmp_path / "legacy10" / "agentsync.db"
    path.parent.mkdir()
    # Build actual historical DDL, not a current schema with a downgraded version.
    with database.connect(path) as target:
        target.executescript(database.SCHEMA)
        for version in range(2, 11):
            target.executescript(getattr(database, "MIGRATION_V" + str(version)))
        target.execute("BEGIN")
        target.execute("PRAGMA defer_foreign_keys=ON")
        with database.connect(prepared[0].db_path) as source:
            for name in tables(target):
                columns = [row[1] for row in target.execute('PRAGMA table_info("' + name + '")')]
                rows = source.execute(
                    "SELECT " + ",".join(columns) + ' FROM "' + name + '"'
                ).fetchall()
                for row in rows:
                    target.execute(
                        'INSERT INTO "'
                        + name
                        + '"('
                        + ",".join(columns)
                        + ") VALUES("
                        + ",".join("?" for _ in columns)
                        + ")",
                        tuple(row),
                    )
        target.commit()
        assert target.execute("PRAGMA user_version").fetchone()[0] == 10
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        before = history(target)
        old_schema = schema(target)
    return path, before, old_schema, owner(prepared), first, second


def test_v10_queued_and_cancelled_history_survives_upgrade_and_reopen(v10):
    path, before, _, auth, first, second = v10
    database.migrate(path)
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 15
        after = history(db)
        assert all(after[name] == rows for name, rows in before.items())
        assert after["candidate_verification_claims"] == []
        assert after["candidate_claim_recoveries"] == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    service = CandidateVerificationJobs(Core(path.parent))
    assert service.get(**auth, job_id=first["id"])["status"] == "queued"
    assert service.get(**auth, job_id=second["id"])["status"] == "cancelled"


def test_v11_failed_rebuild_rolls_back_tables_indexes_receipts_and_version(v10, monkeypatch):
    path, before, old_schema, _, _, _ = v10
    migration = database.MIGRATION_V11
    monkeypatch.setattr(database, "MIGRATION_V11", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 10
        assert history(db) == before and schema(db) == old_schema
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    monkeypatch.setattr(database, "MIGRATION_V11", migration)
    database.migrate(path)


def test_future_schema_rejected_without_any_mutation(v10):
    future_version = database.SCHEMA_VERSION + 1
    path, before, old_schema, _, _, _ = v10
    with database.connect(path) as db:
        db.execute(f"PRAGMA user_version={future_version}")
    with pytest.raises(RuntimeError, match="Unsupported"):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == future_version
        assert history(db) == before and schema(db) == old_schema


def test_fresh_schema12_starts_without_fabricated_claim_history(tmp_path):
    path = tmp_path / "fresh.db"
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 15
        assert db.execute("SELECT count(*) FROM candidate_verification_claims").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM candidate_claim_recoveries").fetchone()[0] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

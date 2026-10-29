"""Real SQLite v11 DDL with copied disposable API history in all four states."""

import sqlite3

import pytest
from test_candidate_claims import claim, recover
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
def v11(prepared, tmp_path):
    first = enqueue(prepared, request_id="keep-queued")
    second = enqueue(prepared, request_id="keep-cancelled")
    cancel(prepared, second)
    third = enqueue(prepared, request_id="keep-claimed")
    fourth = enqueue(prepared, request_id="keep-interrupted")
    claim(prepared, third)
    recover(prepared, claim(prepared, fourth))
    path = tmp_path / "legacy11" / "agentsync.db"
    path.parent.mkdir()
    # Build actual historical DDL, not a current schema with a downgraded version.
    with database.connect(path) as target:
        target.executescript(database.SCHEMA)
        for version in range(2, 12):
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
        assert target.execute("PRAGMA user_version").fetchone()[0] == 11
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        before = history(target)
        old_schema = schema(target)
    return path, before, old_schema, owner(prepared), [first, second, third, fourth], prepared[1]


def test_v11_all_states_and_history_survive_additive_upgrade_and_reopen(v11):
    path, before, _, auth, jobs, enqueue_args = v11
    database.migrate(path)
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 13
        after = history(db)
        assert all(after[name] == rows for name, rows in before.items())
        assert len(after["candidate_verification_claims"]) == 2
        assert len(after["candidate_claim_recoveries"]) == 1
        assert after["candidate_execution_intents"] == []
        assert after["candidate_intent_abandonments"] == []
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    service = CandidateVerificationJobs(Core(path.parent))
    from test_candidate_jobs import profile

    from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents

    intents = OwnerCandidateExecutionIntents(service.core)
    for original, state, request in zip(
        jobs,
        ["queued", "cancelled", "claimed", "interrupted"],
        ["keep-queued", "keep-cancelled", "keep-claimed", "keep-interrupted"],
        strict=True,
    ):
        assert service.get(**auth, job_id=original["id"])["status"] == state
        assert intents.get(**auth, job_id=original["id"])["intent"] is None
        assert service.enqueue(**enqueue_args, request_id=request, profile=profile()) == original


def test_v12_failed_addition_rolls_back_tables_indexes_history_and_version(v11, monkeypatch):
    path, before, old_schema, _, _, _ = v11
    migration = database.MIGRATION_V12
    monkeypatch.setattr(database, "MIGRATION_V12", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 11
        assert history(db) == before and schema(db) == old_schema
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    monkeypatch.setattr(database, "MIGRATION_V12", migration)
    database.migrate(path)


def test_future_schema14_rejected_without_any_mutation(v11):
    path, before, old_schema, _, _, _ = v11
    with database.connect(path) as db:
        db.execute("PRAGMA user_version=14")
    with pytest.raises(RuntimeError, match="Unsupported"):
        database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert history(db) == before and schema(db) == old_schema


def test_fresh_schema12_starts_without_fabricated_intent_history(tmp_path):
    path = tmp_path / "fresh.db"
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 13
        assert db.execute("SELECT count(*) FROM candidate_execution_intents").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM candidate_intent_abandonments").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM candidate_verification_claims").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM candidate_claim_recoveries").fetchone()[0] == 0
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

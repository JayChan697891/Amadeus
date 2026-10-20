import sqlite3
import time
from pathlib import Path

# Historical v1 schema, applied only to empty databases before incremental upgrades.
SCHEMA = """
CREATE TABLE projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, root_path TEXT NOT NULL,
 admin_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE agents(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 name TEXT NOT NULL, capabilities TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE sessions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 agent_id TEXT NOT NULL REFERENCES agents(id), token_hash TEXT NOT NULL,
 created_at REAL NOT NULL, heartbeat_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE tasks(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 title TEXT NOT NULL, description TEXT NOT NULL, priority INTEGER NOT NULL,
 status TEXT NOT NULL, version INTEGER NOT NULL, owner_session_id TEXT REFERENCES sessions(id),
 result TEXT NOT NULL, dependencies TEXT NOT NULL, created_at REAL NOT NULL,
 updated_at REAL NOT NULL, lease_hash TEXT, lease_expires_at REAL, review_evidence TEXT);
CREATE INDEX tasks_project ON tasks(project_id);
CREATE TABLE idempotency(project_id TEXT NOT NULL, session_id TEXT NOT NULL,
 operation TEXT NOT NULL, request_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 response TEXT NOT NULL, PRIMARY KEY(project_id, session_id, operation, request_id));
PRAGMA user_version=1;
"""

MIGRATION_V2 = """
CREATE TABLE reviews(
 task_id TEXT NOT NULL REFERENCES tasks(id),
 project_id TEXT NOT NULL REFERENCES projects(id),
 reviewer_agent_id TEXT NOT NULL REFERENCES agents(id),
 reviewer_session_id TEXT NOT NULL REFERENCES sessions(id),
 evidence TEXT NOT NULL,
 accept INTEGER NOT NULL CHECK(accept IN (0,1)),
 created_at REAL NOT NULL,
 version INTEGER NOT NULL,
 PRIMARY KEY(task_id, version));
CREATE INDEX reviews_project ON reviews(project_id, task_id, version);
PRAGMA user_version=2;
"""


MIGRATION_V3 = """
CREATE TABLE context_revisions(
 context_id TEXT NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
 version INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 summary TEXT NOT NULL, source TEXT NOT NULL,
 author_agent_id TEXT NOT NULL REFERENCES agents(id),
 author_session_id TEXT NOT NULL REFERENCES sessions(id),
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 PRIMARY KEY(context_id,version));
CREATE INDEX contexts_project ON context_revisions(project_id,context_id,version);
CREATE VIRTUAL TABLE context_search USING fts5(
 context_id UNINDEXED, project_id UNINDEXED, kind UNINDEXED,
 title, content, summary, source, tokenize='trigram');
CREATE TABLE handoffs(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 task_id TEXT NOT NULL REFERENCES tasks(id),
 sender_agent_id TEXT NOT NULL REFERENCES agents(id),
 sender_session_id TEXT NOT NULL REFERENCES sessions(id),
 recipient_agent_id TEXT NOT NULL REFERENCES agents(id),
 package TEXT NOT NULL, contexts TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT NOT NULL,
 created_at REAL NOT NULL, resolved_at REAL, task_version INTEGER NOT NULL,
 assigned_agent_id TEXT REFERENCES agents(id), reservation_expires_at REAL);
CREATE INDEX handoffs_task ON handoffs(project_id,task_id,task_version);
PRAGMA user_version=3;
"""


MIGRATION_V4 = """
CREATE TABLE project_resource_roots(
 project_id TEXT PRIMARY KEY REFERENCES projects(id), root_path TEXT NOT NULL,
 device TEXT NOT NULL, inode TEXT NOT NULL);
CREATE TABLE file_locks(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 path TEXT NOT NULL, resource_key TEXT NOT NULL, kind TEXT NOT NULL,
 owner_agent_id TEXT NOT NULL REFERENCES agents(id),
 owner_session_id TEXT NOT NULL REFERENCES sessions(id),
 version INTEGER NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL,
 updated_at REAL NOT NULL, expires_at REAL NOT NULL, lease_hash TEXT NOT NULL);
CREATE INDEX file_locks_active ON file_locks(status,expires_at,resource_key);
CREATE INDEX file_locks_project ON file_locks(project_id,created_at,id);
PRAGMA user_version=4;
"""


MIGRATION_V5 = """
CREATE TABLE repository_snapshots(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 creator_session_id TEXT NOT NULL REFERENCES sessions(id),
 created_at REAL NOT NULL, receipt TEXT NOT NULL);
CREATE INDEX repository_snapshots_project ON repository_snapshots(project_id,id);
CREATE TABLE managed_worktrees(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 snapshot_id TEXT NOT NULL REFERENCES repository_snapshots(id),
 task_id TEXT NOT NULL REFERENCES tasks(id),
 creator_session_id TEXT NOT NULL REFERENCES sessions(id),
 created_at REAL NOT NULL, receipt TEXT NOT NULL);
CREATE INDEX managed_worktrees_project ON managed_worktrees(project_id,id);
CREATE TABLE merge_candidates(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 left_id TEXT NOT NULL REFERENCES managed_worktrees(id),
 right_id TEXT NOT NULL REFERENCES managed_worktrees(id),
 creator_session_id TEXT NOT NULL REFERENCES sessions(id),
 created_at REAL NOT NULL, receipt TEXT NOT NULL);
CREATE INDEX merge_candidates_project ON merge_candidates(project_id,id);
PRAGMA user_version=5;
"""


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def migrate(path: Path) -> None:
    db = connect(path)
    try:
        _enable_wal(db)
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            # execute one statement at a time: executescript would commit our lock.
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 1
        if version == 1:
            # v1 evidence remains in tasks; unknown historical reviewer IDs are not invented.
            for statement in MIGRATION_V2.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 2
        if version == 2:
            for statement in MIGRATION_V3.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 3
        if version == 3:
            for statement in MIGRATION_V4.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 4
        if version == 4:
            for statement in MIGRATION_V5.split(";"):
                if statement.strip():
                    db.execute(statement)
        elif version != 5:
            raise RuntimeError("Unsupported AgentSync database schema version.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _enable_wal(db: sqlite3.Connection) -> None:
    """Retry journal transitions, which can bypass SQLite's busy timeout.

    Multiple fresh processes may request the WAL transition simultaneously.
    Retry only transient SQLite lock codes, before opening a migration transaction.
    Schema statements themselves remain protected by one BEGIN IMMEDIATE.
    """
    deadline = time.monotonic() + 30.0
    delay = 0.01
    while True:
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", None)
            if (
                code is None
                or code & 0xFF not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                or time.monotonic() >= deadline
            ):
                raise
            time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(delay * 2, 0.2)

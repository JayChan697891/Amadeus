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


MIGRATION_V6 = """
CREATE TABLE agent_memberships(
 agent_id TEXT PRIMARY KEY REFERENCES agents(id), project_id TEXT NOT NULL REFERENCES projects(id),
 roles TEXT NOT NULL, version INTEGER NOT NULL, updated_at REAL NOT NULL);
INSERT INTO agent_memberships SELECT id,project_id,'["viewer"]',1,created_at FROM agents;
CREATE INDEX agent_memberships_project ON agent_memberships(project_id,agent_id);
CREATE TABLE approvals(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 requester_agent_id TEXT NOT NULL REFERENCES agents(id), action TEXT NOT NULL,
 subject_id TEXT NOT NULL REFERENCES merge_candidates(id), subject_sha TEXT NOT NULL,
 subject_version INTEGER NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,
 created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL, reason TEXT NOT NULL);
CREATE INDEX approvals_requester ON approvals(project_id,requester_agent_id,created_at,id);
CREATE TABLE owner_idempotency(
 project_id TEXT NOT NULL REFERENCES projects(id), operation TEXT NOT NULL,
 request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, response TEXT NOT NULL,
 PRIMARY KEY(project_id,operation,request_id));
CREATE TABLE audit_events(
 event_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 actor_kind TEXT NOT NULL, actor_id TEXT NOT NULL, operation TEXT NOT NULL,
 target_id TEXT, outcome TEXT NOT NULL, code TEXT NOT NULL,
 pre_version INTEGER, post_version INTEGER, request_id_digest TEXT, time REAL NOT NULL);
CREATE INDEX audit_events_project ON audit_events(project_id,time,event_id);
PRAGMA user_version=6;
"""


MIGRATION_V7 = """
CREATE TABLE verification_jobs(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 snapshot_id TEXT NOT NULL REFERENCES repository_snapshots(id), commit_sha TEXT NOT NULL,
 profile_kind TEXT NOT NULL, profile_sha256 TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','cancel_requested','cancelled','interrupted')),
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 9223372036854775806),
 attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 0 AND 9223372036854775806),
 current_attempt_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(id,project_id));
CREATE INDEX verification_jobs_project ON verification_jobs(project_id,created_at,id);
CREATE TABLE verification_attempts(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
 attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 9223372036854775806),
 token_hash TEXT NOT NULL, lease_expires_at REAL NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','cancel_requested','cancelled','interrupted')),
 reason_code TEXT NOT NULL CHECK(reason_code IN ('','owner_cancelled','lease_expired','service_interrupted')),
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs(id,project_id),
 UNIQUE(job_id,attempt_number));
CREATE INDEX verification_attempts_expiry ON verification_attempts(status,lease_expires_at);
CREATE TABLE verification_requests(
 project_id TEXT NOT NULL REFERENCES projects(id), operation TEXT NOT NULL,
 request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, job_id TEXT NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs(id,project_id),
 PRIMARY KEY(project_id,operation,request_id));
PRAGMA user_version=7;
"""


MIGRATION_V8 = """
CREATE TABLE verification_jobs_v8(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
 snapshot_id TEXT NOT NULL REFERENCES repository_snapshots(id), commit_sha TEXT NOT NULL,
 profile_kind TEXT NOT NULL, profile_sha256 TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','cancel_requested','cancelled','interrupted','finished','cleanup_pending')),
 version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 9223372036854775806),
 attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 0 AND 9223372036854775806),
 current_attempt_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(id,project_id));
CREATE TABLE verification_attempts_v8(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
 attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 9223372036854775806),
 token_hash TEXT NOT NULL, lease_expires_at REAL NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','cancel_requested','cancelled','interrupted','finished','cleanup_pending')),
 reason_code TEXT NOT NULL CHECK(reason_code IN ('','owner_cancelled','lease_expired','service_interrupted','executor_finished','cleanup_uncertain')),
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs_v8(id,project_id),
 UNIQUE(job_id,attempt_number), UNIQUE(id,project_id,job_id));
CREATE TABLE verification_requests_v8(
 project_id TEXT NOT NULL REFERENCES projects(id), operation TEXT NOT NULL,
 request_id TEXT NOT NULL, payload_hash TEXT NOT NULL, job_id TEXT NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs_v8(id,project_id),
 PRIMARY KEY(project_id,operation,request_id));
INSERT INTO verification_jobs_v8(id,project_id,snapshot_id,commit_sha,profile_kind,profile_sha256,status,version,attempt_number,current_attempt_id,created_at,updated_at)
 SELECT id,project_id,snapshot_id,commit_sha,profile_kind,profile_sha256,status,version,attempt_number,current_attempt_id,created_at,updated_at FROM verification_jobs;
INSERT INTO verification_attempts_v8(id,project_id,job_id,attempt_number,token_hash,lease_expires_at,status,reason_code,created_at,updated_at)
 SELECT id,project_id,job_id,attempt_number,token_hash,lease_expires_at,status,reason_code,created_at,updated_at FROM verification_attempts;
INSERT INTO verification_requests_v8(project_id,operation,request_id,payload_hash,job_id)
 SELECT project_id,operation,request_id,payload_hash,job_id FROM verification_requests;
DROP TABLE verification_requests;
DROP TABLE verification_attempts;
DROP TABLE verification_jobs;
ALTER TABLE verification_jobs_v8 RENAME TO verification_jobs;
ALTER TABLE verification_attempts_v8 RENAME TO verification_attempts;
ALTER TABLE verification_requests_v8 RENAME TO verification_requests;
CREATE INDEX verification_jobs_project ON verification_jobs(project_id,created_at,id);
CREATE INDEX verification_attempts_expiry ON verification_attempts(status,lease_expires_at);
CREATE TABLE verification_executions(
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL, attempt_id TEXT NOT NULL UNIQUE,
 attempt_number INTEGER NOT NULL, claim_version INTEGER NOT NULL, revision INTEGER NOT NULL,
 cancel_version INTEGER,
 phase TEXT NOT NULL CHECK(phase IN ('preparing','create_intent','created','executing','finished','cleanup_pending')),
 assessment TEXT NOT NULL CHECK(assessment IN ('unverified','passed','failed','unsupported','error','cancelled')),
 owner_nonce TEXT, container_name TEXT, container_id TEXT,
 create_intent INTEGER NOT NULL CHECK(create_intent IN (0,1)),
 create_reply_complete INTEGER NOT NULL CHECK(create_reply_complete IN (0,1)),
 cleanup_confirmed INTEGER NOT NULL CHECK(cleanup_confirmed IN (0,1)),
 execution_started INTEGER NOT NULL CHECK(execution_started IN (0,1)),
 start_intent INTEGER NOT NULL DEFAULT 0 CHECK(start_intent IN (0,1)),
 tree_sha TEXT, source_sha256 TEXT, input_sha256 TEXT,
 profile_sha256 TEXT NOT NULL, image_id TEXT NOT NULL,
 result_json TEXT NOT NULL, result_sha256 TEXT, error_code TEXT NOT NULL,
 created_at REAL NOT NULL, updated_at REAL NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs(id,project_id),
 FOREIGN KEY(attempt_id,project_id,job_id) REFERENCES verification_attempts(id,project_id,job_id),
 UNIQUE(job_id,project_id));
CREATE INDEX verification_executions_project ON verification_executions(project_id,created_at,id);
PRAGMA user_version=8;
"""


MIGRATION_V9 = """
CREATE UNIQUE INDEX verification_execution_reconciliation_binding ON verification_executions(id,project_id,job_id,attempt_id);
CREATE TABLE verification_reconciliations(
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL,
 job_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL,
 execution_id TEXT NOT NULL UNIQUE,
 request_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 claimed_job_version INTEGER NOT NULL,
 claimed_execution_revision INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('intent','recorded')),
 outcome TEXT NOT NULL CHECK(outcome IN ('unresolved','removed_and_absent')),
 error_code TEXT NOT NULL,
 observation_json TEXT NOT NULL,
 observation_sha256 TEXT,
 created_at REAL NOT NULL,
 updated_at REAL NOT NULL,
 FOREIGN KEY(job_id,project_id) REFERENCES verification_jobs(id,project_id),
 FOREIGN KEY(attempt_id,project_id,job_id) REFERENCES verification_attempts(id,project_id,job_id),
 FOREIGN KEY(execution_id,project_id,job_id,attempt_id) REFERENCES verification_executions(id,project_id,job_id,attempt_id),
 UNIQUE(project_id,request_id));
CREATE INDEX verification_reconciliations_project ON verification_reconciliations(project_id,created_at,id);
PRAGMA user_version=9;
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
            version = 5
        if version == 5:
            for statement in MIGRATION_V6.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 6
        if version == 6:
            for statement in MIGRATION_V7.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 7
        if version == 7:
            for statement in MIGRATION_V8.split(";"):
                if statement.strip():
                    db.execute(statement)
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Database migration violated foreign-key constraints.")
            version = 8
        if version == 8:
            for statement in MIGRATION_V9.split(";"):
                if statement.strip():
                    db.execute(statement)
            version = 9
        if version != 9:
            raise RuntimeError("Unsupported AgentSync database schema version.")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Database migration violated foreign-key constraints.")
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

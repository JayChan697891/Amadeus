import json
import sqlite3

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def setup(tmp_path):
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "test", "root_path": str(tmp_path)})
    actors = []
    for name in ("implementer", "reviewer"):
        actor = core.execute("register_agent", {**project, "name": name})
        owner_grant(core, project, actor)
        actors.append(
            {
                "project_id": project["project_id"],
                "session_id": actor["session_id"],
                "session_token": actor["session_token"],
            }
        )
    return core, project, actors


def task(core, actor, **extra):
    return core.execute(
        "create_task", {**actor, "title": "Implement", "request_id": "create", **extra}
    )


def claim(core, actor, created, **extra):
    return core.execute(
        "claim_task",
        {
            **actor,
            "task_id": created["id"],
            "expected_version": created["version"],
            "request_id": "claim",
            **extra,
        },
    )


def submit(core, actor, leased):
    return core.execute(
        "update_task",
        {
            **actor,
            "task_id": leased["id"],
            "expected_version": leased["version"],
            "lease_token": leased["lease_token"],
            "status": "review",
            "result": "tests passed",
            "request_id": "submit",
        },
    )


def test_persistence_review_and_dependencies(setup):
    core, project, (a, b) = setup
    first = task(core, a)
    second = task(core, a, title="Dependent", request_id="dependent", dependencies=[first["id"]])
    with pytest.raises(AgentSyncError, match="dependencies"):
        claim(core, b, second)
    leased = claim(core, a, first)
    submitted = submit(core, a, leased)
    review = {
        "task_id": first["id"],
        "expected_version": submitted["version"],
        "accept": True,
        "evidence": "Inspected implementation and tests.",
        "request_id": "review",
    }
    with pytest.raises(AgentSyncError, match="different agent"):
        core.execute("review_task", {**a, **review})
    accepted = core.execute("review_task", {**b, **review})
    assert accepted["status"] == "completed"
    assert accepted["latest_review"]["evidence"] == review["evidence"]
    assert accepted["latest_review"]["reviewer_session_id"] == b["session_id"]
    assert accepted["latest_review"]["accept"] is True
    assert accepted["latest_review"]["version"] == accepted["version"]
    assert claim(core, b, second)["status"] == "claimed"
    reopened = Core(core.data_dir)
    state = reopened.execute("get_project_state", a)
    assert len(state["tasks"]) == 2
    persisted_review = next(t for t in state["tasks"] if t["id"] == first["id"])["latest_review"]
    assert persisted_review == accepted["latest_review"]
    assert persisted_review["reviewer_agent_id"] == next(
        s["agent_id"] for s in state["sessions"] if s["id"] == b["session_id"]
    )
    assert state["sessions"][0]["online"] is True
    assert "hash" not in json.dumps(state)
    assert project["admin_token"] not in json.dumps(state)


def test_idempotency_and_no_plaintext_credentials(setup):
    core, project, (a, _) = setup
    first = task(core, a)
    assert task(core, a) == first
    with pytest.raises(AgentSyncError) as exc:
        task(core, a, title="Different")
    assert exc.value.code == "idempotency_conflict"
    leased = claim(core, a, first)
    assert claim(core, a, first) == leased
    with sqlite3.connect(core.db_path) as db:
        dumped = "\n".join(db.iterdump())
    for secret in [project["admin_token"], a["session_token"], leased["lease_token"]]:
        assert secret not in dumped
    assert "lease_token" not in json.dumps(core.execute("list_tasks", a))


def test_expired_lease_replay_reclaim_and_new_owner(setup, monkeypatch):
    core, _, (a, b) = setup
    first = task(core, a)
    leased = claim(core, a, first, lease_seconds=1)
    monkeypatch.setattr(
        "agentsync.core.service.time.time", lambda: leased["lease_expires_at"] + 0.1
    )
    with pytest.raises(AgentSyncError) as exc:
        claim(core, a, first, lease_seconds=1)
    assert exc.value.code == "lease_expired"
    assert core.execute("reclaim_expired", b)["reclaimed_task_ids"] == [first["id"]]
    current = core.execute("list_tasks", b)["tasks"][0]
    new = claim(core, b, current)
    assert new["version"] == leased["version"] + 2
    with pytest.raises(AgentSyncError):
        core.execute(
            "update_task",
            {
                **a,
                "task_id": first["id"],
                "expected_version": new["version"],
                "lease_token": leased["lease_token"],
                "status": "running",
                "request_id": "old-owner",
            },
        )


def test_renew_and_session_expiry(setup, monkeypatch):
    core, _, (a, _) = setup
    leased = claim(core, a, task(core, a), lease_seconds=1)
    request = {
        **a,
        "task_id": leased["id"],
        "lease_token": leased["lease_token"],
        "expected_version": leased["version"],
        "request_id": "renew",
        "lease_seconds": 600,
    }
    renewed = core.execute("renew_lease", request)
    assert renewed["version"] == leased["version"] + 1
    assert core.execute("renew_lease", request) == renewed
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: leased["created_at"] + 4000)
    with pytest.raises(AgentSyncError) as exc:
        core.execute("heartbeat", a)
    assert exc.value.code == "session_expired"


def test_strict_schema_and_no_secret_validation_echo(setup):
    core, _, (a, _) = setup
    with pytest.raises(AgentSyncError) as exc:
        task(core, a, priority="1", extra="no")
    assert exc.value.code == "validation_error"
    assert a["session_token"] not in str(exc.value)
    with pytest.raises(AgentSyncError):
        core.execute("__dict__", {})
    with pytest.raises(AgentSyncError):
        task(core, a, dependencies=["missing"])


def test_wrong_project_and_token_denied(setup, tmp_path):
    core, _, (a, _) = setup
    other = core.execute("create_project", {"name": "other", "root_path": str(tmp_path)})
    with pytest.raises(AgentSyncError):
        core.execute("list_tasks", {**a, "project_id": other["project_id"]})
    with pytest.raises(AgentSyncError):
        core.execute("list_tasks", {**a, "session_token": "invalid"})


def test_review_rejection_releases_task(setup):
    core, _, (a, b) = setup
    leased = claim(core, a, task(core, a))
    submitted = submit(core, a, leased)
    rejected = core.execute(
        "review_task",
        {
            **b,
            "task_id": leased["id"],
            "expected_version": submitted["version"],
            "accept": False,
            "evidence": "Missing verification",
            "request_id": "reject",
        },
    )
    assert rejected["status"] == "pending"
    assert rejected["owner_session_id"] is None
    assert claim(core, b, rejected)["owner_session_id"] == b["session_id"]


def test_relative_data_dir_rejected():
    with pytest.raises(AgentSyncError):
        Core("relative")


def test_heartbeat_extends_session_and_online_window(setup, monkeypatch):
    core, _, (a, _) = setup
    state = core.execute("get_project_state", a)
    heartbeat_at = next(s["heartbeat_at"] for s in state["sessions"] if s["id"] == a["session_id"])
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: heartbeat_at + 121)
    state = core.execute("get_project_state", a)
    assert not next(s["online"] for s in state["sessions"] if s["id"] == a["session_id"])
    heartbeat = core.execute("heartbeat", a)
    assert heartbeat["expires_at"] == heartbeat_at + 121 + 3600
    state = core.execute("get_project_state", a)
    assert next(s["online"] for s in state["sessions"] if s["id"] == a["session_id"])


def test_default_windows_data_dir_independent_of_cwd(tmp_path, monkeypatch):
    from agentsync.config import resolve_data_dir

    monkeypatch.delenv("AGENTSYNC_DATA_DIR", raising=False)
    monkeypatch.setattr("agentsync.config.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    first = resolve_data_dir()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert resolve_data_dir() == first == tmp_path / "local" / "AgentSync"
    monkeypatch.setenv("AGENTSYNC_DATA_DIR", "relative")
    with pytest.raises(AgentSyncError):
        resolve_data_dir()


def test_v1_migration_preserves_data_and_records_future_reviews(tmp_path):
    from agentsync.core.service import digest
    from agentsync.storage.database import SCHEMA

    data_dir = tmp_path / "v1"
    data_dir.mkdir()
    with sqlite3.connect(data_dir / "agentsync.db") as db:
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?)",
            ("project", "Legacy", str(tmp_path), digest("admin"), 1.0),
        )
        db.execute(
            "INSERT INTO agents VALUES(?,?,?,?,?)", ("agent", "project", "Legacy owner", "[]", 1.0)
        )
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
            ("session", "project", "agent", digest("token"), 1.0, 1.0, 99999999999.0),
        )
        db.execute(
            "INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "task",
                "project",
                "Legacy task",
                "Keep description",
                7,
                "completed",
                5,
                "session",
                "Legacy result",
                "[]",
                1.0,
                2.0,
                None,
                None,
                "Legacy unattributed evidence",
            ),
        )
    core = Core(data_dir)
    auth = {"project_id": "project", "session_id": "session", "session_token": "token"}
    owner_grant(
        core, {"project_id": "project", "admin_token": "admin"}, {"agent_id": "agent"}, ("worker",)
    )
    legacy = core.execute("list_tasks", auth)["tasks"][0]
    assert legacy["id"] == "task"
    assert legacy["description"] == "Keep description"
    assert legacy["result"] == "Legacy result"
    assert legacy["latest_review"] is None
    with sqlite3.connect(core.db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 13
        assert (
            db.execute("SELECT review_evidence FROM tasks WHERE id='task'").fetchone()[0]
            == "Legacy unattributed evidence"
        )
    reviewer = core.execute(
        "register_agent", {"project_id": "project", "admin_token": "admin", "name": "New reviewer"}
    )
    owner_grant(core, {"project_id": "project", "admin_token": "admin"}, reviewer, ("reviewer",))
    b = {
        "project_id": "project",
        "session_id": reviewer["session_id"],
        "session_token": reviewer["session_token"],
    }
    created = task(core, auth)
    submitted = submit(core, auth, claim(core, auth, created))
    accepted = core.execute(
        "review_task",
        {
            **b,
            "task_id": created["id"],
            "expected_version": submitted["version"],
            "accept": True,
            "evidence": "Verified after migration",
            "request_id": "new-review",
        },
    )
    reopened = Core(data_dir)
    assert (
        next(t for t in reopened.execute("list_tasks", auth)["tasks"] if t["id"] == created["id"])[
            "latest_review"
        ]
        == accepted["latest_review"]
    )


def test_review_history_survives_rejection_and_second_review(setup):
    core, _, (a, b) = setup
    created = task(core, a)
    submitted = submit(core, a, claim(core, a, created))
    review = {
        **b,
        "task_id": created["id"],
        "expected_version": submitted["version"],
        "accept": False,
        "evidence": "Missing test",
        "request_id": "first-review",
    }
    rejected = core.execute("review_task", review)
    assert core.execute("review_task", review) == rejected
    assert rejected["latest_review"]["accept"] is False
    second_lease = claim(core, a, rejected, request_id="second-claim")
    second_submit = core.execute(
        "update_task",
        {
            **a,
            "task_id": created["id"],
            "lease_token": second_lease["lease_token"],
            "expected_version": second_lease["version"],
            "status": "review",
            "request_id": "second-submit",
        },
    )
    accepted = core.execute(
        "review_task",
        {
            **review,
            "expected_version": second_submit["version"],
            "accept": True,
            "evidence": "Test verified",
            "request_id": "second-review",
        },
    )
    assert accepted["latest_review"]["evidence"] == "Test verified"
    with sqlite3.connect(core.db_path) as db:
        rows = db.execute(
            "SELECT evidence,accept FROM reviews WHERE task_id=? ORDER BY version", (created["id"],)
        ).fetchall()
        assert rows == [("Missing test", 0), ("Test verified", 1)]


@pytest.mark.parametrize("priority", [2**63, -(2**63) - 1, 2**100])
def test_priority_outside_sqlite_range_is_validation_error(setup, priority):
    core, _, (a, _) = setup
    with pytest.raises(AgentSyncError) as exc:
        task(core, a, priority=priority)
    assert exc.value.code == "validation_error"
    assert core.execute("list_tasks", a)["tasks"] == []


def test_huge_version_and_nul_root_are_coded_errors(setup, tmp_path):
    core, _, (a, _) = setup
    created = task(core, a)
    with pytest.raises(AgentSyncError) as exc:
        claim(core, a, created, expected_version=2**100)
    assert exc.value.code == "validation_error"
    with pytest.raises(AgentSyncError) as exc:
        core.execute(
            "create_project", {"name": "Invalid root", "root_path": str(tmp_path) + "\x00"}
        )
    assert exc.value.code == "invalid_root"


def test_wal_initialization_retries_only_transient_locks(monkeypatch):
    from unittest.mock import Mock

    from agentsync.storage.database import _enable_wal

    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
    locked = sqlite3.OperationalError("database is locked")
    locked.sqlite_errorcode = sqlite3.SQLITE_LOCKED
    db = Mock(spec=sqlite3.Connection)
    db.execute.side_effect = [busy, locked, None]
    sleep = Mock()
    monkeypatch.setattr("agentsync.storage.database.time.sleep", sleep)
    _enable_wal(db)
    assert db.execute.call_count == 3
    assert sleep.call_count == 2
    failure = sqlite3.OperationalError("disk I/O error")
    failure.sqlite_errorcode = sqlite3.SQLITE_IOERR
    db.execute.reset_mock()
    db.execute.side_effect = failure
    with pytest.raises(sqlite3.OperationalError) as exc:
        _enable_wal(db)
    assert exc.value is failure
    assert db.execute.call_count == 1


def test_wal_initialization_retry_has_deadline(monkeypatch):
    from unittest.mock import Mock

    from agentsync.storage.database import _enable_wal

    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
    db = Mock(spec=sqlite3.Connection)
    db.execute.side_effect = busy
    monkeypatch.setattr("agentsync.storage.database.time.monotonic", Mock(side_effect=[0.0, 31.0]))
    with pytest.raises(sqlite3.OperationalError) as exc:
        _enable_wal(db)
    assert exc.value is busy
    assert db.execute.call_count == 1

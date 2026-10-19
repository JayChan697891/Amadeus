"""Independent security acceptance checks against the public Core contract."""

import json
import sqlite3
import subprocess
import sys
import time

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient


@pytest.fixture
def world(tmp_path):
    data = tmp_path / "data"
    core = Core(data)
    project = core.execute("create_project", {"name": "Security", "root_path": str(tmp_path)})

    def register(name):
        agent = core.execute(
            "register_agent",
            {
                "project_id": project["project_id"],
                "admin_token": project["admin_token"],
                "name": name,
            },
        )
        return {
            "project_id": project["project_id"],
            "session_id": agent["session_id"],
            "session_token": agent["session_token"],
        }

    return core, project, register("A"), register("B"), data


def create(core, auth, request="create", **fields):
    return core.execute("create_task", {**auth, "title": "Work", "request_id": request, **fields})


def claim(core, auth, task, request="claim", **fields):
    return core.execute(
        "claim_task",
        {
            **auth,
            "task_id": task["id"],
            "expected_version": task["version"],
            "request_id": request,
            **fields,
        },
    )


def reject(core, operation, payload):
    with pytest.raises(AgentSyncError):
        core.execute(operation, payload)


def expire_column(data, table, column, where_column, value):
    """Change only time in test-owned state; no production clock delays."""
    with sqlite3.connect(data / "agentsync.db") as db:
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        assert column in columns, f"Expiry fixture needs {table}.{column}: {columns}"
        db.execute(
            f"UPDATE {table} SET {column}=? WHERE {where_column}=?", (time.time() - 10, value)
        )


def test_session_and_project_credentials_are_bound(world, tmp_path):
    core, project, a, b, data = world
    task = create(core, a)
    reject(core, "list_tasks", {**a, "session_token": b["session_token"]})
    other = core.execute("create_project", {"name": "Other", "root_path": str(tmp_path)})
    reject(core, "list_tasks", {**a, "project_id": other["project_id"]})
    reject(
        core,
        "register_agent",
        {
            "project_id": other["project_id"],
            "admin_token": project["admin_token"],
            "name": "intruder",
        },
    )
    foreign = core.execute(
        "register_agent",
        {"project_id": other["project_id"], "admin_token": other["admin_token"], "name": "foreign"},
    )
    foreign_auth = {
        "project_id": other["project_id"],
        "session_id": foreign["session_id"],
        "session_token": foreign["session_token"],
    }
    reject(
        core,
        "claim_task",
        {
            **foreign_auth,
            "task_id": task["id"],
            "expected_version": task["version"],
            "request_id": "foreign",
        },
    )
    reject(
        core,
        "create_task",
        {
            **foreign_auth,
            "title": "foreign dependency",
            "dependencies": [task["id"]],
            "request_id": "cross-dependency",
        },
    )


def test_owner_version_and_review_identity_are_enforced(world):
    core, _, a, b, _ = world
    task = create(core, a)
    lease = claim(core, a, task)
    payload = {
        **a,
        "task_id": task["id"],
        "expected_version": lease["version"],
        "lease_token": lease["lease_token"],
        "status": "review",
        "request_id": "submit",
    }
    reject(core, "update_task", {**payload, **b})
    reject(core, "update_task", {**payload, "expected_version": task["version"]})
    review = core.execute("update_task", payload)
    reject(
        core,
        "review_task",
        {
            **a,
            "task_id": task["id"],
            "expected_version": review["version"],
            "accept": True,
            "evidence": "self",
            "request_id": "self",
        },
    )
    accepted = core.execute(
        "review_task",
        {
            **b,
            "task_id": task["id"],
            "expected_version": review["version"],
            "accept": True,
            "evidence": "Independent check",
            "request_id": "accept",
        },
    )
    assert accepted["status"] == "completed"
    assert accepted["version"] > review["version"] > lease["version"] > task["version"]


def test_idempotency_replay_collision_and_authentication(world):
    core, _, a, b, _ = world
    task = create(core, a)
    assert create(core, a) == task
    reject(core, "create_task", {**a, "title": "Changed", "request_id": "create"})
    reject(
        core,
        "create_task",
        {**a, "session_token": "wrong", "title": "Work", "request_id": "create"},
    )
    assert create(core, b)["id"] != task["id"]
    lease = claim(core, a, task)
    assert claim(core, a, task) == lease
    assert len(core.execute("list_tasks", a)["tasks"]) == 2


def test_expired_lease_reclaimed_and_stale_owner_cannot_write(world):
    core, _, a, b, data = world
    task = create(core, a)
    lease = claim(core, a, task)
    expire_column(data, "tasks", "lease_expires_at", "id", task["id"])
    reject(
        core,
        "claim_task",
        {**a, "task_id": task["id"], "expected_version": task["version"], "request_id": "claim"},
    )
    reject(
        core,
        "renew_lease",
        {
            **a,
            "task_id": task["id"],
            "lease_token": lease["lease_token"],
            "expected_version": lease["version"],
            "request_id": "renew",
        },
    )
    core.execute("reclaim_expired", b)
    pending = core.execute("list_tasks", b)["tasks"][0]
    assert pending["status"] == "pending" and pending["owner_session_id"] is None
    assert pending["version"] > lease["version"]
    claimed_by_b = claim(core, b, pending, "second")
    reject(
        core,
        "update_task",
        {
            **a,
            "task_id": task["id"],
            "lease_token": lease["lease_token"],
            "expected_version": claimed_by_b["version"],
            "status": "running",
            "request_id": "stale",
        },
    )


def test_expired_session_cannot_heartbeat_or_replay_write(world):
    core, _, a, _, data = world
    create(core, a)
    expire_column(data, "sessions", "expires_at", "id", a["session_id"])
    reject(core, "heartbeat", a)
    reject(core, "list_tasks", a)
    reject(core, "create_task", {**a, "title": "Work", "request_id": "create"})


def test_renewal_replay_does_not_extend_lease_and_expiry_still_wins(world):
    core, _, a, _, data = world
    task = create(core, a)
    lease = claim(core, a, task, lease_seconds=5)
    payload = {
        **a,
        "task_id": task["id"],
        "expected_version": lease["version"],
        "lease_token": lease["lease_token"],
        "lease_seconds": 300,
        "request_id": "renew",
    }
    renewed = core.execute("renew_lease", payload)
    assert renewed["lease_expires_at"] > lease["lease_expires_at"]
    assert renewed["version"] > lease["version"]
    assert core.execute("renew_lease", payload) == renewed
    expire_column(data, "tasks", "lease_expires_at", "id", task["id"])
    reject(core, "renew_lease", payload)
    reject(
        core,
        "update_task",
        {
            **a,
            "task_id": task["id"],
            "expected_version": renewed["version"],
            "lease_token": lease["lease_token"],
            "status": "running",
            "request_id": "expired-write",
        },
    )


def test_online_status_comes_from_heartbeat_not_registration(world):
    core, _, a, b, data = world
    with sqlite3.connect(data / "agentsync.db") as db:
        db.execute(
            "UPDATE sessions SET heartbeat_at=? WHERE id=?", (time.time() - 121, a["session_id"])
        )
    sessions = core.execute("get_project_state", b)["sessions"]
    assert (
        next(session for session in sessions if session["id"] == a["session_id"])["online"] is False
    )
    core.execute("heartbeat", a)
    sessions = core.execute("get_project_state", b)["sessions"]
    assert (
        next(session for session in sessions if session["id"] == a["session_id"])["online"] is True
    )


def test_secrets_absent_from_state_list_and_database(world):
    core, project, a, b, data = world
    task = create(core, a)
    lease = claim(core, a, task)
    secrets = [project["admin_token"], a["session_token"], b["session_token"], lease["lease_token"]]
    state = json.dumps(core.execute("get_project_state", a))
    tasks = json.dumps(core.execute("list_tasks", b))
    for secret in secrets:
        assert secret not in state and secret not in tasks
        for file in data.iterdir():
            if file.is_file():
                assert secret.encode() not in file.read_bytes(), (
                    f"plaintext credential in {file.name}"
                )


@pytest.mark.parametrize("priority", [2**63, -(2**63) - 1])
def test_priority_outside_storage_integer_range_returns_error_envelope(world, priority):
    _, _, a, _, data = world
    response = AgentSyncClient(data).call(
        "create_task", **a, title="Oversized priority", priority=priority, request_id="out-of-range"
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "operation,extra",
    [
        ("claim_task", {}),
        ("renew_lease", {"lease_token": "not-a-lease"}),
        ("update_task", {"lease_token": "not-a-lease", "status": "running"}),
        ("review_task", {"accept": True, "evidence": "Check"}),
    ],
)
def test_oversized_expected_versions_are_structured_validation_errors(world, operation, extra):
    core, _, a, _, data = world
    task = create(core, a)
    response = AgentSyncClient(data).call(
        operation,
        **a,
        task_id=task["id"],
        expected_version=2**63,
        request_id="huge-version",
        **extra,
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "operation,extra",
    [
        ("create_project", {"name": "\ud800"}),
        ("register_agent", {"name": "Bad capability", "capabilities": ["\udfff"]}),
        ("create_task", {"title": "\ud800", "request_id": "bad-title"}),
        (
            "create_task",
            {"title": "Bad description", "description": "\udfff", "request_id": "bad-desc"},
        ),
        ("create_task", {"title": "Bad request ID", "request_id": "\ud800"}),
    ],
)
def test_lone_surrogates_return_redacted_validation_envelopes(world, operation, extra):
    _, project, a, _, data = world
    if operation == "create_project":
        payload = {"root_path": str(data.parent), **extra}
    elif operation == "register_agent":
        payload = {**project, **extra}
    else:
        payload = {**a, **extra}
    response = AgentSyncClient(data).call(operation, **payload)
    assert response["ok"] is False
    assert response["error"]["code"] == "validation_error"
    assert a["session_token"] not in json.dumps(response)
    assert project["admin_token"] not in json.dumps(response)


@pytest.mark.parametrize(
    "operation,extra",
    [
        ("create_task", {"title": "Work", "request_id": "strict", "surprise": True}),
        ("create_task", {"title": "Work", "request_id": "strict", "priority": "1"}),
        ("create_task", {"title": "Work", "request_id": "strict", "priority": True}),
        (
            "claim_task",
            {
                "task_id": "missing",
                "expected_version": 0,
                "request_id": "lease",
                "lease_seconds": 0,
            },
        ),
        (
            "claim_task",
            {
                "task_id": "missing",
                "expected_version": 0,
                "request_id": "lease",
                "lease_seconds": 3601,
            },
        ),
        (
            "claim_task",
            {
                "task_id": "missing",
                "expected_version": 0,
                "request_id": "lease",
                "lease_seconds": "300",
            },
        ),
    ],
)
def test_strict_schemas_reject_unknown_and_coerced_fields(world, operation, extra):
    core, _, a, _, _ = world
    if operation == "claim_task":
        task = create(core, a)
        extra = {**extra, "task_id": task["id"], "expected_version": task["version"]}
    reject(core, operation, {**a, **extra})
    reject(core, "__getattribute__", {})


def test_cross_process_claim_has_exactly_one_winner(world):
    core, _, a, b, data = world
    task = create(core, a)
    script = """
import json,sys
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
data,payload=json.loads(sys.stdin.readline())
print('READY',flush=True)
sys.stdin.readline()
try:
    result=Core(data).execute('claim_task',payload)
    print(json.dumps({'won':True,'owner':result['owner_session_id']}),flush=True)
except AgentSyncError as exc:
    print(json.dumps({'won':False,'code':exc.code}),flush=True)
"""
    children = []
    try:
        for i, auth in enumerate((a, b)):
            child = subprocess.Popen(
                [sys.executable, "-u", "-c", script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            children.append(child)
            child.stdin.write(
                json.dumps(
                    [
                        str(data),
                        {
                            **auth,
                            "task_id": task["id"],
                            "expected_version": task["version"],
                            "request_id": f"race-{i}",
                        },
                    ]
                )
                + "\n"
            )
            child.stdin.flush()
        for child in children:
            assert child.stdout.readline().strip() == "READY"
        for child in children:
            child.stdin.write("GO\n")
            child.stdin.flush()
        results = []
        for child in children:
            output, errors = child.communicate(timeout=20)
            assert child.returncode == 0, errors
            results.append(json.loads(output))
        assert sum(result["won"] for result in results) == 1, results
        current = core.execute("list_tasks", a)["tasks"][0]
        assert current["owner_session_id"] == next(r["owner"] for r in results if r["won"])
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()

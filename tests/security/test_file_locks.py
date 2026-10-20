"""Cooperative lock isolation, authentication, expiry and idempotency."""

import json
import os
import sqlite3
from uuid import uuid4

import pytest
from conftest import owner_grant

from agentsync.core.service import Core, digest
from agentsync.errors import AgentSyncError


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "resources"
    root.mkdir()
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "locks", "root_path": str(root)})
    actors = []
    for name in ("owner", "other"):
        registered = core.execute("register_agent", {**project, "name": name})
        owner_grant(core, project, registered)
        actors.append({"project_id": project["project_id"], **registered})
    return core, project, actors, root


def call(core, operation, actor, **extra):
    return core.execute(
        operation,
        {**{key: actor[key] for key in ("project_id", "session_id", "session_token")}, **extra},
    )


def acquire(core, actor, path="a.txt", **extra):
    return call(core, "acquire_file_lock", actor, path=path, request_id=uuid4().hex, **extra)


def mutate(core, operation, actor, lock, **extra):
    return call(
        core,
        operation,
        actor,
        lock_id=lock["id"],
        lease_token=lock["lease_token"],
        expected_version=lock["version"],
        request_id=uuid4().hex,
        **extra,
    )


def test_tokens_are_hashed_never_listed_and_reopen_preserves_lock(setup):
    core, project, (a, b), root = setup
    request = {"path": "folder\\file.txt", "request_id": "acquire"}
    lock = call(core, "acquire_file_lock", a, **request)
    assert lock["path"] == "folder/file.txt"
    assert call(core, "acquire_file_lock", a, **request) == lock
    public = call(Core(core.data_dir), "list_file_locks", b)["locks"]
    assert public == [{key: value for key, value in lock.items() if key != "lease_token"}]
    assert not (root / "folder").exists()
    with sqlite3.connect(core.db_path) as db:
        dumped = "\n".join(db.iterdump())
        stored_hash = db.execute(
            "SELECT lease_hash FROM file_locks WHERE id=?", (lock["id"],)
        ).fetchone()[0]
        assert stored_hash == digest(lock["lease_token"])
        assert db.execute(
            "SELECT typeof(device),typeof(inode) FROM project_resource_roots"
        ).fetchone() == ("text", "text")
    for secret in (lock["lease_token"], a["session_token"], project["admin_token"]):
        assert secret not in dumped
        assert secret not in json.dumps(public)
    assert "hash" not in json.dumps(public)
    assert "resource_key" not in json.dumps(public)


@pytest.mark.parametrize("operation", ["renew_file_lock", "release_file_lock"])
def test_only_owning_session_can_mutate_even_for_same_agent(setup, operation):
    core, _, (a, b), _ = setup
    lock = acquire(core, a)
    sibling = {**a, "session_id": uuid4().hex, "session_token": uuid4().hex}
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO sessions SELECT ?,project_id,agent_id,?,created_at,heartbeat_at,expires_at FROM sessions WHERE id=?",
            (sibling["session_id"], digest(sibling["session_token"]), a["session_id"]),
        )
    for attacker in (b, sibling, {**a, "session_token": "wrong"}):
        with pytest.raises(AgentSyncError):
            mutate(core, operation, attacker, lock)
    with pytest.raises(AgentSyncError):
        mutate(core, operation, a, {**lock, "lease_token": "wrong"})
    assert call(core, "list_file_locks", a)["locks"][0]["version"] == lock["version"]


def test_superseded_replays_release_history_and_reacquire(setup):
    core, _, (a, b), _ = setup
    request = {"path": "a", "request_id": "acquire"}
    lock = call(core, "acquire_file_lock", a, **request)
    renewal = {
        "lock_id": lock["id"],
        "lease_token": lock["lease_token"],
        "expected_version": lock["version"],
        "lease_seconds": 600,
        "request_id": "renew",
    }
    renewed = call(core, "renew_file_lock", a, **renewal)
    assert renewed["version"] == lock["version"] + 1
    assert call(core, "renew_file_lock", a, **renewal) == renewed
    with pytest.raises(AgentSyncError):
        call(core, "acquire_file_lock", a, **request)
    released = mutate(core, "release_file_lock", a, renewed)
    assert released["status"] == "released" and "lease_token" not in released
    for operation, old_request in (("acquire_file_lock", request), ("renew_file_lock", renewal)):
        with pytest.raises(AgentSyncError):
            call(core, operation, a, **old_request)
    replacement = acquire(core, b, "a")
    assert replacement["id"] != lock["id"]
    with pytest.raises(AgentSyncError):
        mutate(core, "release_file_lock", a, renewed)
    history = call(core, "list_file_locks", a, include_expired=True)["locks"]
    assert {entry["status"] for entry in history} == {"released", "active"}
    assert call(core, "list_file_locks", b)["locks"][0]["id"] == replacement["id"]


def test_expiry_replays_cannot_block_or_mutate_replacement(setup, monkeypatch):
    core, _, (a, b), _ = setup
    request = {"path": "a", "lease_seconds": 1, "request_id": "acquire"}
    lock = call(core, "acquire_file_lock", a, **request)
    renewal = {
        "lock_id": lock["id"],
        "lease_token": lock["lease_token"],
        "expected_version": lock["version"],
        "lease_seconds": 1,
        "request_id": "renew",
    }
    renewed = call(core, "renew_file_lock", a, **renewal)
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: renewed["expires_at"] + 0.1)
    assert call(core, "list_file_locks", a)["locks"] == []
    assert call(core, "list_file_locks", a, include_expired=True)["locks"][0]["status"] == "expired"
    for operation, old_request in (("acquire_file_lock", request), ("renew_file_lock", renewal)):
        with pytest.raises(AgentSyncError):
            call(core, operation, a, **old_request)
    replacement = acquire(Core(core.data_dir), b, "a")
    with pytest.raises(AgentSyncError):
        mutate(core, "release_file_lock", a, renewed)
    assert call(core, "list_file_locks", a)["locks"][0]["id"] == replacement["id"]


@pytest.mark.parametrize(
    "held,held_kind,contender,contender_kind",
    [
        ("a", "directory", "a/x", "file"),
        ("a/x", "file", "a", "directory"),
        ("a", "directory", "a", "directory"),
        ("a", "file", "a", "file"),
        (".", "directory", "child", "file"),
    ],
)
def test_directory_hierarchy_conflicts(setup, held, held_kind, contender, contender_kind):
    core, _, (a, b), _ = setup
    acquire(core, a, held, kind=held_kind)
    with pytest.raises(AgentSyncError):
        acquire(core, b, contender, kind=contender_kind)


@pytest.mark.parametrize(
    "held,held_kind,other,other_kind",
    [
        ("a", "directory", "ab/x", "file"),
        ("a/x", "file", "a/y", "file"),
        ("a", "directory", "ab", "directory"),
    ],
)
def test_sibling_component_boundaries_coexist(setup, held, held_kind, other, other_kind):
    core, _, (a, b), _ = setup
    first = acquire(core, a, held, kind=held_kind)
    second = acquire(core, b, other, kind=other_kind)
    assert first["id"] != second["id"]


@pytest.mark.parametrize("overlapping", [False, True])
def test_conflicts_are_global_across_duplicate_and_overlapping_roots(setup, overlapping):
    core, _, (a, _), root = setup
    (root / "nested").mkdir()
    other_root = root / "nested" if overlapping else root
    other_project = core.execute(
        "create_project", {"name": "foreign", "root_path": str(other_root)}
    )
    outsider = {
        "project_id": other_project["project_id"],
        **core.execute("register_agent", {**other_project, "name": "outsider"}),
    }
    owner_grant(core, other_project, outsider, ("worker",))
    held = acquire(core, a, "nested/file")
    with pytest.raises(AgentSyncError) as exc:
        acquire(core, outsider, "file" if overlapping else "nested/file")
    for private in (held["id"], a["agent_id"], a["session_id"], a["project_id"]):
        assert private not in str(exc.value)
    assert call(core, "list_file_locks", outsider, include_expired=True)["locks"] == []
    with pytest.raises(AgentSyncError):
        mutate(core, "release_file_lock", outsider, held)


def test_list_pagination_and_strict_bounds(setup):
    core, _, (a, _), _ = setup
    for index in range(3):
        acquire(core, a, f"file-{index}")
    first = call(core, "list_file_locks", a, limit=2)
    last = call(core, "list_file_locks", a, limit=2, offset=2)
    assert len(first["locks"]) == 2 and first["has_more"] is True
    assert len(last["locks"]) == 1 and last["has_more"] is False
    assert len({item["id"] for item in first["locks"] + last["locks"]}) == 3
    for extra in ({"limit": 0}, {"offset": -1}, {"include_expired": "true"}):
        with pytest.raises(AgentSyncError):
            call(core, "list_file_locks", a, **extra)


@pytest.mark.skipif(os.name != "nt", reason="Windows conflict keys case-fold")
def test_windows_case_and_separator_aliases_conflict(setup):
    core, _, (a, b), _ = setup
    acquire(core, a, "Folder\\Resource.txt")
    with pytest.raises(AgentSyncError):
        acquire(core, b, "folder/resource.TXT")


def test_renewal_versions_request_fingerprints_and_expired_session(setup, monkeypatch):
    core, _, (a, _), _ = setup
    request = {"path": "file", "request_id": "initial"}
    initial = call(core, "acquire_file_lock", a, **request)
    with pytest.raises(AgentSyncError):
        call(core, "acquire_file_lock", a, **{**request, "path": "changed"})
    first_request = {
        "lock_id": initial["id"],
        "lease_token": initial["lease_token"],
        "expected_version": initial["version"],
        "request_id": "first-renew",
    }
    first = call(core, "renew_file_lock", a, **first_request)
    second = mutate(core, "renew_file_lock", a, first)
    with pytest.raises(AgentSyncError):
        call(core, "renew_file_lock", a, **first_request)
    assert second["version"] == initial["version"] + 2
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: initial["created_at"] + 4000)
    for operation, fields in (
        ("acquire_file_lock", request),
        ("renew_file_lock", first_request),
        ("list_file_locks", {}),
    ):
        with pytest.raises(AgentSyncError) as exc:
            call(core, operation, a, **fields)
        assert exc.value.code == "session_expired"


def test_file_and_task_leases_have_distinct_token_domains(setup):
    core, _, (a, _), _ = setup
    task = call(core, "create_task", a, title="Token domain", request_id="task")
    lease = call(
        core,
        "claim_task",
        a,
        task_id=task["id"],
        expected_version=task["version"],
        request_id="same-request",
    )
    lock = call(core, "acquire_file_lock", a, path="file", request_id="same-request")
    assert lock["lease_token"] != lease["lease_token"]


@pytest.mark.parametrize(
    "extra",
    [
        {"lease_seconds": 0},
        {"lease_seconds": 3601},
        {"lease_seconds": "1"},
        {"kind": "other"},
        {"request_id": ""},
    ],
)
def test_invalid_acquire_inputs_leave_no_lock(setup, extra):
    core, _, (a, _), _ = setup
    with pytest.raises(AgentSyncError):
        call(core, "acquire_file_lock", a, **{"path": "file", "request_id": "invalid", **extra})
    assert call(core, "list_file_locks", a, include_expired=True)["locks"] == []

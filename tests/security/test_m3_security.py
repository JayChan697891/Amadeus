"""Ownership, project boundaries, and pinned handoff data."""

import sqlite3
from uuid import uuid4

import pytest

from agentsync.core.service import Core, digest
from agentsync.errors import AgentSyncError


@pytest.fixture
def setup(tmp_path):
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "handoff", "root_path": str(tmp_path)})
    actors = []
    for name in ("sender", "recipient", "third"):
        actor = core.execute("register_agent", {**project, "name": name})
        actors.append({"project_id": project["project_id"], **actor})
    return core, project, actors


def call(core, operation, actor, **fields):
    auth = {key: actor[key] for key in ("project_id", "session_id", "session_token")}
    return core.execute(operation, {**auth, **fields})


def leased_task(core, actor, **fields):
    task = call(core, "create_task", actor, title="Transfer", request_id=uuid4().hex)
    return call(
        core,
        "claim_task",
        actor,
        task_id=task["id"],
        expected_version=task["version"],
        request_id=uuid4().hex,
        **fields,
    )


def handoff(core, actor, target, task, **fields):
    return call(
        core,
        "submit_handoff",
        actor,
        task_id=task["id"],
        lease_token=task["lease_token"],
        expected_version=task["version"],
        target_agent_id=target["agent_id"],
        package={"summary": "Continue work"},
        request_id=uuid4().hex,
        **fields,
    )


def task_state(core, actor, task_id):
    return next(task for task in call(core, "list_tasks", actor)["tasks"] if task["id"] == task_id)


def test_context_and_handoff_project_isolation(setup, tmp_path):
    core, _, (a, b, _) = setup
    context = call(
        core,
        "publish_context",
        a,
        kind="decision",
        title="Private",
        content="secret needle",
        request_id="publish",
    )
    transfer = handoff(core, a, b, leased_task(core, a))
    other_project = core.execute("create_project", {"name": "other", "root_path": str(tmp_path)})
    outsider = {
        "project_id": other_project["project_id"],
        **core.execute("register_agent", {**other_project, "name": "outsider"}),
    }
    other_recipient = {
        "project_id": other_project["project_id"],
        **core.execute("register_agent", {**other_project, "name": "other-recipient"}),
    }
    for operation, fields in (
        ("get_context", {"context_id": context["id"]}),
        ("get_handoff", {"handoff_id": transfer["id"]}),
        (
            "publish_context",
            {
                "context_id": context["id"],
                "expected_version": 1,
                "kind": "note",
                "title": "Cross",
                "content": "Overwrite",
                "request_id": "cross",
            },
        ),
    ):
        with pytest.raises(AgentSyncError):
            call(core, operation, outsider, **fields)
    assert call(core, "search_context", outsider, query="needle")["entries"] == []
    other_task = leased_task(core, outsider)
    with pytest.raises(AgentSyncError):
        handoff(core, outsider, b, other_task)
    with pytest.raises(AgentSyncError):
        call(
            core,
            "submit_handoff",
            outsider,
            task_id=other_task["id"],
            lease_token=other_task["lease_token"],
            expected_version=other_task["version"],
            target_agent_id=other_recipient["agent_id"],
            package={
                "summary": "Cross ref",
                "context_refs": [{"context_id": context["id"], "version": 1}],
            },
            request_id="cross-ref",
        )
    current = task_state(core, outsider, other_task["id"])
    assert current["version"] == other_task["version"]
    assert current["owner_session_id"] == outsider["session_id"]
    # The failed cross-project package leaves the original lease usable.
    valid = handoff(core, outsider, other_recipient, other_task)
    assert valid["status"] == "pending"


def test_handoff_pins_context_and_invalid_reference_is_atomic(setup):
    core, _, (a, b, _) = setup
    first = call(
        core,
        "publish_context",
        a,
        kind="note",
        title="Pinned",
        content="Original",
        request_id="context",
    )
    task = leased_task(core, a)
    package = {
        "summary": "Pinned package",
        "changed_files": ["../never-read"],
        "evidence": ["do not execute"],
        "context_refs": [{"context_id": first["id"], "version": 1}],
    }
    for ref in (
        {"context_id": "missing", "version": 1},
        {"context_id": first["id"], "version": 99},
    ):
        with pytest.raises(AgentSyncError):
            call(
                core,
                "submit_handoff",
                a,
                task_id=task["id"],
                lease_token=task["lease_token"],
                expected_version=task["version"],
                target_agent_id=b["agent_id"],
                package={**package, "context_refs": [ref]},
                request_id=uuid4().hex,
            )
        assert task_state(core, a, task["id"])["version"] == task["version"]
    request = dict(
        task_id=task["id"],
        lease_token=task["lease_token"],
        expected_version=task["version"],
        target_agent_id=b["agent_id"],
        package=package,
        request_id="transfer",
    )
    transfer = call(core, "submit_handoff", a, **request)
    call(
        core,
        "publish_context",
        a,
        kind="note",
        title="Changed",
        content="Revised",
        context_id=first["id"],
        expected_version=1,
        request_id="revision",
    )
    persisted = call(core, "get_handoff", b, handoff_id=transfer["id"])
    assert persisted == transfer
    assert persisted["contexts"] == [first]
    assert persisted["package"] == {"completed_work": "", "open_questions": [], **package}
    assert call(core, "submit_handoff", a, **request) == transfer
    assert task_state(core, b, task["id"])["status"] == "handoff"
    with pytest.raises(AgentSyncError):
        call(
            core,
            "update_task",
            a,
            task_id=task["id"],
            lease_token=task["lease_token"],
            expected_version=transfer["task_version"],
            status="running",
            request_id="old-write",
        )
    with pytest.raises(AgentSyncError):
        call(
            core,
            "renew_lease",
            a,
            task_id=task["id"],
            lease_token=task["lease_token"],
            expected_version=transfer["task_version"],
            request_id="old-renew",
        )


def test_handoff_requires_active_owner_and_distinct_agent(setup, monkeypatch):
    core, _, (a, b, _) = setup
    task = leased_task(core, a, lease_seconds=1)
    with pytest.raises(AgentSyncError):
        handoff(core, a, a, task)
    with pytest.raises(AgentSyncError):
        handoff(core, b, a, task)
    sibling = {**a, "session_id": uuid4().hex, "session_token": uuid4().hex}
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO sessions SELECT ?,project_id,agent_id,?,created_at,heartbeat_at,expires_at FROM sessions WHERE id=?",
            (sibling["session_id"], digest(sibling["session_token"]), a["session_id"]),
        )
    # Submission is session-owned even though resolution/reservations use agent identity.
    with pytest.raises(AgentSyncError):
        handoff(core, sibling, b, task)
    with pytest.raises(AgentSyncError):
        handoff(core, a, sibling, task)
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: task["lease_expires_at"] + 0.1)
    with pytest.raises(AgentSyncError):
        handoff(core, a, b, task)
    assert task_state(core, a, task["id"])["version"] == task["version"]


@pytest.mark.parametrize("outcome", ["accept", "reject", "withdraw"])
def test_identity_resolution_reservation_and_reassignment(setup, outcome):
    core, _, (a, b, c) = setup
    task = leased_task(core, a)
    transfer = handoff(core, a, b, task)
    operation = "withdraw_handoff" if outcome == "withdraw" else "resolve_handoff"
    fields = {
        "handoff_id": transfer["id"],
        "expected_version": transfer["task_version"],
        "reason": "Reviewed decision",
        "request_id": "resolution",
    }
    if outcome != "withdraw":
        fields["accept"] = outcome == "accept"
    resolver = a if outcome == "withdraw" else b
    with pytest.raises(AgentSyncError):
        call(core, operation, c, **fields)
    # A second authenticated session for the SAME agent must retain identity rights.
    sibling = {**resolver, "session_id": uuid4().hex, "session_token": uuid4().hex}
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO sessions SELECT ?,project_id,agent_id,?,created_at,heartbeat_at,expires_at FROM sessions WHERE id=?",
            (sibling["session_id"], digest(sibling["session_token"]), resolver["session_id"]),
        )
    result = call(core, operation, sibling, **fields)
    assert call(core, operation, sibling, **fields) == result
    current = task_state(core, a, task["id"])
    assert current["status"] == "pending"
    recipient = b if outcome == "accept" else a
    assert current["assigned_agent_id"] == recipient["agent_id"]
    with pytest.raises(AgentSyncError):
        call(
            core,
            "claim_task",
            c,
            task_id=task["id"],
            expected_version=current["version"],
            request_id="steal",
        )
    claimed = call(
        core,
        "claim_task",
        recipient,
        task_id=task["id"],
        expected_version=current["version"],
        request_id="reclaim",
    )
    assert claimed["lease_token"] != task["lease_token"]
    second = handoff(core, recipient, c, claimed)
    with pytest.raises(AgentSyncError):
        call(
            core,
            operation,
            sibling,
            **{
                **fields,
                "expected_version": second["task_version"],
                "request_id": "stale-resolution",
            },
        )
    assert call(core, "get_handoff", a, handoff_id=transfer["id"]) == result
    assert task_state(core, c, task["id"])["status"] == "handoff"


def test_reservation_expires_after_successful_claim_and_lease_reclaim(setup, monkeypatch):
    core, _, (a, b, c) = setup
    transfer = handoff(core, a, b, leased_task(core, a))
    call(
        core,
        "resolve_handoff",
        b,
        handoff_id=transfer["id"],
        expected_version=transfer["task_version"],
        accept=True,
        request_id="accept",
    )
    current = task_state(core, b, transfer["task_id"])
    fresh = call(
        core,
        "claim_task",
        b,
        task_id=current["id"],
        expected_version=current["version"],
        lease_seconds=1,
        request_id="fresh",
    )
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: fresh["lease_expires_at"] + 0.1)
    assert call(core, "reclaim_expired", c)["reclaimed_task_ids"] == [current["id"]]
    reclaimed = task_state(core, c, current["id"])
    assert reclaimed.get("assigned_agent_id") is None
    claimed = call(
        core,
        "claim_task",
        c,
        task_id=current["id"],
        expected_version=reclaimed["version"],
        request_id="third-claim",
    )
    assert claimed["owner_session_id"] == c["session_id"]


@pytest.mark.parametrize("operation", ["resolve_handoff", "withdraw_handoff"])
@pytest.mark.parametrize("reason", ["", "   "])
def test_negative_decision_requires_reason_without_releasing_task(setup, operation, reason):
    core, _, (a, b, _) = setup
    transfer = handoff(core, a, b, leased_task(core, a))
    fields = {
        "handoff_id": transfer["id"],
        "expected_version": transfer["task_version"],
        "reason": reason,
        "request_id": "empty-reason",
    }
    actor = a
    if operation == "resolve_handoff":
        fields["accept"] = False
        actor = b
    with pytest.raises(AgentSyncError):
        call(core, operation, actor, **fields)
    assert call(core, "get_handoff", a, handoff_id=transfer["id"]) == transfer
    assert task_state(core, a, transfer["task_id"])["status"] == "handoff"


@pytest.mark.parametrize("invalid_auth", ["token", "expired"])
def test_replayed_writes_and_reads_always_authenticate(setup, monkeypatch, invalid_auth):
    core, _, (a, b, _) = setup
    context_request = {
        "kind": "note",
        "title": "Auth",
        "content": "Protected",
        "request_id": "context",
    }
    context = call(core, "publish_context", a, **context_request)
    task = leased_task(core, a)
    submit_request = {
        "task_id": task["id"],
        "lease_token": task["lease_token"],
        "expected_version": task["version"],
        "target_agent_id": b["agent_id"],
        "package": {"summary": "Authenticated replay"},
        "request_id": "submit",
    }
    transfer = call(core, "submit_handoff", a, **submit_request)
    resolve_request = {
        "handoff_id": transfer["id"],
        "expected_version": transfer["task_version"],
        "accept": True,
        "request_id": "resolve",
    }
    resolved = call(core, "resolve_handoff", b, **resolve_request)
    # An authenticated submit replay returns its stored response without reviving ownership.
    assert call(core, "submit_handoff", a, **submit_request) == transfer
    assert call(core, "get_handoff", b, handoff_id=transfer["id"]) == resolved
    assert task_state(core, b, task["id"])["status"] == "pending"
    other = handoff(core, a, b, leased_task(core, a))
    withdraw_request = {
        "handoff_id": other["id"],
        "expected_version": other["task_version"],
        "reason": "Cancel transfer",
        "request_id": "withdraw",
    }
    call(core, "withdraw_handoff", a, **withdraw_request)
    operations = [
        ("publish_context", a, context_request),
        ("submit_handoff", a, submit_request),
        ("resolve_handoff", b, resolve_request),
        ("withdraw_handoff", a, withdraw_request),
        ("get_context", a, {"context_id": context["id"]}),
        ("search_context", a, {"query": "Protected"}),
        ("get_handoff", b, {"handoff_id": transfer["id"]}),
    ]
    if invalid_auth == "expired":
        monkeypatch.setattr("agentsync.core.service.time.time", lambda: task["created_at"] + 4000)
    for operation, actor, fields in operations:
        if invalid_auth == "token":
            actor = {**actor, "session_token": "incorrect"}
        with pytest.raises(AgentSyncError):
            call(core, operation, actor, **fields)


def test_unclaimed_reservation_deadline_releases_task_without_restoring_sender_lease(setup):
    core, _, (a, b, c) = setup
    old_lease = leased_task(core, a)
    transfer = handoff(core, a, b, old_lease)
    request = {
        "handoff_id": transfer["id"],
        "expected_version": transfer["task_version"],
        "accept": True,
        "request_id": "accept",
    }
    resolved = call(core, "resolve_handoff", b, **request)
    assert (
        resolved["resolved_at"]
        < resolved["reservation_expires_at"]
        <= resolved["resolved_at"] + 300
    )
    reserved = task_state(core, c, old_lease["id"])
    assert reserved["assigned_agent_id"] == b["agent_id"]
    assert reserved["assignment_expires_at"] == resolved["reservation_expires_at"]
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "UPDATE handoffs SET reservation_expires_at=? WHERE id=?",
            (old_lease["created_at"] - 1, transfer["id"]),
        )
    current = task_state(core, c, old_lease["id"])
    assert current.get("assigned_agent_id") is None
    assert current.get("assignment_expires_at") is None
    # Even a successful old resolution replay cannot re-create its expired reservation.
    assert call(core, "resolve_handoff", b, **request) == resolved
    assert task_state(core, c, old_lease["id"]).get("assigned_agent_id") is None
    claimed = call(
        core,
        "claim_task",
        c,
        task_id=current["id"],
        expected_version=current["version"],
        request_id="third-claim",
    )
    assert call(core, "resolve_handoff", b, **request) == resolved
    current = task_state(core, c, old_lease["id"])
    assert current["owner_session_id"] == c["session_id"]
    assert current["version"] == claimed["version"]
    assert current.get("assigned_agent_id") is None
    for operation, extra in (("renew_lease", {}), ("update_task", {"status": "running"})):
        with pytest.raises(AgentSyncError):
            call(
                core,
                operation,
                a,
                task_id=current["id"],
                expected_version=current["version"],
                lease_token=old_lease["lease_token"],
                request_id=operation,
                **extra,
            )


def test_accept_reservation_cannot_outlive_recipient_session(setup, monkeypatch):
    core, _, (a, b, c) = setup
    task = leased_task(core, a)
    transfer = handoff(core, a, b, task)
    recipient_expiry = task["created_at"] + 10
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "UPDATE sessions SET expires_at=? WHERE id=?", (recipient_expiry, b["session_id"])
        )
    resolved = call(
        core,
        "resolve_handoff",
        b,
        handoff_id=transfer["id"],
        expected_version=transfer["task_version"],
        accept=True,
        request_id="accept",
    )
    assert resolved["reservation_expires_at"] <= recipient_expiry
    monkeypatch.setattr("agentsync.core.service.time.time", lambda: recipient_expiry + 0.1)
    current = task_state(core, c, task["id"])
    assert current.get("assigned_agent_id") is None
    claimed = call(
        core,
        "claim_task",
        c,
        task_id=current["id"],
        expected_version=current["version"],
        request_id="claim-after-recipient-expiry",
    )
    assert claimed["owner_session_id"] == c["session_id"]


def test_rejected_handoff_does_not_reserve_for_sender_without_valid_sessions(setup):
    core, _, (a, b, c) = setup
    task = leased_task(core, a)
    transfer = handoff(core, a, b, task)
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "UPDATE sessions SET expires_at=? WHERE project_id=? AND agent_id=?",
            (task["created_at"] - 1, a["project_id"], a["agent_id"]),
        )
    rejected = call(
        core,
        "resolve_handoff",
        b,
        handoff_id=transfer["id"],
        expected_version=transfer["task_version"],
        accept=False,
        reason="Sender unavailable",
        request_id="reject",
    )
    assert rejected["reservation_expires_at"] <= rejected["resolved_at"]
    current = task_state(core, c, task["id"])
    assert current.get("assigned_agent_id") is None
    claimed = call(
        core,
        "claim_task",
        c,
        task_id=current["id"],
        expected_version=current["version"],
        request_id="claim-unreserved",
    )
    assert claimed["owner_session_id"] == c["session_id"]

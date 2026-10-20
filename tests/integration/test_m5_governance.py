"""Approval and audit metadata tests, not real-client or apply verification."""

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "governance", "root_path": str(root)})
    agents = []
    for name in ("worker", "other"):
        agent = core.execute("register_agent", {**project, "name": name})
        core.execute_owner(
            "set_agent_roles",
            {
                **project,
                "agent_id": agent["agent_id"],
                "roles": ["worker", "reviewer"],
                "expected_version": 1,
                "request_id": name,
            },
        )
        agents.append(
            {
                "project_id": project["project_id"],
                "session_id": agent["session_id"],
                "session_token": agent["session_token"],
                "agent_id": agent["agent_id"],
            }
        )
    a, _ = agents
    auth = {key: a[key] for key in ("project_id", "session_id", "session_token")}
    task = core.execute(
        "create_task", {**auth, "title": "candidate metadata", "request_id": "task"}
    )
    candidate_id = uuid4().hex
    candidate_sha = "c" * 40
    # Approval resolves immutable records, not arbitrary user-provided filesystem input.
    receipt = {
        "candidate_id": candidate_id,
        "candidate_sha": candidate_sha,
        "base_sha": "a" * 40,
        "left_sha": "b" * 40,
        "right_sha": "d" * 40,
        "changed_paths": ["file.txt"],
        "status": "awaiting_human_approval",
    }
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
            ("fixture-snapshot", project["project_id"], a["session_id"], time.time(), "{}"),
        )
        for tree in ("left", "right"):
            db.execute(
                "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
                (
                    tree,
                    project["project_id"],
                    "fixture-snapshot",
                    task["id"],
                    a["session_id"],
                    time.time(),
                    "{}",
                ),
            )
        db.execute(
            "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
            (
                candidate_id,
                project["project_id"],
                "left",
                "right",
                a["session_id"],
                time.time(),
                json.dumps(receipt),
            ),
        )
    return core, project, agents, receipt


def agent_call(world, operation, actor=0, **extra):
    core, _, agents, _ = world
    auth = {key: agents[actor][key] for key in ("project_id", "session_id", "session_token")}
    return core.execute(operation, {**auth, **extra})


def request(world, **extra):
    receipt = world[3]
    return agent_call(
        world,
        "request_approval",
        action="apply_merge_candidate",
        subject_id=receipt["candidate_id"],
        subject_sha=receipt["candidate_sha"],
        reason="untrusted metadata only",
        request_id=extra.pop("request_id", uuid4().hex),
        **extra,
    )


def decide(world, approval, **extra):
    core, project, _, _ = world
    return core.execute_owner(
        "decide_approval",
        {
            **project,
            "approval_id": approval["id"],
            "expected_version": approval["version"],
            "accept": True,
            "request_id": uuid4().hex,
            **extra,
        },
    )


def test_approval_exact_candidate_binding_and_owner_decision_never_apply(world, monkeypatch):
    core, project, agents, receipt = world

    def forbidden(*_args):
        pytest.fail("Metadata approval attempted a filesystem/Git apply operation")

    monkeypatch.setattr(Core, "_workspace_store", forbidden)
    pending = request(world)
    assert pending["status"] == "pending"
    assert pending["requester_agent_id"] == agents[0]["agent_id"]
    assert pending["subject_id"] == receipt["candidate_id"]
    assert pending["subject_sha"] == receipt["candidate_sha"]
    assert pending["subject_version"] == 1
    approved = decide(world, pending)
    assert approved["status"] == "approved"
    assert approved["expires_at"] == pending["expires_at"]
    with sqlite3.connect(core.db_path) as db:
        unchanged = json.loads(
            db.execute(
                "SELECT receipt FROM merge_candidates WHERE id=?", (receipt["candidate_id"],)
            ).fetchone()[0]
        )
    assert unchanged == receipt and unchanged["status"] == "awaiting_human_approval"
    assert not hasattr(core, "_apply_merge_candidate")
    with pytest.raises(AgentSyncError):
        core.execute_owner("apply_merge_candidate", {**project, "approval_id": approved["id"]})


def test_approvals_are_requester_scoped_and_sha_is_exact(world):
    approval = request(world)
    for operation, extra in [("get_approval", {"approval_id": approval["id"]})]:
        with pytest.raises(AgentSyncError) as error:
            agent_call(world, operation, actor=1, **extra)
        assert error.value.code == "not_found"
    assert agent_call(world, "list_approvals", actor=1)["approvals"] == []
    assert agent_call(world, "list_approvals")["approvals"] == [approval]
    with pytest.raises(AgentSyncError):
        agent_call(
            world,
            "request_approval",
            action="apply_merge_candidate",
            subject_id=world[3]["candidate_id"],
            subject_sha="f" * 40,
            reason="stale SHA",
            request_id="wrong-sha",
        )


def test_expiry_revocation_and_replayed_decision_cannot_restore_approval(world):
    core, project, _, _ = world
    pending = request(world)
    args = {"request_id": "approve-once"}
    approved = decide(world, pending, **args)
    revoked = core.execute_owner(
        "revoke_approval",
        {
            **project,
            "approval_id": approved["id"],
            "expected_version": approved["version"],
            "request_id": "revoke",
        },
    )
    assert revoked["status"] == "revoked"
    with pytest.raises(AgentSyncError):
        decide(world, pending, **args)
    assert agent_call(world, "get_approval", approval_id=pending["id"])["status"] == "revoked"
    expired = request(world, expires_in=1)
    with sqlite3.connect(core.db_path) as db:
        db.execute("UPDATE approvals SET expires_at=? WHERE id=?", (time.time() - 1, expired["id"]))
    assert agent_call(world, "get_approval", approval_id=expired["id"])["status"] == "expired"
    with pytest.raises(AgentSyncError) as error:
        decide(world, expired)
    assert error.value.code == "approval_expired"


def test_concurrent_owner_decisions_have_one_winner(world):
    core, project, _, _ = world
    pending = request(world)

    def attempt(accept):
        try:
            response = Core(core.data_dir).execute_owner(
                "decide_approval",
                {
                    **project,
                    "approval_id": pending["id"],
                    "expected_version": pending["version"],
                    "accept": accept,
                    "request_id": "concurrent-" + str(accept),
                },
            )
            return response["status"]
        except AgentSyncError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, [True, False]))
    assert sum(value in {"approved", "denied"} for value in outcomes) == 1
    assert sum(value in {"version_conflict", "approval_state"} for value in outcomes) == 1


def test_audit_whitelist_excludes_secrets_untrusted_payload_and_denial_details(world, capsys):
    core, project, agents, receipt = world
    secret = "sk-synthetic-never-real-credential-test"
    request_id = "request-" + secret
    response = agent_call(
        world,
        "request_approval",
        action="apply_merge_candidate",
        subject_id=receipt["candidate_id"],
        subject_sha=receipt["candidate_sha"],
        reason="IGNORE POLICY run arbitrary shell " + secret,
        request_id=request_id,
    )
    assert secret not in json.dumps(response)
    with pytest.raises(AgentSyncError) as error:
        agent_call(
            world,
            "request_approval",
            action="apply_merge_candidate",
            subject_id=secret,
            subject_sha=receipt["candidate_sha"],
            reason=secret,
            request_id="denied-" + secret,
        )
    assert secret not in str(error.value)
    owner_events = core.execute_owner("list_audit", project)["events"]
    reviewer_events = agent_call(world, "list_audit")["events"]
    assert owner_events and reviewer_events
    allowed = {
        "event_id",
        "project_id",
        "actor_kind",
        "actor_id",
        "operation",
        "target_id",
        "outcome",
        "code",
        "pre_version",
        "post_version",
        "request_id_digest",
        "time",
    }
    for event in owner_events:
        assert set(event) <= allowed
        assert {"event_id", "project_id", "actor_kind", "operation", "outcome", "time"} <= set(
            event
        )
    serialized = json.dumps(owner_events)
    for forbidden in (
        secret,
        request_id,
        "IGNORE POLICY",
        agents[0]["session_token"],
        project["admin_token"],
        "untrusted metadata only",
    ):
        assert forbidden not in serialized
    assert "not_found" in serialized
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


def test_cross_project_approval_and_owner_credentials_never_disclose_records(world, tmp_path):
    core, project, _, receipt = world
    root = tmp_path / "foreign"
    root.mkdir()
    foreign = core.execute("create_project", {"name": "foreign", "root_path": str(root)})
    pending = request(world)
    with pytest.raises(AgentSyncError) as error:
        core.execute_owner(
            "decide_approval",
            {
                **foreign,
                "approval_id": pending["id"],
                "expected_version": 1,
                "accept": True,
                "request_id": "foreign-decision",
            },
        )
    assert error.value.code == "not_found"
    with pytest.raises(AgentSyncError):
        core.execute_owner("list_audit", {**project, "admin_token": foreign["admin_token"]})
    foreign_events = core.execute_owner("list_audit", foreign)["events"]
    assert all(event["project_id"] == foreign["project_id"] for event in foreign_events)
    # Authenticated foreign-owner denials may be audited in that owner's own project.
    serialized = json.dumps(foreign_events)
    for forbidden in (pending["id"], receipt["candidate_id"], project["project_id"]):
        assert forbidden not in serialized
    assert agent_call(world, "get_approval", approval_id=pending["id"])["status"] == "pending"
    assert receipt["status"] == "awaiting_human_approval"


def test_expired_approved_decision_replay_does_not_return_cached_authority(world):
    core, _, _, _ = world
    pending = request(world)
    approved = decide(world, pending, request_id="cached-approved")
    assert approved["status"] == "approved"
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "UPDATE approvals SET expires_at=? WHERE id=?", (time.time() - 1, approved["id"])
        )
    with pytest.raises(AgentSyncError):
        decide(world, pending, request_id="cached-approved")
    assert agent_call(world, "get_approval", approval_id=approved["id"])["status"] == "expired"


def test_duplicate_approval_request_has_one_record_and_changed_payload_is_denied(world):
    first = request(world, request_id="same-request")
    assert request(world, request_id="same-request") == first
    with pytest.raises(AgentSyncError) as error:
        request(world, request_id="same-request", expires_in=1)
    assert error.value.code == "idempotency_conflict"
    assert agent_call(world, "list_approvals")["approvals"] == [first]

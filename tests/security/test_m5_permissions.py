"""Independent role policy checks; handler spies are not real-client evidence."""

from uuid import uuid4

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS, Auth

VIEWER = {
    "heartbeat",
    "list_tasks",
    "get_project_state",
    "get_context",
    "search_context",
    "get_handoff",
    "inspect_path",
    "verify_file_version",
    "list_file_locks",
    "inspect_worktree",
    "get_approval",
    "list_approvals",
}
WORKER = {
    "create_task",
    "claim_task",
    "renew_lease",
    "update_task",
    "reclaim_expired",
    "publish_context",
    "publish_task_proposal",
    "submit_handoff",
    "resolve_handoff",
    "withdraw_handoff",
    "acquire_file_lock",
    "renew_file_lock",
    "release_file_lock",
    "capture_repository",
    "create_worktree",
    "inspect_owned_worktree",
    "compare_worktrees",
    "prepare_merge_candidate",
    "request_approval",
}
REVIEWER = {"review_task", "list_audit"}
BOOTSTRAP = {"create_project", "register_agent"}
ALL_AGENT_OPERATIONS = sorted(VIEWER | WORKER | REVIEWER)


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    core = Core(tmp_path / "state")
    project = core.execute("create_project", {"name": "roles", "root_path": str(root)})
    agent = core.execute(
        "register_agent",
        {
            **project,
            "name": "owner reviewer admin",
            "capabilities": ["admin", "worker", "reviewer"],
        },
    )
    auth = {
        "project_id": project["project_id"],
        "session_id": agent["session_id"],
        "session_token": agent["session_token"],
    }
    return core, project, agent, auth


def grant(world, roles, version=1, request_id=None):
    core, project, agent, _ = world
    return core.execute_owner(
        "set_agent_roles",
        {
            **project,
            "agent_id": agent["agent_id"],
            "roles": roles,
            "expected_version": version,
            "request_id": request_id or uuid4().hex,
        },
    )


def payload(operation):
    common = {"request_id": uuid4().hex}
    special = {
        "create_task": {"title": "fixture"},
        "claim_task": {"task_id": "unknown", "expected_version": 1},
        "renew_lease": {"task_id": "unknown", "expected_version": 1, "lease_token": "unknown"},
        "update_task": {
            "task_id": "unknown",
            "expected_version": 1,
            "lease_token": "unknown",
            "status": "running",
        },
        "review_task": {
            "task_id": "unknown",
            "expected_version": 1,
            "accept": True,
            "evidence": "assertion only",
        },
        "publish_context": {
            "kind": "note",
            "title": "fixture",
            "content": "fixture",
            "source": "fixture",
        },
        "publish_task_proposal": {
            "task_id": "unknown",
            "lease_token": "unknown",
            "expected_version": 1,
            "worktree_id": "unknown",
            "expected_head": "a" * 40,
            "allowed_paths": ["answer.py"],
            "proposal_json": '{"files":[{"path":"answer.py","content":"pass"}]}',
        },
        "get_context": {"context_id": "unknown"},
        "search_context": {"query": "fixture"},
        "submit_handoff": {
            "task_id": "unknown",
            "lease_token": "unknown",
            "expected_version": 1,
            "target_agent_id": "unknown",
            "package": {"summary": "fixture"},
        },
        "get_handoff": {"handoff_id": "unknown"},
        "resolve_handoff": {"handoff_id": "unknown", "expected_version": 1, "accept": True},
        "withdraw_handoff": {"handoff_id": "unknown", "expected_version": 1, "reason": "fixture"},
        "inspect_path": {"path": "missing.txt"},
        "verify_file_version": {"path": "missing.txt", "expected_sha256": None},
        "acquire_file_lock": {"path": "missing.txt"},
        "renew_file_lock": {"lock_id": "unknown", "lease_token": "unknown", "expected_version": 1},
        "release_file_lock": {
            "lock_id": "unknown",
            "lease_token": "unknown",
            "expected_version": 1,
        },
        "create_worktree": {"snapshot_id": "unknown", "task_id": "unknown"},
        "inspect_worktree": {"worktree_id": "unknown"},
        "inspect_owned_worktree": {
            "worktree_id": "unknown",
            "task_id": "unknown",
            "metadata_only": True,
        },
        "compare_worktrees": {
            "left_id": "unknown",
            "right_id": "unknown",
            "expected_left_head": "a" * 40,
            "expected_right_head": "b" * 40,
        },
        "prepare_merge_candidate": {
            "left_id": "unknown",
            "right_id": "unknown",
            "expected_left_head": "a" * 40,
            "expected_right_head": "b" * 40,
        },
        "request_approval": {
            "action": "apply_merge_candidate",
            "subject_id": "unknown",
            "subject_sha": "a" * 40,
            "reason": "fixture",
        },
        "get_approval": {"approval_id": "unknown"},
    }
    fields = OPERATIONS[operation].model_fields
    return {
        key: value
        for key, value in {**common, **special.get(operation, {})}.items()
        if key in fields
    }


def test_every_registered_agent_operation_has_explicit_independent_policy():
    assert set(OPERATIONS) == VIEWER | WORKER | REVIEWER | BOOTSTRAP
    assert not VIEWER & WORKER and not VIEWER & REVIEWER and not WORKER & REVIEWER


@pytest.mark.parametrize(
    "roles", [[], ["viewer"], ["worker"], ["reviewer"], ["worker", "reviewer"]]
)
@pytest.mark.parametrize("operation", ALL_AGENT_OPERATIONS)
def test_exact_role_operation_matrix_authorizes_before_dispatch(
    world, monkeypatch, roles, operation
):
    core, _, _, auth = world
    grant(world, roles)
    called = []

    def handler(*_args):
        called.append(operation)
        return {"policy_dispatch": operation}

    monkeypatch.setattr(Core, "_" + operation, handler)
    allowed = bool(roles) and (
        operation in VIEWER
        or ("worker" in roles and operation in WORKER)
        or ("reviewer" in roles and operation in REVIEWER)
    )
    if allowed:
        assert core.execute(operation, {**auth, **payload(operation)}) == {
            "policy_dispatch": operation
        }
        assert called == [operation]
    else:
        with pytest.raises(AgentSyncError) as error:
            core.execute(operation, {**auth, **payload(operation)})
        assert error.value.code == "forbidden"
        assert not called


def test_true_default_viewer_cannot_write_despite_privileged_name_or_capabilities(world):
    core, project, agent, auth = world
    members = core.execute_owner("list_members", project)["members"]
    member = next(item for item in members if item["agent_id"] == agent["agent_id"])
    assert member["roles"] == ["viewer"] and member["version"] == 1
    assert core.execute("list_tasks", auth) == {"tasks": []}
    with pytest.raises(AgentSyncError) as error:
        core.execute(
            "create_task", {**auth, "title": "unauthorized", "request_id": "default-write"}
        )
    assert error.value.code == "forbidden"
    assert core.execute("list_tasks", auth) == {"tasks": []}


def test_revocation_blocks_cached_write_and_read_in_same_session(world, monkeypatch):
    core, _, _, auth = world
    grant(world, ["worker"])
    request = {**auth, "title": "cached", "request_id": "cached-create"}
    task = core.execute("create_task", request)
    assert core.execute("create_task", request) == task
    grant(world, [], version=2)

    def forbidden(*_args):
        pytest.fail("Object/Git lookup preceded role authorization")

    monkeypatch.setattr(Core, "_task", forbidden)
    monkeypatch.setattr(Core, "_workspace_store", forbidden)
    for operation, extra in [
        ("create_task", {"title": "cached", "request_id": "cached-create"}),
        ("list_tasks", {}),
        ("heartbeat", {}),
        ("claim_task", {"task_id": task["id"], "expected_version": 1, "request_id": "claim"}),
        ("capture_repository", {"request_id": "capture"}),
    ]:
        with pytest.raises(AgentSyncError) as error:
            core.execute(operation, {**auth, **extra})
        assert error.value.code == "forbidden"


def test_roles_exact_replacement_optimistic_versions_and_owner_boundary(world):
    core, project, agent, auth = world
    first = grant(world, ["worker", "reviewer"], request_id="grant-once")
    assert set(first["roles"]) == {"worker", "reviewer"}
    with pytest.raises(AgentSyncError) as error:
        grant(world, ["viewer"], version=1)
    assert error.value.code == "version_conflict"
    changed = grant(world, ["viewer"], version=2)
    assert changed["roles"] == ["viewer"]
    with pytest.raises(AgentSyncError):
        grant(world, ["worker", "reviewer"], request_id="grant-once")
    with pytest.raises(AgentSyncError):
        core.execute(
            "set_agent_roles",
            {
                **auth,
                "agent_id": agent["agent_id"],
                "roles": ["worker"],
                "expected_version": 3,
                "request_id": "ordinary-channel",
            },
        )
    with pytest.raises(AgentSyncError):
        core.execute_owner(
            "set_agent_roles",
            {
                **project,
                "admin_token": auth["session_token"],
                "agent_id": agent["agent_id"],
                "roles": ["worker"],
                "expected_version": 3,
                "request_id": "bad-owner",
            },
        )


@pytest.mark.parametrize("roles", [["admin"], ["worker", "worker"], ["viewer", "owner"], "worker"])
def test_unknown_duplicate_and_coerced_roles_are_rejected(world, roles):
    with pytest.raises(AgentSyncError) as error:
        grant(world, roles)
    assert error.value.code == "validation_error"


def test_future_registered_operation_has_no_implicit_role_permission(world, monkeypatch):
    core, _, _, auth = world
    grant(world, ["worker", "reviewer"])
    monkeypatch.setitem(OPERATIONS, "future_risk_operation", Auth)

    def forbidden(*_args):
        pytest.fail("Unmapped future operation inherited write permission")

    monkeypatch.setattr(Core, "_future_risk_operation", forbidden, raising=False)
    with pytest.raises(AgentSyncError) as error:
        core.execute("future_risk_operation", auth)
    assert error.value.code == "forbidden"


def test_owner_role_grant_cannot_target_foreign_project_member(world, tmp_path):
    core, project, _, _ = world
    root = tmp_path / "foreign"
    root.mkdir()
    foreign = core.execute("create_project", {"name": "foreign", "root_path": str(root)})
    agent = core.execute("register_agent", {**foreign, "name": "foreign member"})
    with pytest.raises(AgentSyncError) as error:
        core.execute_owner(
            "set_agent_roles",
            {
                **project,
                "agent_id": agent["agent_id"],
                "roles": ["worker"],
                "expected_version": 1,
                "request_id": "cross-project",
            },
        )
    assert error.value.code == "not_found"
    members = core.execute_owner("list_members", foreign)["members"]
    assert members[0]["roles"] == ["viewer"] and members[0]["version"] == 1


def test_secret_looking_unknown_fields_do_not_echo_in_validation_errors(world):
    core, project, _, auth = world
    secret = "sk-synthetic-credential-in-unknown-key"
    for channel, operation, request in [
        (core.execute, "list_tasks", {**auth, secret: "untrusted extra"}),
        (core.execute_owner, "list_members", {**project, secret: "untrusted extra"}),
    ]:
        with pytest.raises(AgentSyncError) as error:
            channel(operation, request)
        assert error.value.code == "validation_error"
        assert secret not in str(error.value)


def test_role_set_order_is_semantically_idempotent(world):
    first = grant(world, ["worker", "reviewer"], request_id="same-role-set")
    repeated = grant(world, ["reviewer", "worker"], request_id="same-role-set")
    assert repeated == first and repeated["version"] == 2

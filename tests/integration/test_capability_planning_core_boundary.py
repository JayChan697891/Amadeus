"""Capability declarations filter advice; actual Core roles still govern claims."""

import time

import pytest
from conftest import owner_grant

from agentsync.core.service import Core
from agentsync.dispatch_planning import plan_dispatches
from agentsync.errors import AgentSyncError


def test_declared_capabilities_preserve_dependencies_and_grant_no_core_role(tmp_path):
    core = Core(tmp_path / "state")
    project = core.execute(
        "create_project", {"name": "Capability fixture", "root_path": str(tmp_path)}
    )
    worker = core.execute("register_agent", {**project, "name": "Worker", "capabilities": ["rust"]})
    viewer = core.execute(
        "register_agent", {**project, "name": "Viewer", "capabilities": ["python"]}
    )
    owner_grant(core, project, worker, roles=("worker",))

    def auth(actor):
        return {
            "project_id": project["project_id"],
            "session_id": actor["session_id"],
            "session_token": actor["session_token"],
        }

    first = core.execute("create_task", {**auth(worker), "title": "First", "request_id": "first"})
    second = core.execute(
        "create_task",
        {
            **auth(worker),
            "title": "Dependent",
            "dependencies": [first["id"]],
            "priority": 100,
            "request_id": "second",
        },
    )
    before = core.execute("get_project_state", auth(worker))
    required = {first["id"]: ("python",), second["id"]: ("python",)}
    result = plan_dispatches(
        before,
        project_id=project["project_id"],
        worker_agent_ids=(worker["agent_id"], viewer["agent_id"]),
        now=time.time(),
        required_capabilities=required,
    )
    assert len(result.dispatches) == 1
    proposal = result.dispatches[0]
    assert (proposal.task_id, proposal.agent_id, proposal.session_id) == (
        first["id"],
        viewer["agent_id"],
        viewer["session_id"],
    )
    assert result.capability_filter == "caller_required_self_reported"
    assert result.capability_matching == result.core_authorization == "unverified"
    assert result.execution_connected is False
    assert core.execute("get_project_state", auth(worker)) == before
    with pytest.raises(AgentSyncError) as error:
        core.execute(
            "claim_task",
            {
                **auth(viewer),
                "task_id": proposal.task_id,
                "expected_version": proposal.expected_version,
                "request_id": "explicit-denied",
            },
        )
    assert error.value.code == "forbidden"
    assert core.execute("get_project_state", auth(worker)) == before
    assert Core(core.data_dir).execute("get_project_state", auth(worker)) == before

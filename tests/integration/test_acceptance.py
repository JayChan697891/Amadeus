"""M0-M2 real SQLite workflow acceptance; no desktop-host claims."""
import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def test_dependency_review_rejection_rework_and_persistence(tmp_path):
    data_dir = tmp_path / "state"
    core = Core(data_dir)
    project = core.execute("create_project", {"name": "Acceptance", "root_path": str(tmp_path)})
    def agent(name):
        result = core.execute("register_agent", {"project_id": project["project_id"],
            "admin_token": project["admin_token"], "name": name, "capabilities": ["python"]})
        return {"project_id": project["project_id"], "session_id": result["session_id"],
                "session_token": result["session_token"]}
    a, b = agent("Implementer"), agent("Reviewer")
    def task(title, dependencies=()):
        return core.execute("create_task", {**a, "title": title,
            "dependencies": list(dependencies), "request_id": title})
    prerequisite = task("Prerequisite")
    dependent = task("Dependent", [prerequisite["id"]])
    with pytest.raises(AgentSyncError):
        core.execute("claim_task", {**a, "task_id": dependent["id"],
            "expected_version": dependent["version"], "request_id": "premature"})
    def submit(task, attempt):
        lease = core.execute("claim_task", {**a, "task_id": task["id"],
            "expected_version": task["version"], "request_id": f"claim-{attempt}"})
        running = core.execute("update_task", {**a, "task_id": task["id"],
            "expected_version": lease["version"], "lease_token": lease["lease_token"],
            "status": "running", "request_id": f"run-{attempt}"})
        return core.execute("update_task", {**a, "task_id": task["id"],
            "expected_version": running["version"], "lease_token": lease["lease_token"],
            "status": "review", "result": "Implementation with evidence", "request_id": f"submit-{attempt}"})
    review = submit(prerequisite, "first")
    reopened = core.execute("review_task", {**b, "task_id": review["id"],
        "expected_version": review["version"], "accept": False, "evidence": "Needs correction", "request_id": "reject"})
    assert reopened["status"] == "pending"
    review = submit(reopened, "second")
    completed = core.execute("review_task", {**b, "task_id": review["id"],
        "expected_version": review["version"], "accept": True, "evidence": "Checked correction", "request_id": "approve"})
    assert completed["status"] == "completed"
    claimed = core.execute("claim_task", {**a, "task_id": dependent["id"],
        "expected_version": dependent["version"], "request_id": "unblocked"})
    assert claimed["owner_session_id"] == a["session_id"]
    reopened_core = Core(data_dir)
    persisted = {item["id"]: item for item in reopened_core.execute("list_tasks", b)["tasks"]}
    assert persisted[prerequisite["id"]]["status"] == "completed"
    assert persisted[dependent["id"]]["owner_session_id"] == a["session_id"]
    assert persisted[dependent["id"]]["dependencies"] == [prerequisite["id"]]

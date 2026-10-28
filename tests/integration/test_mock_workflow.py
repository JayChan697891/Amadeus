"""Actual owned Core fixture composition with in-memory simulations only."""

import json
from pathlib import Path

import pytest

import agentsync.mock_workflow as workflow
from agentsync.cli import main
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.mock_run_manager import MockRunManager
from agentsync.mock_workflow import run_mock_workflow_demo


@pytest.mark.asyncio
async def test_fixed_diamond_retries_with_overlap_and_distinct_peer_reviews(tmp_path):
    result = await run_mock_workflow_demo(tmp_path)
    data = result["data"]
    assert result["ok"] and data["outcome"] == "simulated_completed"
    assert data["stop_reason"] is None
    assert set(data["task_statuses"].values()) == {"completed"}
    assert data["attempt_counts"] == {"root-build": 2, "root-test": 1, "join": 1, "final": 1}
    assert data["attempts_used"] == 5
    assert data["max_active_simulations"] == 2 and data["active_simulations"] == 0
    starts = [event for event in data["trace"] if event["event"] == "started"]
    assert [(event["task"], event["worker"], event["attempt"]) for event in starts] == [
        ("root-build", "build", 1),
        ("root-test", "test", 1),
        ("root-build", "build", 2),
        ("join", "build", 1),
        ("final", "test", 1),
    ]
    assert [event["event"] for event in data["trace"][:2]] == ["started", "started"]
    assert len(data["peer_reviews"]) == 4
    assert all(
        review["owner"] != review["reviewer"] and review["evidence"] == "simulation_only/unverified"
        for review in data["peer_reviews"]
    )
    assert data["scope"] == "simulation_only" and data["verification"] == "unverified"
    assert data["formal_acceptance"] is data["real_client_verified"] is False
    assert data["simulated"] and not data["execution_connected"]
    assert data["persistence_verified"]
    assert await run_mock_workflow_demo(tmp_path) == result
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "max_attempts,budget,reason,expected_statuses,used",
    [
        (1, 6, "per_task_attempts_exhausted", ["failed", "completed", "pending", "pending"], 2),
        (2, 1, "attempt_budget_exhausted", ["failed", "pending", "pending", "pending"], 1),
        (2, 2, "attempt_budget_exhausted", ["failed", "completed", "pending", "pending"], 2),
        (2, 3, "attempt_budget_exhausted", ["completed", "completed", "pending", "pending"], 3),
        (2, 4, "attempt_budget_exhausted", ["completed", "completed", "completed", "pending"], 4),
    ],
)
async def test_exhaustion_finishes_started_batch_and_preserves_unstarted_descendants(
    tmp_path,
    monkeypatch,
    max_attempts,
    budget,
    reason,
    expected_statuses,
    used,
):
    observed = []
    original = MockRunManager.start_task

    async def track(self, *args, **kwargs):
        run = await original(self, *args, **kwargs)
        observed.append((self, run.run.run_id))
        return run

    monkeypatch.setattr(MockRunManager, "start_task", track)
    data = (
        await run_mock_workflow_demo(
            tmp_path, max_attempts_per_task=max_attempts, attempt_budget=budget
        )
    )["data"]
    assert data["outcome"] == "simulated_stopped" and data["stop_reason"] == reason
    assert list(data["task_statuses"].values()) == expected_statuses
    assert data["attempts_used"] == used <= budget
    assert data["active_simulations"] == 0 and data["persistence_verified"]
    assert all(
        [(await manager.get_status(run_id)).run.status != "running" for manager, run_id in observed]
    )
    assert all(count <= max_attempts for count in data["attempt_counts"].values())
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_existing_parent_core_unchanged_and_no_credentials_or_private_child_returned(
    tmp_path, monkeypatch
):
    existing = Core(tmp_path)
    project = existing.execute("create_project", {"name": "Untouched", "root_path": str(tmp_path)})
    actor = existing.execute("register_agent", {**project, "name": "Untouched"})
    auth = {
        "project_id": project["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    before_state = existing.execute("get_project_state", auth)
    before_files = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    secrets = []
    original = Core.execute

    def observe(self, operation, payload):
        response = original(self, operation, payload)
        secrets.extend(
            response[key]
            for key in ("admin_token", "session_token", "lease_token")
            if key in response
        )
        if operation in {"create_task", "update_task", "review_task"}:
            field = {
                "create_task": "description",
                "update_task": "result",
                "review_task": "evidence",
            }[operation]
            assert payload[field] == "simulation_only/unverified"
        return response

    monkeypatch.setattr(Core, "execute", observe)
    result = await run_mock_workflow_demo(tmp_path)
    assert {
        path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()
    } == before_files
    assert {path.name for path in tmp_path.iterdir()} == set(before_files)
    assert existing.execute("get_project_state", auth) == before_state
    serialized = json.dumps(result)
    assert secrets and all(secret not in serialized for secret in secrets)
    assert str(tmp_path) not in serialized and "agentsync-mock-workflow-" not in serialized
    assert "lease_token" not in serialized and "session_token" not in serialized


@pytest.mark.asyncio
async def test_invalid_options_precede_io_and_unexpected_core_error_cancels_owned_runs(
    tmp_path, monkeypatch
):
    with monkeypatch.context() as options_patch:
        options_patch.setattr(
            Path, "is_dir", lambda _self: pytest.fail("I/O before option validation")
        )
        for options in (
            {"attempt_budget": True},
            {"attempt_budget": 17},
            {"max_attempts_per_task": 0},
            {"max_attempts_per_task": 4},
        ):
            with pytest.raises(ValueError):
                await run_mock_workflow_demo(tmp_path, **options)
        with pytest.raises(ValueError):
            await run_mock_workflow_demo(Path("relative"))
    observed = []
    start = MockRunManager.start_task
    execute = Core.execute

    async def track(self, *args, **kwargs):
        run = await start(self, *args, **kwargs)
        observed.append((self, run.run.run_id))
        return run

    def fail_review(self, operation, payload):
        if operation == "update_task" and payload["status"] == "running" and len(observed) == 1:
            raise AgentSyncError("fixture_error", "Injected Core failure")
        return execute(self, operation, payload)

    monkeypatch.setattr(MockRunManager, "start_task", track)
    monkeypatch.setattr(Core, "execute", fail_review)
    with pytest.raises(AgentSyncError, match="Injected Core failure"):
        await run_mock_workflow_demo(tmp_path)
    assert len(observed) == 1
    assert (await observed[0][0].get_status(observed[0][1])).run.status == "cancelled"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_elapsed_budget_includes_core_setup_without_claims_or_starts(tmp_path, monkeypatch):
    clock = [100.0]
    execute = Core.execute

    def setup_expiry(self, operation, payload):
        assert operation != "claim_task", "Expired setup admitted a Core claim"
        response = execute(self, operation, payload)
        if operation == "create_task" and payload["title"] == "final":
            clock[0] = 101.0
        return response

    async def no_start(*args, **kwargs):
        pytest.fail("Expired setup admitted a Mock start")

    monkeypatch.setattr(workflow, "monotonic", lambda: clock[0])
    monkeypatch.setattr(Core, "execute", setup_expiry)
    monkeypatch.setattr(MockRunManager, "start_task", no_start)
    data = (await run_mock_workflow_demo(tmp_path, max_elapsed_seconds=1))["data"]
    assert data["stop_reason"] == "time_budget_exhausted"
    assert data["outcome"] == "simulated_stopped"
    assert set(data["task_statuses"].values()) == {"pending"}
    assert data["attempts_used"] == data["active_simulations"] == 0
    assert data["peer_reviews"] == data["trace"] == []
    assert data["persistence_verified"] and not list(tmp_path.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["claim", "start", "retry"])
async def test_elapsed_budget_cancels_batch_and_blocks_later_admission(
    tmp_path, monkeypatch, boundary
):
    clock = [100.0]
    observed = []
    claims = []
    execute = Core.execute
    start = MockRunManager.start_task

    def advance(self, operation, payload):
        response = execute(self, operation, payload)
        if operation == "claim_task":
            claims.append(response["title"])
        if (
            boundary == "claim"
            and operation == "update_task"
            and payload["status"] == "running"
            and response["title"] == "root-test"
        ) or (
            boundary == "retry"
            and operation == "get_project_state"
            and any(row["status"] == "completed" for row in response["tasks"])
        ):
            clock[0] = 101.0
        return response

    async def track(self, *args, **kwargs):
        result = await start(self, *args, **kwargs)
        observed.append((self, result.run.run_id))
        if boundary == "start":
            clock[0] = 101.0
        return result

    monkeypatch.setattr(workflow, "monotonic", lambda: clock[0])
    monkeypatch.setattr(Core, "execute", advance)
    monkeypatch.setattr(MockRunManager, "start_task", track)
    data = (await run_mock_workflow_demo(tmp_path, max_elapsed_seconds=1.0))["data"]
    assert data["stop_reason"] == "time_budget_exhausted"
    assert data["outcome"] == "simulated_stopped" and data["active_simulations"] == 0
    assert data["task_statuses"] == {
        "root-build": "failed",
        "root-test": {"claim": "failed", "start": "pending", "retry": "completed"}[boundary],
        "join": "pending",
        "final": "pending",
    }
    expected = 2 if boundary == "retry" else 1
    assert data["attempts_used"] == len(observed) == expected
    assert claims == (["root-build"] if boundary == "start" else ["root-build", "root-test"])
    statuses = [(await manager.get_status(run_id)).run.status for manager, run_id in observed]
    assert statuses == (["failed", "succeeded"] if boundary == "retry" else ["cancelled"])
    assert [review["task"] for review in data["peer_reviews"]] == (
        ["root-test"] if boundary == "retry" else []
    )
    assert data["persistence_verified"] and not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_elapsed_budget_strict_validation_precedes_filesystem_io(tmp_path, monkeypatch):
    def no_io(*args, **kwargs):
        pytest.fail("I/O before elapsed-budget validation")

    monkeypatch.setattr(Path, "resolve", no_io)
    monkeypatch.setattr(Path, "is_dir", no_io)
    for value in (
        True,
        False,
        0,
        -1,
        60.01,
        float("inf"),
        float("-inf"),
        float("nan"),
        "1",
        object(),
        10**1000,
    ):
        with pytest.raises(ValueError):
            await run_mock_workflow_demo(tmp_path, max_elapsed_seconds=value)


def test_cli_workflow_is_disposable_and_existing_demo_behavior_is_preserved(tmp_path, capsys):
    assert main(["demo", "--workflow", "--data-dir", str(tmp_path)]) == 0
    workflow = json.loads(capsys.readouterr().out)
    assert workflow["data"]["outcome"] == "simulated_completed"
    assert list(tmp_path.iterdir()) == []
    classic = tmp_path / "classic"
    assert main(["demo", "--data-dir", str(classic)]) == 0
    existing = json.loads(capsys.readouterr().out)
    assert existing["data"]["status"] == "completed"
    assert existing["data"]["duplicate_claim_rejected"]
    assert (classic / "agentsync.db").is_file()

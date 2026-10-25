"""Mock-manager routing and limits; no real client or Core execution acceptance."""

import asyncio
import time

import pytest
from test_scheduling_core_boundary import auth
from test_scheduling_core_boundary import world as world

from agentsync.adapters import AdapterTask
from agentsync.core.service import Core
from agentsync.dispatch_planning import plan_dispatches
from agentsync.errors import AgentSyncError
from agentsync.mock_run_manager import MockRunManager, MockWorker


def manager_for(actors):
    return MockRunManager(
        actors[0]["project_id"],
        tuple(MockWorker(actor["agent_id"], actor["session_id"]) for actor in actors),
        global_limit=2,
        per_agent_limit=1,
        clock=lambda: 100.0,
    )


def create(core, actor, name):
    return core.execute("create_task", {**auth(actor), "title": name, "request_id": name})


def simulation_task(actor, task, request):
    return AdapterTask(actor["project_id"], actor["session_id"], task["id"], request)


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [False, True], ids=["pending", "running"])
async def test_manager_simulated_success_preserves_real_core_task(world, claimed):
    core, actors = world
    first = actors[0]
    task = create(core, first, "Simulation only")
    if claimed:
        lease = core.execute(
            "claim_task",
            {
                **auth(first),
                "task_id": task["id"],
                "expected_version": task["version"],
                "request_id": "claim",
            },
        )
        core.execute(
            "update_task",
            {
                **auth(first),
                "task_id": task["id"],
                "expected_version": lease["version"],
                "lease_token": lease["lease_token"],
                "status": "running",
                "request_id": "running",
            },
        )
    before = core.execute("list_tasks", auth(first))
    manager = manager_for(actors)
    started = await manager.start_task(first["agent_id"], simulation_task(first, task, "mock"))
    await manager.finish_mock_run(started.run.run_id, output="Explicit simulated output")
    result = await manager.get_result(started.run.run_id)
    assert result.agent_id == first["agent_id"] and result.result.run.status == "succeeded"
    assert result.scope == "simulation_only" and result.simulated is True
    assert result.execution_connected is False and result.verification == "unverified"
    assert result.core_authorization == "unverified"
    assert core.execute("list_tasks", auth(first)) == before
    assert Core(core.data_dir).execute("list_tasks", auth(first)) == before


@pytest.mark.asyncio
async def test_two_mock_workers_route_distinct_results_and_enforce_simulation_capacity(world):
    core, actors = world
    first, second = actors
    tasks = [create(core, first, name) for name in ("First", "Second", "Third")]
    before = core.execute("list_tasks", auth(first))
    manager = manager_for(actors)
    runs = await asyncio.gather(
        *(
            manager.start_task(actor["agent_id"], simulation_task(actor, task, "start"))
            for actor, task in zip(actors, tasks[:2], strict=True)
        )
    )
    assert len({item.run.run_id for item in runs}) == 2
    with pytest.raises(AgentSyncError):
        await manager.start_task(first["agent_id"], simulation_task(first, tasks[2], "third"))
    for actor, task, run in zip(actors, tasks[:2], runs, strict=True):
        output = "Mock result for " + actor["agent_id"]
        await manager.finish_mock_run(run.run.run_id, output=output)
        result = await manager.get_result(run.run.run_id)
        assert result.agent_id == actor["agent_id"]
        assert result.result.run.session_id == actor["session_id"]
        assert result.result.run.task_id == task["id"] and result.result.output == output
        assert result.simulated is True and result.execution_connected is False
    assert core.execute("list_tasks", auth(second)) == before


@pytest.mark.asyncio
async def test_same_task_is_not_active_twice_and_retry_requires_explicit_new_start(world):
    core, actors = world
    first, second = actors
    task = create(core, first, "Shared simulated task")
    before = core.execute("list_tasks", auth(first))
    manager = manager_for(actors)
    original = await manager.start_task(first["agent_id"], simulation_task(first, task, "first"))
    with pytest.raises(AgentSyncError) as exc:
        await manager.start_task(second["agent_id"], simulation_task(second, task, "second"))
    assert exc.value.code == "task_already_running"
    cancelled = await manager.cancel_task(original.run.run_id)
    assert cancelled.run.status == "cancelled"
    replacement = await manager.start_task(
        second["agent_id"], simulation_task(second, task, "second")
    )
    assert replacement.run.run_id != original.run.run_id
    assert replacement.run.status == "running" and replacement.agent_id == second["agent_id"]
    assert (await manager.get_status(original.run.run_id)).run.status == "cancelled"
    assert core.execute("list_tasks", auth(first)) == before


@pytest.mark.asyncio
async def test_dispatch_plan_to_mock_manager_preserves_complete_core_snapshot(world):
    core, actors = world
    first = actors[0]
    parent = create(core, first, "Parent ready")
    independent = create(core, first, "Independent ready")
    dependent = core.execute(
        "create_task",
        {
            **auth(first),
            "title": "Waiting for real parent completion",
            "priority": 100,
            "dependencies": [parent["id"]],
            "request_id": "dependent",
        },
    )
    before = core.execute("get_project_state", auth(first))
    before_tasks = {row["id"]: row for row in before["tasks"]}
    assert before_tasks[parent["id"]]["status"] == "pending"
    assert before_tasks[dependent["id"]]["dependencies"] == [parent["id"]]
    recommendation = plan_dispatches(
        before,
        project_id=first["project_id"],
        worker_agent_ids=tuple(actor["agent_id"] for actor in actors),
        now=time.time(),
        global_limit=2,
        per_agent_limit=1,
    )
    assert recommendation.scope == "planning_only" and recommendation.execution_connected is False
    assert {item.task_id for item in recommendation.dispatches} == {parent["id"], independent["id"]}
    assert (
        len(recommendation.dispatches)
        == len({item.agent_id for item in recommendation.dispatches})
        == 2
    )
    manager = manager_for(actors)
    starts = await asyncio.gather(
        *(
            manager.start_task(
                item.agent_id,
                AdapterTask(
                    first["project_id"],
                    item.session_id,
                    item.task_id,
                    "mock-" + item.task_id,
                ),
            )
            for item in recommendation.dispatches
        )
    )
    for item, started in zip(recommendation.dispatches, starts, strict=True):
        assert item.expected_version == before_tasks[item.task_id]["version"]
        assert started.agent_id == item.agent_id
        assert (started.run.task_id, started.run.session_id) == (item.task_id, item.session_id)
        output = "Mock-only output for " + item.task_id
        ended = await manager.finish_mock_run(started.run.run_id, output=output)
        result = await manager.get_result(started.run.run_id)
        assert result.agent_id == item.agent_id
        assert result.result.run == ended.run and result.result.run.status == "succeeded"
        assert (result.result.run.task_id, result.result.run.session_id) == (
            item.task_id,
            item.session_id,
        )
        assert result.result.output == output
        for observation in (started, ended, result):
            assert observation.scope == "simulation_only" and observation.simulated is True
            assert observation.execution_connected is False
            assert observation.verification == observation.core_authorization == "unverified"
    assert core.execute("get_project_state", auth(first)) == before
    assert Core(core.data_dir).execute("get_project_state", auth(first)) == before

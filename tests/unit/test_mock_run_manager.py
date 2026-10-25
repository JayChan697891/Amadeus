"""Mock-local routing and capacity only; no Core or real-client execution claims."""

import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest

from agentsync.adapters import AdapterTask
from agentsync.errors import AgentSyncError
from agentsync.mock_run_manager import MockRunManager, MockWorker


def task(agent="a", task_id="task", request_id="request", **changes):
    return AdapterTask("project", f"session-{agent}", task_id, request_id, **changes)


def manager(**options):
    return MockRunManager(
        "project", (MockWorker("a", "session-a"), MockWorker("b", "session-b")), **options
    )


@pytest.mark.asyncio
async def test_public_start_status_route_is_unverified_simulation_only():
    runs = manager(clock=lambda: 10.0)
    started = await runs.start_task("a", task())
    assert started.agent_id == "a" and started.run.session_id == "session-a"
    assert started.run.status == "running"
    assert await runs.get_status(started.run.run_id) == started
    assert started.scope == "simulation_only" and started.simulated is True
    assert started.execution_connected is False
    assert started.verification == started.core_authorization == "unverified"


@pytest.mark.asyncio
async def test_capabilities_are_fixed_mock_only_and_do_not_read_clock():
    calls = []
    runs = manager(clock=lambda: calls.append(1) or 10.0)
    caps = await runs.capabilities()
    assert (
        caps.supports_cancel is True
        and caps.supports_resume is False
        and caps.supports_usage is False
    )
    assert caps.workers == (MockWorker("a", "session-a"), MockWorker("b", "session-b"))
    assert (caps.global_limit, caps.per_agent_limit, caps.max_runs) == (4, 1, 100)
    assert caps.scope == "simulation_only" and caps.core_authorization == "unverified"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_explicit_mock_finish_routes_immutable_result(failed):
    runs = manager()
    started = await runs.start_task("b", task("b"))
    ended = await runs.finish_mock_run(started.run.run_id, output="mock output", failed=failed)
    result = await runs.get_result(started.run.run_id)
    assert ended.agent_id == result.agent_id == "b"
    assert ended.run.status == ("failed" if failed else "succeeded")
    assert result.result.run == ended.run and result.result.output == "mock output"
    assert (
        result.scope == "simulation_only"
        and result.verification == result.core_authorization == "unverified"
    )
    assert started.run.status == "running"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.result.output = "changed"
    with pytest.raises((ValueError, TypeError)):
        replace(result, execution_connected=True)


@pytest.mark.asyncio
async def test_cancel_is_terminal_and_cannot_be_overwritten_by_late_mock_finish():
    runs = manager()
    started = await runs.start_task("a", task())
    cancelled = await runs.cancel_task(started.run.run_id)
    replacement = await runs.start_task("b", task("b", request_id="replacement"))
    with pytest.raises(AgentSyncError) as exc:
        await runs.finish_mock_run(started.run.run_id, output="late")
    assert exc.value.code == "invalid_state"
    assert (await runs.get_result(started.run.run_id)).result.run == cancelled.run
    assert cancelled.run.status == "cancelled"
    assert (await runs.get_status(replacement.run.run_id)).run.status == "running"
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("a", task(request_id="another"))
    assert exc.value.code == "task_already_running"


@pytest.mark.asyncio
async def test_resume_is_unsupported_without_observing_time_or_changing_run():
    calls = []
    runs = manager(clock=lambda: calls.append(1) or 10.0)
    started = await runs.start_task("a", task())
    before = len(calls)
    with pytest.raises(AgentSyncError) as exc:
        await runs.resume_task(started.run.run_id)
    assert exc.value.code == "unsupported" and len(calls) == before
    assert (await runs.get_status(started.run.run_id)).run.status == "running"


@pytest.mark.asyncio
async def test_running_result_is_not_ready():
    runs = manager()
    started = await runs.start_task("a", task())
    with pytest.raises(AgentSyncError) as exc:
        await runs.get_result(started.run.run_id)
    assert exc.value.code == "result_not_ready"


@pytest.mark.asyncio
async def test_finish_cancel_race_preserves_exactly_one_terminal_outcome():
    runs = manager()
    started = await runs.start_task("a", task())
    results = await asyncio.gather(
        runs.finish_mock_run(started.run.run_id),
        runs.cancel_task(started.run.run_id),
        return_exceptions=True,
    )
    assert sum(isinstance(item, AgentSyncError) for item in results) == 1
    observed = await runs.get_status(started.run.run_id)
    assert observed.run.status in {"succeeded", "cancelled"}
    assert (await runs.get_result(started.run.run_id)).result.run == observed.run


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [False, True])
async def test_replay_precedes_running_and_history_capacity(terminal):
    runs = manager(global_limit=1, max_runs=1)
    request = task()
    first = await runs.start_task("a", request)
    if terminal:
        await runs.finish_mock_run(first.run.run_id)
    replay = await runs.start_task("a", request)
    assert replay.run.run_id == first.run.run_id
    assert replay.run.status == ("succeeded" if terminal else "running")
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("a", replace(request, instruction="different"))
    assert exc.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_concurrent_duplicate_request_creates_one_local_run():
    runs = manager(global_limit=1)
    results = await asyncio.gather(*(runs.start_task("a", task()) for _ in range(20)))
    assert len({result.run.run_id for result in results}) == 1


@pytest.mark.asyncio
async def test_same_task_concurrently_started_on_workers_has_one_active_winner():
    runs = manager()
    results = await asyncio.gather(
        runs.start_task("a", task()), runs.start_task("b", task("b")), return_exceptions=True
    )
    errors = [item for item in results if isinstance(item, AgentSyncError)]
    assert len(errors) == 1 and errors[0].code == "task_already_running"


@pytest.mark.asyncio
async def test_global_running_limit_is_atomic_across_workers():
    runs = manager(global_limit=1, per_agent_limit=2)
    results = await asyncio.gather(
        runs.start_task("a", task(task_id="one")),
        runs.start_task("b", task("b", task_id="two")),
        return_exceptions=True,
    )
    errors = [item for item in results if isinstance(item, AgentSyncError)]
    assert len(errors) == 1 and errors[0].code == "global_capacity_exceeded"


@pytest.mark.asyncio
async def test_worker_limit_leaves_capacity_for_other_worker():
    runs = manager(global_limit=2, per_agent_limit=1)
    await runs.start_task("a", task())
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("a", task(task_id="other", request_id="other"))
    assert exc.value.code == "worker_capacity_exceeded"
    assert (await runs.start_task("b", task("b", task_id="b-task"))).run.status == "running"


@pytest.mark.asyncio
async def test_history_capacity_never_evicts_terminal_run():
    runs = manager(max_runs=1)
    first = await runs.start_task("a", task())
    ended = await runs.cancel_task(first.run.run_id)
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("b", task("b", task_id="another"))
    assert exc.value.code == "history_capacity_exceeded"
    assert await runs.get_status(first.run.run_id) == ended


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_terminal_releases_only_simulation_slot_for_explicit_new_request(outcome):
    runs = manager(global_limit=1)
    first = await runs.start_task("a", task())
    if outcome == "cancel":
        await runs.cancel_task(first.run.run_id)
    else:
        await runs.finish_mock_run(first.run.run_id, failed=outcome == "failure")
    later = await runs.start_task("b", task("b", request_id="new-request"))
    assert later.run.run_id != first.run.run_id and later.run.status == "running"


@pytest.mark.asyncio
async def test_each_operation_samples_shared_clock_once_for_all_workers():
    calls = []
    runs = manager(clock=lambda: calls.append(1) or 10.0)
    first = await runs.start_task("a", task(task_id="one"))
    assert len(calls) == 1
    second = await runs.start_task("b", task("b", task_id="two"))
    assert len(calls) == 2
    await runs.get_status(first.run.run_id)
    assert len(calls) == 3
    await runs.finish_mock_run(second.run.run_id)
    assert len(calls) == 4


@pytest.mark.asyncio
async def test_timeout_releases_mock_slot_without_automatic_completion():
    now = [10.0]
    runs = manager(global_limit=1, clock=lambda: now[0])
    first = await runs.start_task("a", task(timeout_seconds=1))
    now[0] = 11.0
    later = await runs.start_task("b", task("b", task_id="later"))
    assert later.run.status == "running"
    old = await runs.get_status(first.run.run_id)
    assert old.run.status == "timed_out" and old.run.error_code == "timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), 9.0])
async def test_manager_clock_fault_is_sticky_even_for_worker_never_started(bad):
    now = [10.0]
    runs = manager(clock=lambda: now[0])
    first = await runs.start_task("a", task())
    now[0] = bad
    failed = await runs.get_status(first.run.run_id)
    assert failed.run.status == "failed" and failed.run.error_code == "invalid_clock"
    now[0] = 10.0
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("b", task("b", task_id="new"))
    assert exc.value.code == "invalid_clock"
    assert (await runs.start_task("a", task())).run.run_id == first.run.run_id


@pytest.mark.asyncio
async def test_clock_fault_cannot_overwrite_existing_terminal_result():
    now = [10.0]
    runs = manager(clock=lambda: now[0])
    first = await runs.start_task("a", task(task_id="done"))
    await runs.finish_mock_run(first.run.run_id, output="stable")
    before = await runs.get_result(first.run.run_id)
    second = await runs.start_task("b", task("b", task_id="active"))
    now[0] = float("nan")
    assert (await runs.get_status(second.run.run_id)).run.status == "failed"
    assert await runs.get_result(first.run.run_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["get_status", "get_result", "cancel_task", "finish_mock_run", "resume_task"]
)
async def test_unknown_run_is_static_not_found_without_clock_sample(method):
    calls = []
    runs = manager(clock=lambda: calls.append(1) or 10.0)
    with pytest.raises(AgentSyncError) as exc:
        await getattr(runs, method)("unknown")
    assert exc.value.code == "not_found" and calls == []


@pytest.mark.asyncio
async def test_invalid_start_and_finish_inputs_never_refresh_running_state():
    calls = []
    runs = manager(clock=lambda: calls.append(1) or 10.0)
    first = await runs.start_task("a", task())
    before = len(calls)
    invalid_calls = [
        lambda: runs.start_task("missing", task()),
        lambda: runs.start_task("a", replace(task(), project_id="other-project")),
        lambda: runs.start_task("a", task("b")),
        lambda: runs.finish_mock_run(first.run.run_id, failed=1),
        lambda: runs.finish_mock_run(first.run.run_id, output={}),
    ]
    for invoke in invalid_calls:
        with pytest.raises(AgentSyncError) as exc:
            await invoke()
        assert "other-project" not in exc.value.message and len(calls) == before
    assert (await runs.get_status(first.run.run_id)).run.status == "running"


def test_bounded_strict_configuration_and_distinct_worker_namespaces():
    for options in (
        {"global_limit": True},
        {"per_agent_limit": 1.0},
        {"global_limit": 0},
        {"per_agent_limit": 101},
        {"max_runs": 0},
        {"max_runs": 10001},
    ):
        with pytest.raises(AgentSyncError) as exc:
            manager(**options)
        assert exc.value.code == "validation_error"
    for workers in (
        (),
        (MockWorker("a", "s"), MockWorker("a", "other")),
        (MockWorker("a", "s"), MockWorker("b", "s")),
        tuple(MockWorker(str(i), f"s-{i}") for i in range(33)),
    ):
        with pytest.raises(AgentSyncError):
            MockRunManager("project", workers)


@pytest.mark.asyncio
async def test_managers_do_not_share_routes_or_claim_cross_instance_authority():
    first, other = manager(clock=lambda: 10.0), manager(clock=lambda: 10.0)
    started = await first.start_task("a", task())
    with pytest.raises(AgentSyncError) as exc:
        await other.get_status(started.run.run_id)
    assert exc.value.code == "not_found"
    independently_simulated = await other.start_task("a", task())
    assert independently_simulated.run.run_id != started.run.run_id
    assert await first.get_status(started.run.run_id) == started


@pytest.mark.asyncio
async def test_adapter_deadline_clock_failure_also_latches_manager_fault():
    runs = manager(clock=lambda: float(2**53))
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("a", task(timeout_seconds=1))
    assert exc.value.code == "invalid_clock"
    # A longer deadline is representable but must not let a fresh worker bypass the fault.
    with pytest.raises(AgentSyncError) as exc:
        await runs.start_task("b", task("b", timeout_seconds=4))
    assert exc.value.code == "invalid_clock"

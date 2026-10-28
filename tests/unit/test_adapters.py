"""Mock adapter observations only; no real-client execution or acceptance evidence."""

import asyncio
from dataclasses import FrozenInstanceError, replace

import pytest

from agentsync.adapters import AdapterTask, MockAdapter
from agentsync.errors import AgentSyncError


@pytest.mark.asyncio
async def test_start_and_observe_running_adapter_run():
    adapter = MockAdapter("project", "session", clock=lambda: 10.0)
    task = AdapterTask("project", "session", "task", "request")
    started = await adapter.start_task(task)
    observed = await adapter.get_status(started.run_id)
    assert observed == started
    assert observed.status == "running"
    assert (observed.project_id, observed.session_id, observed.task_id) == (
        "project",
        "session",
        "task",
    )
    assert observed.simulated is True
    assert observed.execution_connected is False
    assert observed.verification == "unverified"


def request(**changes):
    return replace(AdapterTask("project", "session", "task", "request"), **changes)


@pytest.mark.asyncio
async def test_concurrent_duplicate_start_is_one_run():
    adapter = MockAdapter("project", "session")
    runs = await asyncio.gather(*(adapter.start_task(request()) for _ in range(30)))
    assert len({run.run_id for run in runs}) == 1
    with pytest.raises(AgentSyncError) as exc:
        await adapter.start_task(request(instruction="different"))
    assert exc.value.code == "idempotency_conflict"


@pytest.mark.asyncio
async def test_capacity_never_evicts_existing_run_and_allows_replay():
    adapter = MockAdapter("project", "session", max_runs=1)
    first = await adapter.start_task(request())
    with pytest.raises(AgentSyncError) as exc:
        await adapter.start_task(request(request_id="another"))
    assert exc.value.code == "capacity_exceeded"
    assert await adapter.start_task(request()) == first
    assert await adapter.get_status(first.run_id) == first


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"project_id": "other"}, {"session_id": "other"}])
async def test_adapter_namespace_must_match(change):
    adapter = MockAdapter("project", "session")
    with pytest.raises(AgentSyncError) as exc:
        await adapter.start_task(request(**change))
    assert exc.value.code == "namespace_mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [True, False])
async def test_capabilities_honestly_declare_simulation_and_cancel(supported):
    adapter = MockAdapter("project", "session", cancel_supported=supported)
    caps = await adapter.capabilities()
    assert caps.supports_cancel is supported
    assert caps.supports_resume is False and caps.supports_usage is False
    assert caps.simulated and not caps.execution_connected and caps.verification == "unverified"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        caps.supports_resume = True


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_only_explicit_finish_produces_simulated_result(failed):
    adapter = MockAdapter("project", "session")
    run = await adapter.start_task(request())
    ended = await adapter.finish_run(run.run_id, output="explicit mock output", failed=failed)
    result = await adapter.get_result(run.run_id)
    assert ended.status == ("failed" if failed else "succeeded")
    assert ended.error_code == ("mock_failure" if failed else None)
    assert result.output == "explicit mock output" and result.run == ended
    assert (
        result.simulated and not result.execution_connected and result.verification == "unverified"
    )
    assert run.status == "running", "Previously returned immutable snapshots cannot change"
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        result.output = "changed"


@pytest.mark.asyncio
async def test_running_result_is_not_ready_and_cannot_be_forged_as_real():
    adapter = MockAdapter("project", "session")
    run = await adapter.start_task(request())
    with pytest.raises(AgentSyncError) as exc:
        await adapter.get_result(run.run_id)
    assert exc.value.code == "result_not_ready"
    # Supported stdlib versions reject init=False replacement with either type.
    with pytest.raises((TypeError, ValueError)):
        replace(run, execution_connected=True)
    assert run.execution_connected is False
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        run.status = "succeeded"


@pytest.mark.asyncio
async def test_cancel_cannot_be_overwritten_by_late_finish():
    adapter = MockAdapter("project", "session")
    run = await adapter.start_task(request())
    cancelled = await adapter.cancel_task(run.run_id)
    assert cancelled.status == "cancelled"
    with pytest.raises(AgentSyncError) as exc:
        await adapter.finish_run(run.run_id, output="late")
    assert exc.value.code == "invalid_state"
    result = await adapter.get_result(run.run_id)
    assert result.run == cancelled and result.output == ""


@pytest.mark.asyncio
async def test_unsupported_cancel_and_resume_do_not_change_run():
    adapter = MockAdapter("project", "session", cancel_supported=False, clock=lambda: 10.0)
    run = await adapter.start_task(request())
    for method in (adapter.cancel_task, adapter.resume_task):
        with pytest.raises(AgentSyncError) as exc:
            await method(run.run_id)
        assert exc.value.code == "unsupported"
    assert await adapter.get_status(run.run_id) == run


@pytest.mark.asyncio
async def test_finish_cancel_race_has_one_terminal_winner():
    adapter = MockAdapter("project", "session")
    run = await adapter.start_task(request())
    attempts = await asyncio.gather(
        adapter.finish_run(run.run_id, output="finished"),
        adapter.cancel_task(run.run_id),
        return_exceptions=True,
    )
    assert sum(isinstance(item, AgentSyncError) for item in attempts) == 1
    final = await adapter.get_status(run.run_id)
    assert final.status in {"succeeded", "cancelled"}
    assert (await adapter.get_result(run.run_id)).run == final


@pytest.mark.asyncio
async def test_observing_clock_only_times_out_never_completes():
    clock = [10.0]
    adapter = MockAdapter("project", "session", clock=lambda: clock[0])
    run = await adapter.start_task(request(timeout_seconds=2))
    clock[0] = 11.0
    assert (await adapter.get_status(run.run_id)).status == "running"
    clock[0] = 12.0
    expired = await adapter.get_status(run.run_id)
    assert expired.status == "timed_out" and expired.timed_out
    assert expired.error_code == "timeout" and expired.finished_at == 12.0
    assert (await adapter.get_result(run.run_id)).run == expired
    with pytest.raises(AgentSyncError):
        await adapter.finish_run(run.run_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_clock", [float("nan"), float("inf"), 9.0, True, "bad"])
async def test_invalid_or_regressed_clock_fails_closed(bad_clock):
    clock = [10.0]
    adapter = MockAdapter("project", "session", clock=lambda: clock[0])
    run = await adapter.start_task(request())
    clock[0] = bad_clock
    failed = await adapter.get_status(run.run_id)
    assert failed.status == "failed" and failed.finished_at == 10.0
    expected = "clock_regressed" if bad_clock == 9.0 else "invalid_clock"
    assert failed.error_code == expected
    assert (await adapter.get_result(run.run_id)).run == failed
    with pytest.raises(AgentSyncError) as exc:
        await adapter.start_task(request(request_id="new"))
    assert exc.value.code == expected


@pytest.mark.parametrize(
    "change",
    [
        {"project_id": True},
        {"task_id": ""},
        {"request_id": "x" * 201},
        {"instruction": {}},
        {"instruction": "private" * 3000},
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": "300"},
    ],
)
def test_invalid_task_inputs_have_static_safe_errors(change):
    with pytest.raises(AgentSyncError) as exc:
        request(**change)
    assert exc.value.code == "validation_error"
    assert "private" not in exc.value.message


def test_invalid_configuration_is_rejected():
    for options in (
        {"max_runs": True},
        {"max_runs": 0},
        {"max_runs": 1.0},
        {"cancel_supported": 1},
    ):
        with pytest.raises(AgentSyncError) as exc:
            MockAdapter("project", "session", **options)
        assert exc.value.code == "validation_error"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_status", "get_result", "cancel_task", "resume_task"])
async def test_unknown_run_returns_not_found(method):
    adapter = MockAdapter("project", "session")
    with pytest.raises(AgentSyncError) as exc:
        await getattr(adapter, method)("unknown")
    assert exc.value.code == "not_found"


@pytest.mark.asyncio
async def test_separate_mock_instances_do_not_share_runs_or_authorize_core_access():
    first = MockAdapter("project", "session", clock=lambda: 10.0)
    other = MockAdapter("other-project", "other-session")
    run = await first.start_task(request())
    for method in (other.get_status, other.get_result, other.cancel_task, other.finish_run):
        with pytest.raises(AgentSyncError) as exc:
            await method(run.run_id)
        assert exc.value.code == "not_found"
    assert await first.get_status(run.run_id) == run


@pytest.mark.asyncio
async def test_finish_controls_reject_bad_types_and_keep_running():
    adapter = MockAdapter("project", "session", clock=lambda: 10.0)
    run = await adapter.start_task(request())
    for options in ({"failed": 1}, {"output": {}}, {"output": "x" * 65537}):
        with pytest.raises(AgentSyncError) as exc:
            await adapter.finish_run(run.run_id, **options)
        assert exc.value.code == "validation_error"
    assert await adapter.get_status(run.run_id) == run


def test_timeout_bounds_and_invalid_unicode_are_rejected():
    for value in (0, -1, 7201, float("inf"), 10**1000):
        with pytest.raises(AgentSyncError):
            request(timeout_seconds=value)
    for value in ("\x00", "\ud800", " " * 2):
        with pytest.raises(AgentSyncError):
            request(task_id=value)

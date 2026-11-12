"""Synthetic execution-budget coverage without any real client or provider."""

import asyncio
from types import SimpleNamespace

import pytest

from agentsync.adapters.approved_launch import ApprovedLaunchFactory
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor_invocation import CursorHostProfile
from agentsync.adapters.launch_context import _new_launch_context
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue


async def test_drain_budget_interrupts_the_current_wave_without_starting_another(monkeypatch):
    queue = object.__new__(RelayQueue)
    actor = SimpleNamespace(profile=SimpleNamespace(project_id="fixture-project"))
    items = (SimpleNamespace(first=actor),)
    deadlines = []
    interrupted = False

    async def wait_for_stop(_items, **options):
        nonlocal interrupted
        deadlines.append(options["_execution_deadline"])
        try:
            await asyncio.Event().wait()
        finally:
            interrupted = True

    monkeypatch.setattr(queue, "_validate_items", lambda supplied, _limit: supplied)
    monkeypatch.setattr(queue, "run_ready_once", wait_for_stop)
    result = await queue.drain_ready(
        items,
        request_id="fixture-request",
        admin_token="unused-fixture-token",
        max_waves=2,
        execution_budget_seconds=0.1,
    )
    assert result.reason == "execution_limit"
    assert result.waves == ()
    assert result.verification == "unverified"
    assert interrupted
    assert len(deadlines) == 1 and deadlines[0] is not None


async def test_expired_relay_budget_prevents_launch_preparation_and_reservation(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    profile = CursorHostProfile("project", "session", root / "unused.exe", root, "0" * 64, "fixture")
    task = AdapterTask("project", "session", "task", "request", "fixture")
    loop = asyncio.get_running_loop()
    context = _new_launch_context(task, loop, loop.time() + 30, lambda: False)

    def unexpected(*_args):
        pytest.fail("An expired relay budget must prevent preparation and launch")

    factory = ApprovedLaunchFactory(
        profile, environment={}, receipts=root, authority=unexpected, revalidate=unexpected,
        _execution_deadline=loop.time() - 1,
    )
    monkeypatch.setattr(factory, "_review", unexpected)
    with pytest.raises(AgentSyncError) as refused:
        await factory(task, context)
    assert refused.value.code == "relay_execution_limit"
    assert list(root.iterdir()) == []

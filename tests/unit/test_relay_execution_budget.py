"""Synthetic execution-budget coverage without any real client or provider."""

import asyncio
from types import SimpleNamespace

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

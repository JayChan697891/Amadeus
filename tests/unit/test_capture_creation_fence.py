"""Same-tick capture ownership fixtures, never real-client or auth evidence."""

import asyncio
from queue import Queue
from threading import Thread

import pytest
from test_claude_adapter import factory_for as claude_factory
from test_codex_adapter import factory_for as codex_factory
from test_cursor_adapter import factory_for as cursor_factory

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude import ClaudeAdapter
from agentsync.adapters.codex import CodexAdapter
from agentsync.adapters.cursor import CursorAdapter
from agentsync.adapters.process_capture import CapturedProcess

_CLIENTS = [
    (CodexAdapter, codex_factory),
    (ClaudeAdapter, claude_factory),
    (CursorAdapter, cursor_factory),
]


async def terminal(adapter, run_id):
    async with asyncio.timeout(7):
        while True:
            observed = await adapter.get_status(run_id)
            if observed.status not in {"starting", "running"}:
                return observed
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("adapter_type,make_capture", _CLIENTS, ids=["codex", "claude", "cursor"])
@pytest.mark.parametrize("preexisting", [False, True], ids=["fresh", "preexisting"])
@pytest.mark.asyncio
async def test_equal_public_timestamps_do_not_replace_capture_creation_order(
    tmp_path,
    adapter_type,
    make_capture,
    preexisting,
):
    request = AdapterTask("p", "s", "task", "request")
    release = asyncio.Event()
    captures = []
    if preexisting:
        captures.append(await make_capture(tmp_path, delay=5)(request))

    async def factory(task):
        await release.wait()
        if not preexisting:
            captures.append(await make_capture(tmp_path)(task))
        capture = captures[0]
        # Only the stored observation changes; the real loop clock/timers run normally.
        capture._started = begun.started_at
        return capture

    adapter = adapter_type("p", "s", factory=factory)
    try:
        begun = await adapter.start_task(request)
        release.set()
        observed = await terminal(adapter, begun.run_id)
        assert (await captures[0].snapshot()).started_at == begun.started_at
        if preexisting:
            assert observed.status == "unknown" and observed.error_code == "capture_stale"
            assert observed.slot_held and observed.capture_id is None
            assert adapter._entries[begun.run_id].process is None
            assert adapter._capture_owners == {}
            await adapter.cancel_task(begun.run_id)
            unowned = await captures[0].snapshot()
            assert unowned.state == "running" and not unowned.parent_ended
        else:
            assert observed.status == "succeeded" and observed.exit_code == 0
            assert observed.parent_ended and not observed.slot_held
            assert observed.capture_id == (await captures[0].snapshot()).capture_id
            assert (await adapter.start_task(request)).run_id == begun.run_id
            result = await adapter.get_result(begun.run_id)
            assert result.real_client_verified is False and result.verification == "unverified"
    finally:
        release.set()
        for capture in captures:
            await capture.cancel()


@pytest.mark.asyncio
async def test_newer_foreign_loop_capture_is_rejected_without_ownership_or_stopping_it():
    queue = Queue()
    cleanup = []
    release_factory = asyncio.Event()

    def foreign_thread():
        async def own():
            capture = CapturedProcess()
            stop = asyncio.Event()
            queue.put((capture, asyncio.get_running_loop(), stop))
            await stop.wait()
            cleanup.append(await capture.cancel())

        asyncio.run(own())

    thread = Thread(target=foreign_thread, daemon=True)
    foreign = None

    async def factory(_task):
        nonlocal foreign
        await release_factory.wait()
        thread.start()
        foreign = await asyncio.to_thread(queue.get, True, 3)
        capture = foreign[0]
        # A later timestamp alone must not permit cross-loop ownership.
        capture._started = begun.started_at + 1
        return capture

    adapter = CodexAdapter("p", "s", factory=factory)
    try:
        begun = await adapter.start_task(AdapterTask("p", "s", "task", "request"))
        release_factory.set()
        observed = await terminal(adapter, begun.run_id)
        assert observed.status == "unknown" and observed.error_code == "capture_stale"
        assert observed.slot_held and observed.capture_id is None
        assert adapter._entries[begun.run_id].process is None
        assert adapter._capture_owners == {}
        capture = foreign[0]
        assert not capture._done.done() and capture._reason is None
        await adapter.cancel_task(begun.run_id)
        assert not capture._done.done() and capture._reason is None
    finally:
        if foreign is not None:
            foreign[1].call_soon_threadsafe(foreign[2].set)
        if thread.ident is not None:
            await asyncio.to_thread(thread.join, 3)
            assert not thread.is_alive()
    assert cleanup[0].error_code == "capture_not_started"

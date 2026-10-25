"""Controlled factory-delay cancellation, not an actual OS launch-timeout claim.

The public event-loop subprocess factory is gated before delegating to its real
implementation. Only one known, self-ending local Python helper may be spawned.
No real Agent client, sandbox, child tree or external service is exercised.
"""

import asyncio
import sys

import pytest

from agentsync.adapters.process_capture import CapturedProcess


@pytest.mark.asyncio
async def test_caller_cancel_during_delayed_factory_stops_later_owned_parent(tmp_path, monkeypatch):
    loop = asyncio.get_running_loop()
    original_factory = loop.subprocess_exec
    factory_entered = asyncio.Event()
    allow_launch = asyncio.Event()
    transport_returned = asyncio.Event()
    owned_transports = []
    factory_calls = []

    async def delayed_factory(protocol_factory, *args, **kwargs):
        factory_calls.append(args)
        factory_entered.set()
        await allow_launch.wait()
        transport, protocol = await original_factory(protocol_factory, *args, **kwargs)
        owned_transports.append(transport)
        transport_returned.set()
        return transport, protocol

    monkeypatch.setattr(loop, "subprocess_exec", delayed_factory)
    argv = (sys.executable, "-I", "-u", "-c", "import time; time.sleep(2)")
    caller = asyncio.create_task(
        CapturedProcess.start(
            argv, cwd=tmp_path, stdin_text="literal fixture input", timeout_seconds=10
        )
    )
    try:
        await asyncio.wait_for(factory_entered.wait(), timeout=5)
        # Cancellation occurs while the public factory has been entered but no
        # process is launched. The shielded launch later owns its exact handle.
        assert not owned_transports
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        allow_launch.set()
        await asyncio.wait_for(transport_returned.wait(), timeout=5)
        transport = owned_transports[0]
        assert transport.get_pid() > 0
        async with asyncio.timeout(1):
            while transport.get_returncode() is None:
                await asyncio.sleep(0.01)
        # This helper would otherwise end normally after two seconds. A
        # nonzero exit confirms the delayed cancellation stopped this parent.
        assert transport.get_returncode() != 0
        await asyncio.sleep(0.05)
        assert factory_calls == [argv]
        assert len(owned_transports) == 1
    finally:
        allow_launch.set()
        if not caller.done():
            caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
        if factory_entered.is_set() and not transport_returned.is_set():
            try:
                await asyncio.wait_for(transport_returned.wait(), timeout=5)
            except TimeoutError:
                pass  # No returned parent handle is claimed or discovered.
        # Cleanup uses only a transport returned by this test's known factory;
        # no PID discovery or unrelated process termination is allowed.
        for transport in owned_transports:
            if transport.get_returncode() is None:
                transport.kill()
                async with asyncio.timeout(3):
                    while transport.get_returncode() is None:
                        await asyncio.sleep(0.01)
            transport.close()

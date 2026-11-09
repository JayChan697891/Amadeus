"""Adapter-local launch observations, never permission or persistent reservation.

A context consumes one attempt before process capture is entered. The check is
cooperative: OS creation already scheduled can finish after cancellation. Keep
the issuing event loop alive for the adapter's existing late-parent cleanup.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.process_capture import CapturedProcess
from agentsync.errors import AgentSyncError

_T = TypeVar("_T")


class _LaunchBlocked(AgentSyncError):
    def __init__(self, *, expired: bool = False) -> None:
        super().__init__(
            "launch_deadline_exceeded" if expired else "launch_stopped",
            "Local launch observation prevents this attempt.",
            409,
        )
        self.expired = expired


class LaunchContext:
    """Issued to one trusted factory/task/run/loop; it grants no authorization.

    Do not construct or serialize these objects. Python-private construction is
    an API convention, not a boundary against arbitrary trusted host code.
    """

    __slots__ = ("_task", "_loop", "_deadline", "_stopped", "_attempted")
    _task: AdapterTask
    _loop: asyncio.AbstractEventLoop
    _deadline: float
    _stopped: Callable[[], bool]
    _attempted: bool

    def __init__(self) -> None:
        raise AgentSyncError("validation_error", "Adapter-issued launch context required.")

    def check(self, task: AdapterTask) -> None:
        """Observe exact task, loop, stop and deadline without consuming a start."""
        if (
            type(task) is not AdapterTask
            or task != self._task
            or asyncio.get_running_loop() is not self._loop
        ):
            raise AgentSyncError("validation_error", "Invalid launch context association.")
        if self._attempted or self._stopped():
            raise _LaunchBlocked()
        if self._loop.time() >= self._deadline:
            raise _LaunchBlocked(expired=True)

    async def wait_before_start(self, task: AdapterTask, wait: Callable[[], Awaitable[_T]]) -> _T:
        """Bound a cooperative host wait by the same deadline as process admission."""
        self.check(task)
        deadline = asyncio.timeout_at(self._deadline)
        try:
            async with deadline:
                value = await wait()
        except TimeoutError:
            if deadline.expired():
                raise _LaunchBlocked(expired=True) from None
            raise
        if deadline.expired():
            # Even a callback that handled its cancellation cannot supply a late grant.
            raise _LaunchBlocked(expired=True)
        self.check(task)
        return value

    async def start(
        self,
        task: AdapterTask,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        stdin_text: str,
        timeout_seconds: float,
        output_limit: int,
        env: dict[str, str],
    ) -> CapturedProcess:
        self.check(task)
        # No await between the observation, consumption and capture entry.
        # Failures consume the attempt too; this is not a retry/approval ledger.
        self._attempted = True
        if type(env) is not dict:
            raise AgentSyncError("validation_error", "Explicit launch environment required.")
        return await CapturedProcess.start(
            argv,
            cwd=cwd,
            stdin_text=stdin_text,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
            env=env,
        )


def _new_launch_context(
    task: AdapterTask,
    loop: asyncio.AbstractEventLoop,
    deadline: float,
    stopped: Callable[[], bool],
) -> LaunchContext:
    context = object.__new__(LaunchContext)
    context._task = task
    context._loop = loop
    context._deadline = deadline
    context._stopped = stopped
    context._attempted = False
    return context

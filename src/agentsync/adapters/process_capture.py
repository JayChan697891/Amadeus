"""Trusted-host parent-process observation, not a sandbox or a client adapter.

Arguments must come from trusted host code, never model/tool/task text. This
module grants no execution authorization and has no Core or client integration.
Only the owned parent handle is stopped; descendants and tree cleanup remain
unverified. Results contain private caller data and must not be logged blindly.
An explicit child environment selects values only; it is not a sandbox or a
credential-isolation guarantee. The default still inherits the host environment.
Use one subprocess-capable asyncio event loop and keep it alive through wait or
cancel. Parent exit with unavailable pipe EOF becomes capture_incomplete after
0.25 seconds; unconfirmed parent termination becomes unknown after two seconds.
These are observation limits, never evidence that descendants have stopped.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from threading import Lock
from typing import Literal, TypedDict, cast

from agentsync.errors import AgentSyncError

_CREATION_ORDER = count()
_CREATION_LOCK = Lock()


def _next_creation_order() -> int:
    """Process-local ordering only, never authentication or restart identity."""
    with _CREATION_LOCK:
        return next(_CREATION_ORDER)


class _EnvironmentArgs(TypedDict, total=False):
    env: dict[str, str]


def _text(value: object, maximum: int) -> bytes:
    if type(value) is not str or "\x00" in value:
        raise AgentSyncError("validation_error", "Invalid process capture input.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise AgentSyncError("validation_error", "Invalid process capture input.") from None
    if len(encoded) > maximum:
        raise AgentSyncError("validation_error", "Invalid process capture input.")
    return encoded


def _validate(
    argv: tuple[str, ...], cwd: Path, stdin_text: str, timeout: float, limit: int
) -> bytes:
    invalid = AgentSyncError("validation_error", "Invalid process capture input.")
    if type(argv) is not tuple or not 1 <= len(argv) <= 64:
        raise invalid
    encoded_args = [_text(argument, 4096) for argument in argv]
    if not argv[0].strip() or sum(map(len, encoded_args)) > 32768:
        raise invalid
    if not isinstance(cwd, Path):
        raise invalid
    _text(str(cwd), 4096)
    try:
        if not cwd.is_absolute() or not cwd.is_dir():
            raise invalid
    except (OSError, ValueError):
        raise invalid from None
    try:
        valid_timeout = (
            type(timeout) in {int, float} and math.isfinite(timeout) and 0.1 <= timeout <= 300
        )
    except (OverflowError, ValueError):
        valid_timeout = False
    if not valid_timeout or type(limit) is not int or not 1 <= limit <= 1024 * 1024:
        raise invalid
    return _text(stdin_text, 16384)


def _copy_environment(env: dict[str, str] | None) -> dict[str, str] | None:
    if env is None:
        return None
    if type(env) is not dict or len(env) > 256:
        raise AgentSyncError("validation_error", "Invalid process capture input.")
    copied: dict[str, str] = {}
    total = 0
    for name, value in env.items():
        encoded_name = _text(name, 256)
        encoded_value = _text(value, 16384)
        if not name or "=" in name:
            raise AgentSyncError("validation_error", "Invalid process capture input.")
        total += len(encoded_name) + len(encoded_value) + 2
        if total > 65536:
            raise AgentSyncError("validation_error", "Invalid process capture input.")
        copied[name] = value
    return copied


CaptureState = Literal[
    "running",
    "exited",
    "failed_to_start",
    "cancelled",
    "timed_out",
    "output_limit",
    "capture_incomplete",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class CaptureSnapshot:
    capture_id: str
    state: CaptureState
    exit_code: int | None
    started_at: float
    deadline_at: float
    finished_at: float | None
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    parent_ended: bool
    error_code: str | None
    termination_scope: Literal["parent_only"] = field(default="parent_only", init=False)
    tree_cleanup: Literal["unverified"] = field(default="unverified", init=False)
    sandbox: Literal[False] = field(default=False, init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class CaptureResult:
    snapshot: CaptureSnapshot
    stdout: bytes = field(repr=False)
    stderr: bytes = field(repr=False)


class _Protocol(asyncio.SubprocessProtocol):
    def __init__(self, owner: CapturedProcess) -> None:
        self.owner = owner

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.owner._transport = cast(asyncio.SubprocessTransport, transport)

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        self.owner._data(fd, data)

    def pipe_connection_lost(self, fd: int, exc: Exception | None) -> None:
        self.owner._closed.add(fd)
        if fd in {1, 2} and exc is not None:
            self.owner._capture_broken = True
            self.owner._stop("unknown")
        self.owner._maybe_finish()

    def process_exited(self) -> None:
        self.owner._parent_ended = True
        self.owner._maybe_finish()


class CapturedProcess:
    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._creation_order = _next_creation_order()
        self._id = uuid.uuid4().hex
        self._state: CaptureState = "running"
        self._transport: asyncio.SubprocessTransport | None = None
        self._started = self._loop.time()
        self._deadline = self._started + 3
        self._finished: float | None = None
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._closed: set[int] = set()
        self._parent_ended = False
        self._done: asyncio.Future[CaptureSnapshot] = self._loop.create_future()
        self._limit = 1024 * 1024
        self._truncated: set[int] = set()
        self._reason: CaptureState | None = None
        self._error: str | None = None
        self._capture_broken = False
        self._timer: asyncio.TimerHandle | None = None
        self._grace: asyncio.TimerHandle | None = None
        self._kill_confirmation: asyncio.TimerHandle | None = None
        self._spawn_task: asyncio.Task[None] | None = None

    def _created_after(self, fence: int) -> bool:
        """Check local construction order and loop association, not timestamps."""
        return self._creation_order > fence and self._loop is asyncio.get_running_loop()

    @classmethod
    async def start(
        cls,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        stdin_text: str,
        timeout_seconds: float,
        output_limit: int = 1024 * 1024,
        env: dict[str, str] | None = None,
    ) -> CapturedProcess:
        """Start only trusted argv; stdin is data, never a command or script.

        Each stream retains at most output_limit bytes (two independent caps).
        A supported event loop with subprocess support is required. This method
        does not restrict child access. env=None inherits the host environment;
        an explicit strict dict is bounded and copied before the first await.
        """
        encoded_stdin = _validate(argv, cwd, stdin_text, timeout_seconds, output_limit)
        environment = _copy_environment(env)
        owner = cls()
        owner._deadline = owner._started + timeout_seconds
        owner._limit = output_limit
        owner._timer = owner._loop.call_later(timeout_seconds, owner._stop, "timed_out")
        owner._spawn_task = asyncio.create_task(owner._spawn(argv, cwd, encoded_stdin, environment))
        try:
            await asyncio.shield(owner._spawn_task)
        except asyncio.CancelledError:
            owner._stop("cancelled")
            raise
        return owner

    async def _spawn(
        self,
        argv: tuple[str, ...],
        cwd: Path,
        encoded_stdin: bytes,
        environment: dict[str, str] | None,
    ) -> None:
        # Preserve the original inherited-environment call when env is omitted.
        environment_args: _EnvironmentArgs = {} if environment is None else {"env": environment}
        try:
            transport, _ = await self._loop.subprocess_exec(
                lambda: _Protocol(self),
                *argv,
                cwd=str(cwd),
                stdin=-1,
                stdout=-1,
                stderr=-1,
                **environment_args,
            )
        except (OSError, ValueError, RuntimeError):
            self._finish("failed_to_start", "spawn_failed")
            return
        stdin = cast(asyncio.WriteTransport | None, transport.get_pipe_transport(0))
        if stdin is not None:
            try:
                stdin.write(encoded_stdin)
                stdin.close()
            except (OSError, RuntimeError):
                # An already-exited/non-reading parent can close stdin normally.
                stdin.close()
        if self._reason is not None:
            self._kill_parent()

    def _data(self, fd: int, data: bytes) -> None:
        if self._done.done() or fd not in {1, 2}:
            return
        target = self._stdout if fd == 1 else self._stderr
        remaining = self._limit - len(target)
        target.extend(data[:remaining])
        if len(data) > remaining:
            self._truncated.add(fd)
            self._stop("output_limit")

    def _maybe_finish(self) -> None:
        if self._done.done() or not self._parent_ended:
            return
        if {1, 2} <= self._closed:
            if self._capture_broken:
                self._finish("capture_incomplete", "capture_incomplete")
            else:
                self._finish(self._reason or "exited", self._error)
        elif self._grace is None:
            # Descendants can inherit pipes. Only wait a bounded interval after
            # the owned parent ends; closing our pipes does not stop descendants.
            self._grace = self._loop.call_later(
                0.25, self._finish, "capture_incomplete", "capture_incomplete"
            )

    def _stop(self, reason: CaptureState) -> None:
        if self._done.done():
            return
        if self._transport is not None and self._transport.get_returncode() is not None:
            self._parent_ended = True
        if self._parent_ended and reason != "output_limit":
            self._maybe_finish()
            return
        if self._reason is None:
            self._reason = reason
            self._error = reason
        self._kill_parent()

    def _kill_parent(self) -> None:
        if self._transport is None or self._parent_ended or self._done.done():
            return
        try:
            self._transport.kill()
        except ProcessLookupError:
            pass  # Exit callback may already be queued.
        except (OSError, RuntimeError):
            self._finish("unknown", "parent_termination_unconfirmed")
            return
        if self._kill_confirmation is None:
            self._kill_confirmation = self._loop.call_later(
                2, self._finish, "unknown", "parent_termination_unconfirmed"
            )

    def _finish(self, state: CaptureState, error: str | None) -> None:
        if self._done.done():
            return
        self._state, self._error = state, error
        self._finished = self._loop.time()
        for timer in (self._timer, self._grace, self._kill_confirmation):
            if timer is not None:
                timer.cancel()
        self._done.set_result(self._view())
        if self._transport is not None:
            try:
                self._transport.close()
            except (OSError, RuntimeError):
                # Closing our handles is best effort. A frozen terminal result
                # never upgrades unconfirmed parent/tree cleanup afterwards.
                pass

    def _view(self) -> CaptureSnapshot:
        if self._done.done():
            return self._done.result()
        return CaptureSnapshot(
            self._id,
            self._state,
            self._transport.get_returncode() if self._transport else None,
            self._started,
            self._deadline,
            self._finished,
            len(self._stdout),
            len(self._stderr),
            1 in self._truncated,
            2 in self._truncated,
            self._parent_ended,
            self._error,
        )

    async def snapshot(self) -> CaptureSnapshot:
        return self._view()

    async def wait(self) -> CaptureSnapshot:
        return await asyncio.shield(self._done)

    async def get_result(self) -> CaptureResult:
        if not self._done.done():
            raise AgentSyncError("result_not_ready", "Process result is not ready.", 409)
        return CaptureResult(self._done.result(), bytes(self._stdout), bytes(self._stderr))

    async def cancel(self) -> CaptureSnapshot:
        if self._spawn_task is None and self._transport is None:
            # A trusted factory can accidentally return the public constructor
            # without start(). There is no parent or future spawn to observe.
            # Freeze uncertainty instead of awaiting an event that cannot arrive.
            self._finish("unknown", "capture_not_started")
        else:
            self._stop("cancelled")
        return await asyncio.shield(self._done)

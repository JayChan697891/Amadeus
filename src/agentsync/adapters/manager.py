"""Instance-local routing for trusted adapters; no scheduling or Core authorization.

Use one asyncio loop. Registration and lifetime history are bounded and immutable;
there is no eviction, restart recovery, automatic retry, or cross-instance dedup.
A dispatched start owns its history slot even if it raises, hangs, or its caller
cancels. The loop must remain alive for outstanding starts. Adapter timeouts and
cleanup remain the adapter's responsibility. Raw observations retain their own
markers: this router makes no success, verification, or authorization claims.
Hosts may bound pending starts and active managed routes without a waiting queue.
With an active limit, unobserved or uncertain runs keep their slot. A released slot
does not establish descendant or remote process cleanup.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Generic, Literal, Protocol, TypeVar, cast

from agentsync.adapters._host_process import _HostRun
from agentsync.adapters.base import AdapterTask, AgentAdapter, RunSnapshot, _identifier
from agentsync.errors import AgentSyncError


class AdapterRun(Protocol):
    @property
    def project_id(self) -> str: ...

    @property
    def session_id(self) -> str: ...

    @property
    def task_id(self) -> str: ...

    @property
    def request_id(self) -> str: ...

    @property
    def run_id(self) -> str: ...


C = TypeVar("C")
R = TypeVar("R", bound=AdapterRun)
T = TypeVar("T")
U = TypeVar("U")

_OPERATION_ERRORS = {
    "unsupported": ("Operation is unsupported by this adapter.", 400),
    "not_found": ("Adapter run was not found.", 404),
    "result_not_ready": ("Adapter result is not ready.", 409),
    "invalid_state": ("Adapter run is in an invalid state.", 409),
    "invalid_adapter_run": ("Adapter returned an inconsistent run.", 409),
    "namespace_mismatch": ("Request does not match adapter namespace.", 403),
    "capacity_exceeded": ("Adapter capacity is exhausted.", 409),
    "history_capacity_exceeded": ("Adapter history capacity is exhausted.", 409),
    "running_capacity_exceeded": ("Adapter running capacity is exhausted.", 409),
    "task_already_active": ("Task already has an active adapter run.", 409),
    "idempotency_conflict": ("Request ID has different inputs.", 409),
    "validation_error": ("Invalid adapter input.", 400),
}


def _raise_pending_cancellation() -> None:
    # An uncleared request prevents adapter entry, even if its original exception
    # was swallowed. The count is policy, not proof of an exception's origin.
    # Fresh errors raised outside handlers cannot retain private adapter details.
    caller = asyncio.current_task()
    if caller is not None and caller.cancelling():
        raise asyncio.CancelledError()


async def _call_adapter(callback: Callable[[], Awaitable[U]]) -> U:
    _raise_pending_cancellation()
    code = "adapter_operation_unknown"
    try:
        value = await callback()
    except AgentSyncError as error:
        public_code = vars(error).get("code")
        if type(public_code) is str and public_code in _OPERATION_ERRORS:
            code = public_code
    except (Exception, asyncio.CancelledError):
        pass
    else:
        _raise_pending_cancellation()
        return value
    # Raise outside the handlers so the public error retains no private context.
    _raise_pending_cancellation()
    message, status = _OPERATION_ERRORS.get(code, ("Adapter operation did not complete.", 409))
    raise AgentSyncError(code, message, status)


@dataclass(frozen=True, slots=True)
class ManagedRun(Generic[R]):
    handle: str
    adapter_id: str
    run: R = field(repr=False)


@dataclass(frozen=True, slots=True)
class DispatchSnapshot:
    handle: str
    adapter_id: str
    project_id: str
    session_id: str
    task_id: str
    request_id: str
    state: Literal["pending", "returned", "error"]
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ManagerCapacity:
    history: int
    history_limit: int
    pending_starts: int
    pending_start_limit: int | None
    held_active_slots: int | None
    active_limit: int | None


@dataclass(frozen=True, slots=True)
class CancellationObservation(Generic[R]):
    handle: str
    state: Literal["start_unresolved", "start_error", "unsupported", "cancel_unresolved", "returned"]
    run: ManagedRun[R] | None = field(default=None, repr=False)
    error_code: str | None = None
    cleanup_verified: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _StartResult(Generic[R]):
    run: R | None = field(default=None, repr=False)
    run_id: str | None = field(default=None, repr=False)
    error_code: str | None = None


@dataclass(slots=True)
class _Route(Generic[R]):
    handle: str
    adapter_id: str
    task: AdapterTask = field(repr=False)
    start: asyncio.Task[_StartResult[R]] = field(repr=False)
    resume_epoch: int = 0
    resuming: bool = False


class RunManager(Generic[C, R, T]):
    def __init__(
        self,
        project_id: str,
        session_id: str,
        adapters: Mapping[str, AgentAdapter[C, R, T]],
        *,
        max_runs: int = 100,
        max_pending_starts: int | None = None,
        max_active_runs: int | None = None,
    ) -> None:
        _identifier(project_id)
        _identifier(session_id)
        if type(max_runs) is not int or not 1 <= max_runs <= 10000:
            raise AgentSyncError("validation_error", "Invalid manager capacity.")
        if max_pending_starts is not None and (
            type(max_pending_starts) is not int or not 1 <= max_pending_starts <= max_runs
        ):
            raise AgentSyncError("validation_error", "Invalid pending start capacity.")
        if max_active_runs is not None and (
            type(max_active_runs) is not int or not 1 <= max_active_runs <= max_runs
        ):
            raise AgentSyncError("validation_error", "Invalid active run capacity.")
        if not isinstance(adapters, Mapping) or not 1 <= len(adapters) <= 32:
            raise AgentSyncError("validation_error", "Invalid adapter registration.")
        self._adapters = dict(adapters)
        for name, adapter in self._adapters.items():
            _identifier(name)
            if not isinstance(adapter, AgentAdapter):
                raise AgentSyncError("validation_error", "Invalid adapter registration.")
        self._project_id, self._session_id = project_id, session_id
        self._max_runs = max_runs
        self._max_pending_starts = max_pending_starts
        self._max_active_runs = max_active_runs
        self._active_handles: set[str] = set()
        self._lock = asyncio.Lock()
        self._routes: dict[str, _Route[R]] = {}
        self._requests: dict[str, _Route[R]] = {}

    def history(self) -> tuple[str, ...]:
        """Opaque handles in dispatch order, including unresolved/failed starts."""
        return tuple(self._routes)

    def capacity(self) -> ManagerCapacity:
        """Read instance capacity without calling adapters or starting work."""
        return ManagerCapacity(
            history=len(self._routes),
            history_limit=self._max_runs,
            pending_starts=self._pending_start_count(),
            pending_start_limit=self._max_pending_starts,
            held_active_slots=None if self._max_active_runs is None else len(self._active_handles),
            active_limit=self._max_active_runs,
        )

    def _pending_start_count(self) -> int:
        return sum(not route.start.done() for route in self._routes.values())

    def get_dispatch(self, handle: str) -> DispatchSnapshot:
        """Inspect without waiting; returned means a start receipt, never run success."""
        _identifier(handle)
        route = self._routes.get(handle)
        if route is None:
            raise AgentSyncError("not_found", "Manager run does not exist.", 404)
        state: Literal["pending", "returned", "error"] = "pending"
        error_code = None
        if route.start.done():
            if route.start.cancelled():
                state, error_code = "error", "adapter_start_unknown"
            else:
                outcome = route.start.result()
                if outcome.run is None:
                    state, error_code = "error", outcome.error_code or "adapter_start_unknown"
                else:
                    state = "returned"
        return DispatchSnapshot(
            handle,
            route.adapter_id,
            route.task.project_id,
            route.task.session_id,
            route.task.task_id,
            route.task.request_id,
            state,
            error_code,
        )

    def _adapter(self, adapter_id: str) -> AgentAdapter[C, R, T]:
        _identifier(adapter_id)
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise AgentSyncError("not_found", "Adapter is not registered.", 404)
        return adapter

    async def wait_dispatch(self, handle: str, *, timeout_seconds: float) -> DispatchSnapshot:
        """Observe an existing start for up to 300 seconds, without starting more work.

        This observation timeout neither limits adapter execution nor grants permission.
        Timeout or caller cancellation leaves the dispatched start running; a returned
        receipt never establishes run success.
        """
        if type(timeout_seconds) not in (int, float) or not 0 <= timeout_seconds <= 300:
            raise AgentSyncError("validation_error", "Invalid dispatch observation timeout.")
        snapshot = self.get_dispatch(handle)
        if snapshot.state == "pending" and timeout_seconds > 0:
            # asyncio.wait does not cancel its input task on timeout or caller cancellation.
            await asyncio.wait((self._routes[handle].start,), timeout=timeout_seconds)
        return self.get_dispatch(handle)

    async def capabilities(self, adapter_id: str) -> C:
        adapter = self._adapter(adapter_id)
        return await _call_adapter(lambda: adapter.capabilities())

    async def start_task(self, adapter_id: str, task: AdapterTask) -> ManagedRun[R]:
        """Return the original dispatch receipt on replay; use get_status for freshness."""
        route = await self._admit(adapter_id, task)
        run, _ = await self._started(route)
        self._observe_active_slot(route, run, epoch=0)
        return ManagedRun(route.handle, route.adapter_id, run)

    async def dispatch_task(self, adapter_id: str, task: AdapterTask) -> DispatchSnapshot:
        """Admit once and return a handle without waiting for the adapter's receipt.

        Replay observes the current dispatch state, never execution success or permission.
        The admitted start retains its history slot independently of caller cancellation.
        """
        route = await self._admit(adapter_id, task)
        return self.get_dispatch(route.handle)

    async def _admit(self, adapter_id: str, task: AdapterTask) -> _Route[R]:
        adapter = self._adapter(adapter_id)
        if type(task) is not AdapterTask:
            raise AgentSyncError("validation_error", "Invalid adapter request.")
        task = replace(task)
        if (task.project_id, task.session_id) != (self._project_id, self._session_id):
            raise AgentSyncError(
                "namespace_mismatch", "Request does not match manager namespace.", 403
            )
        async with self._lock:
            route = self._requests.get(task.request_id)
            if route is not None:
                if route.adapter_id != adapter_id or route.task != task:
                    raise AgentSyncError(
                        "idempotency_conflict", "Request ID has different inputs.", 409
                    )
            else:
                if len(self._routes) >= self._max_runs:
                    raise AgentSyncError(
                        "history_capacity_exceeded", "Manager history is exhausted.", 409
                    )
                limit = self._max_pending_starts
                if limit is not None and self._pending_start_count() >= limit:
                    raise AgentSyncError(
                        "pending_start_capacity_exceeded", "Manager pending start capacity is exhausted.", 409
                    )
                handle = uuid.uuid4().hex
                self._hold_active_slot(handle)
                start = asyncio.create_task(self._start(adapter, task))
                route = _Route(handle, adapter_id, task, start)
                self._routes[handle] = route
                self._requests[task.request_id] = route
        return route

    def _hold_active_slot(self, handle: str) -> bool:
        """Reserve capacity on the owning event loop before entering an adapter."""
        limit = self._max_active_runs
        if limit is None or handle in self._active_handles:
            return False
        if len(self._active_handles) >= limit:
            raise AgentSyncError(
                "running_capacity_exceeded", "Manager active run capacity is exhausted.", 409,
            )
        self._active_handles.add(handle)
        return True

    def _observe_active_slot(self, route: _Route[R], run: AdapterRun, *, epoch: int) -> None:
        if self._max_active_runs is None or route.resuming or route.resume_epoch != epoch:
            return
        if (
            isinstance(run, _HostRun) and not run.slot_held and run.parent_ended
            and run.status in ("succeeded", "failed")
        ) or (
            isinstance(run, RunSnapshot) and run.finished_at is not None
            and run.status in ("succeeded", "failed", "cancelled", "timed_out")
        ):
            self._active_handles.discard(route.handle)

    async def _started(self, route: _Route[R]) -> tuple[R, str]:
        outcome = await asyncio.shield(route.start)
        if outcome.run is None or outcome.run_id is None:
            raise AgentSyncError(
                outcome.error_code or "adapter_start_unknown",
                "Adapter start did not return a usable run.",
                409,
            )
        return outcome.run, outcome.run_id

    async def _start(self, adapter: AgentAdapter[C, R, T], task: AdapterTask) -> _StartResult[R]:
        try:
            run = await adapter.start_task(task)
            run_id = self._validate_run(run, task)
            return _StartResult(run=run, run_id=run_id)
        except AgentSyncError as error:
            # Only fixed public codes survive; no exception, traceback, or message is retained.
            public_code = vars(error).get("code")
            code = (
                public_code
                if type(public_code) is str
                and public_code
                in {
                    "unsupported",
                    "invalid_adapter_run",
                    "namespace_mismatch",
                    "capacity_exceeded",
                    "history_capacity_exceeded",
                    "running_capacity_exceeded",
                    "task_already_active",
                    "idempotency_conflict",
                    "validation_error",
                }
                else "adapter_start_unknown"
            )
            return _StartResult(error_code=code)
        except (Exception, asyncio.CancelledError):
            return _StartResult(error_code="adapter_start_unknown")

    @staticmethod
    def _validate_run(run: R, task: AdapterTask, run_id: str | None = None) -> str:
        _raise_pending_cancellation()
        try:
            captured_id = run.run_id
            _identifier(captured_id)
            valid = bool(
                (run.project_id, run.session_id, run.task_id, run.request_id)
                == (task.project_id, task.session_id, task.task_id, task.request_id)
                and (run_id is None or captured_id == run_id)
            )
        except (Exception, asyncio.CancelledError):
            valid = False
        _raise_pending_cancellation()
        if not valid:
            raise AgentSyncError(
                "invalid_adapter_run", "Adapter returned an inconsistent run.", 409
            )
        return captured_id

    async def _lookup(self, handle: str) -> tuple[_Route[R], str]:
        _identifier(handle)
        route = self._routes.get(handle)
        if route is None:
            raise AgentSyncError("not_found", "Manager run does not exist.", 404)
        _, run_id = await self._started(route)
        return route, run_id

    async def get_status(self, handle: str) -> ManagedRun[R]:
        route, run_id = await self._lookup(handle)
        epoch = route.resume_epoch
        adapter = self._adapter(route.adapter_id)
        run = await _call_adapter(lambda: adapter.get_status(run_id))
        self._validate_run(run, route.task, run_id)
        self._observe_active_slot(route, run, epoch=epoch)
        return ManagedRun(handle, route.adapter_id, run)

    async def get_result(self, handle: str) -> T:
        route, run_id = await self._lookup(handle)
        epoch = route.resume_epoch
        adapter = self._adapter(route.adapter_id)
        result = await _call_adapter(lambda: adapter.get_result(run_id))
        _raise_pending_cancellation()
        try:
            run = getattr(result, "run", None)
        except (Exception, asyncio.CancelledError):
            run = None
        self._validate_run(cast(R, run), route.task, run_id)
        self._observe_active_slot(route, cast(R, run), epoch=epoch)
        return result

    async def cancel_task(self, handle: str) -> ManagedRun[R]:
        route, run_id = await self._lookup(handle)
        epoch = route.resume_epoch
        adapter = self._adapter(route.adapter_id)
        run = await _call_adapter(lambda: adapter.cancel_task(run_id))
        self._validate_run(run, route.task, run_id)
        self._observe_active_slot(route, run, epoch=epoch)
        return ManagedRun(handle, route.adapter_id, run)

    async def cancel_bounded(self, handle: str, *, timeout_seconds: float) -> CancellationObservation[R]:
        """Observe one cancel request within a shared startup and operation deadline.

        An unreturned start is left alone. After adapter entry, a timeout means
        that the cancellation outcome is unknown, even if cleanup is still running.
        A returned adapter receipt never proves descendant or remote cleanup.
        """
        if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 300:
            raise AgentSyncError("validation_error", "Invalid cancellation observation timeout.")
        _raise_pending_cancellation()
        snapshot = self.get_dispatch(handle)
        entered = False
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout_seconds
        window = asyncio.timeout_at(end)
        try:
            async with window:
                if snapshot.state == "pending":
                    snapshot = await self.wait_dispatch(handle, timeout_seconds=timeout_seconds)
                if snapshot.state == "error":
                    return CancellationObservation(
                        handle, "start_unresolved" if snapshot.error_code == "adapter_start_unknown" else "start_error",
                        error_code=snapshot.error_code,
                    )
                if snapshot.state == "pending" or loop.time() >= end:
                    return CancellationObservation(handle, "start_unresolved", error_code="observation_timeout")
                entered = True
                observed = await self.cancel_task(handle)
        except TimeoutError:
            return CancellationObservation(
                handle, "cancel_unresolved" if entered else "start_unresolved", error_code="observation_timeout",
            )
        except AgentSyncError as error:
            # cancel_task routes failures through fixed public adapter codes.
            return CancellationObservation(
                handle, "unsupported" if error.code == "unsupported" else "cancel_unresolved",
                error_code=error.code,
            )
        if window.expired() or loop.time() >= end:
            return CancellationObservation(handle, "cancel_unresolved", error_code="observation_timeout")
        return CancellationObservation(handle, "returned", observed)

    async def resume_task(self, handle: str) -> ManagedRun[R]:
        route, run_id = await self._lookup(handle)
        adapter = self._adapter(route.adapter_id)
        bounded = self._max_active_runs is not None
        if bounded and route.resuming:
            raise AgentSyncError("task_already_active", "An adapter resume is already active.", 409)
        reacquired = self._hold_active_slot(handle)
        if bounded:
            route.resuming = True
            route.resume_epoch += 1
        try:
            run = await _call_adapter(lambda: adapter.resume_task(run_id))
        except AgentSyncError as error:
            if reacquired and error.code == "unsupported":
                self._active_handles.discard(handle)
            raise
        finally:
            if bounded:
                route.resuming = False
        self._validate_run(run, route.task, run_id)
        self._observe_active_slot(route, run, epoch=route.resume_epoch)
        return ManagedRun(handle, route.adapter_id, run)

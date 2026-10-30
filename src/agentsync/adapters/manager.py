"""Instance-local routing for trusted adapters; no scheduling or Core authorization.

Use one asyncio loop. Registration and lifetime history are bounded and immutable;
there is no eviction, restart recovery, automatic retry, or cross-instance dedup.
A dispatched start owns its history slot even if it raises, hangs, or its caller
cancels. The loop must remain alive for outstanding starts. Adapter timeouts and
cleanup remain the adapter's responsibility. Raw observations retain their own
markers: this router makes no success, verification, or authorization claims.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Generic, Literal, Protocol, TypeVar, cast

from agentsync.adapters.base import AdapterTask, AgentAdapter, _identifier
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
class _StartResult(Generic[R]):
    run: R | None = field(default=None, repr=False)
    error_code: str | None = None


@dataclass(slots=True)
class _Route(Generic[R]):
    handle: str
    adapter_id: str
    task: AdapterTask = field(repr=False)
    start: asyncio.Task[_StartResult[R]] = field(repr=False)


class RunManager(Generic[C, R, T]):
    def __init__(
        self,
        project_id: str,
        session_id: str,
        adapters: Mapping[str, AgentAdapter[C, R, T]],
        *,
        max_runs: int = 100,
    ) -> None:
        _identifier(project_id)
        _identifier(session_id)
        if type(max_runs) is not int or not 1 <= max_runs <= 10000:
            raise AgentSyncError("validation_error", "Invalid manager capacity.")
        if not isinstance(adapters, Mapping) or not 1 <= len(adapters) <= 32:
            raise AgentSyncError("validation_error", "Invalid adapter registration.")
        self._adapters = dict(adapters)
        for name, adapter in self._adapters.items():
            _identifier(name)
            if not isinstance(adapter, AgentAdapter):
                raise AgentSyncError("validation_error", "Invalid adapter registration.")
        self._project_id, self._session_id = project_id, session_id
        self._max_runs = max_runs
        self._lock = asyncio.Lock()
        self._routes: dict[str, _Route[R]] = {}
        self._requests: dict[str, _Route[R]] = {}

    def history(self) -> tuple[str, ...]:
        """Opaque handles in dispatch order, including unresolved/failed starts."""
        return tuple(self._routes)

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
        return await self._adapter(adapter_id).capabilities()

    async def start_task(self, adapter_id: str, task: AdapterTask) -> ManagedRun[R]:
        """Return the original dispatch receipt on replay; use get_status for freshness."""
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
                handle = uuid.uuid4().hex
                start = asyncio.create_task(self._start(adapter, task))
                route = _Route(handle, adapter_id, task, start)
                self._routes[handle] = route
                self._requests[task.request_id] = route
        run = await self._started(route)
        return ManagedRun(route.handle, route.adapter_id, run)

    async def _started(self, route: _Route[R]) -> R:
        outcome = await asyncio.shield(route.start)
        if outcome.run is None:
            raise AgentSyncError(
                outcome.error_code or "adapter_start_unknown",
                "Adapter start did not return a usable run.",
                409,
            )
        return outcome.run

    async def _start(self, adapter: AgentAdapter[C, R, T], task: AdapterTask) -> _StartResult[R]:
        try:
            run = await adapter.start_task(task)
            self._validate_run(run, task)
            return _StartResult(run=run)
        except AgentSyncError as error:
            # Only fixed public codes survive; no exception, traceback, or message is retained.
            code = (
                error.code
                if error.code
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
    def _validate_run(run: R, task: AdapterTask, run_id: str | None = None) -> None:
        try:
            _identifier(run.run_id)
            valid = (run.project_id, run.session_id, run.task_id, run.request_id) == (
                task.project_id,
                task.session_id,
                task.task_id,
                task.request_id,
            ) and (run_id is None or run.run_id == run_id)
        except (AttributeError, TypeError, AgentSyncError):
            valid = False
        if not valid:
            raise AgentSyncError(
                "invalid_adapter_run", "Adapter returned an inconsistent run.", 409
            )

    async def _lookup(self, handle: str) -> tuple[_Route[R], R]:
        _identifier(handle)
        route = self._routes.get(handle)
        if route is None:
            raise AgentSyncError("not_found", "Manager run does not exist.", 404)
        return route, await self._started(route)

    async def get_status(self, handle: str) -> ManagedRun[R]:
        route, initial = await self._lookup(handle)
        run = await self._adapter(route.adapter_id).get_status(initial.run_id)
        self._validate_run(run, route.task, initial.run_id)
        return ManagedRun(handle, route.adapter_id, run)

    async def get_result(self, handle: str) -> T:
        route, initial = await self._lookup(handle)
        result = await self._adapter(route.adapter_id).get_result(initial.run_id)
        self._validate_run(cast(R, getattr(result, "run", None)), route.task, initial.run_id)
        return result

    async def cancel_task(self, handle: str) -> ManagedRun[R]:
        route, initial = await self._lookup(handle)
        run = await self._adapter(route.adapter_id).cancel_task(initial.run_id)
        self._validate_run(run, route.task, initial.run_id)
        return ManagedRun(handle, route.adapter_id, run)

    async def resume_task(self, handle: str) -> ManagedRun[R]:
        route, initial = await self._lookup(handle)
        run = await self._adapter(route.adapter_id).resume_task(initial.run_id)
        self._validate_run(run, route.task, initial.run_id)
        return ManagedRun(handle, route.adapter_id, run)

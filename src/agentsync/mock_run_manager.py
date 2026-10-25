"""Instance-local Mock simulation routing, not Core scheduling or authorization.

This manager never claims or updates Core tasks, invokes real clients, or grants
permissions. Capacity and task deduplication cover this one in-memory instance,
not other managers, Core leases, processes, or actual client concurrency.
Use from one asyncio event loop only. All routes and history are in memory;
there is no durability, restart recovery, or cross-process synchronization.
"""

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal

from agentsync.adapters import AdapterResult, AdapterTask, MockAdapter, RunSnapshot
from agentsync.adapters.base import _bounded_text, _identifier
from agentsync.errors import AgentSyncError


@dataclass(frozen=True, slots=True)
class MockWorker:
    agent_id: str
    session_id: str

    def __post_init__(self) -> None:
        _identifier(self.agent_id)
        _identifier(self.session_id)


@dataclass(frozen=True, slots=True)
class _Markers:
    scope: Literal["simulation_only"] = field(default="simulation_only", init=False)
    simulated: Literal[True] = field(default=True, init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class RoutedSnapshot(_Markers):
    agent_id: str
    run: RunSnapshot


@dataclass(frozen=True, slots=True)
class RoutedResult(_Markers):
    agent_id: str
    result: AdapterResult


@dataclass(frozen=True, slots=True)
class MockManagerCapabilities(_Markers):
    workers: tuple[MockWorker, ...]
    global_limit: int
    per_agent_limit: int
    max_runs: int
    supports_cancel: Literal[True] = field(default=True, init=False)
    supports_resume: Literal[False] = field(default=False, init=False)
    supports_usage: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class _Route:
    agent_id: str
    task: AdapterTask


class MockRunManager:
    def __init__(
        self,
        project_id: str,
        workers: tuple[MockWorker, ...],
        *,
        global_limit: int = 4,
        per_agent_limit: int = 1,
        max_runs: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        _identifier(project_id)
        if (
            type(workers) is not tuple
            or not 1 <= len(workers) <= 32
            or any(type(worker) is not MockWorker for worker in workers)
        ):
            raise AgentSyncError("validation_error", "Invalid mock worker configuration.")
        workers = tuple(replace(worker) for worker in workers)
        if len({worker.agent_id for worker in workers}) != len(workers) or len(
            {worker.session_id for worker in workers}
        ) != len(workers):
            raise AgentSyncError("validation_error", "Mock worker namespaces must be distinct.")
        if (
            any(
                type(value) is not int or not 1 <= value <= 100
                for value in (global_limit, per_agent_limit)
            )
            or type(max_runs) is not int
            or not 1 <= max_runs <= 10000
            or not callable(clock)
        ):
            raise AgentSyncError("validation_error", "Invalid mock manager configuration.")
        self._project_id = project_id
        self._workers = workers
        self._worker_by_agent = {worker.agent_id: worker for worker in workers}
        self._global_limit = global_limit
        self._per_agent_limit = per_agent_limit
        self._max_runs = max_runs
        self._clock = clock
        self._cached_time = 0.0
        self._last_time: float | None = None
        self._clock_failed = False
        self._lock = asyncio.Lock()
        self._adapters = {
            worker.agent_id: MockAdapter(
                project_id, worker.session_id, max_runs=max_runs, clock=self._clock_value
            )
            for worker in workers
        }
        self._routes: dict[str, _Route] = {}
        self._requests: dict[tuple[str, str], str] = {}
        self._active: dict[str, str] = {}

    async def capabilities(self) -> MockManagerCapabilities:
        return MockManagerCapabilities(
            self._workers, self._global_limit, self._per_agent_limit, self._max_runs
        )

    async def start_task(self, agent_id: str, task: AdapterTask) -> RoutedSnapshot:
        _identifier(agent_id)
        worker = self._worker_by_agent.get(agent_id)
        if worker is None:
            raise AgentSyncError("not_found", "Mock worker does not exist.", 404)
        if type(task) is not AdapterTask:
            raise AgentSyncError("validation_error", "Invalid mock task request.")
        task = replace(task)
        if task.project_id != self._project_id or task.session_id != worker.session_id:
            raise AgentSyncError(
                "namespace_mismatch", "Mock request does not match worker namespace.", 403
            )
        async with self._lock:
            previous = self._requests.get((agent_id, task.request_id))
            if previous is not None and self._routes[previous].task != task:
                raise AgentSyncError(
                    "idempotency_conflict", "Mock request has different inputs.", 409
                )
            await self._refresh_running()
            if previous is not None:
                return RoutedSnapshot(agent_id, await self._adapters[agent_id].get_status(previous))
            if self._clock_failed:
                raise AgentSyncError("invalid_clock", "Mock manager clock is unavailable.", 409)
            if task.task_id in self._active:
                raise AgentSyncError(
                    "task_already_running", "Task already has an active local mock run.", 409
                )
            if len(self._routes) >= self._max_runs:
                raise AgentSyncError(
                    "history_capacity_exceeded", "Mock history capacity has been reached.", 409
                )
            if len(self._active) >= self._global_limit:
                raise AgentSyncError(
                    "global_capacity_exceeded",
                    "Mock global running capacity has been reached.",
                    409,
                )
            if (
                sum(self._routes[run_id].agent_id == agent_id for run_id in self._active.values())
                >= self._per_agent_limit
            ):
                raise AgentSyncError(
                    "worker_capacity_exceeded",
                    "Mock worker running capacity has been reached.",
                    409,
                )
            try:
                run = await self._adapters[agent_id].start_task(task)
            except AgentSyncError as exc:
                if exc.code in {"invalid_clock", "clock_regressed"}:
                    self._clock_failed = True
                    self._cached_time = float("nan")
                    await self._refresh_running()
                    raise AgentSyncError(
                        "invalid_clock", "Mock manager clock is unavailable.", 409
                    ) from None
                raise
            self._routes[run.run_id] = _Route(agent_id, task)
            self._requests[(agent_id, task.request_id)] = run.run_id
            self._active[task.task_id] = run.run_id
            return RoutedSnapshot(agent_id, run)

    async def get_status(self, run_id: str) -> RoutedSnapshot:
        async with self._lock:
            route = self._route(run_id)
            await self._refresh_running()
            return RoutedSnapshot(
                route.agent_id, await self._adapters[route.agent_id].get_status(run_id)
            )

    async def get_result(self, run_id: str) -> RoutedResult:
        async with self._lock:
            route = self._route(run_id)
            await self._refresh_running()
            return RoutedResult(
                route.agent_id, await self._adapters[route.agent_id].get_result(run_id)
            )

    async def cancel_task(self, run_id: str) -> RoutedSnapshot:
        async with self._lock:
            route = self._route(run_id)
            await self._refresh_running()
            ended = await self._adapters[route.agent_id].cancel_task(run_id)
            self._active.pop(route.task.task_id, None)
            return RoutedSnapshot(route.agent_id, ended)

    async def finish_mock_run(
        self, run_id: str, *, output: str = "", failed: bool = False
    ) -> RoutedSnapshot:
        _bounded_text(output, 65536)
        if type(failed) is not bool:
            raise AgentSyncError("validation_error", "Invalid mock finish control.")
        async with self._lock:
            route = self._route(run_id)
            await self._refresh_running()
            ended = await self._adapters[route.agent_id].finish_run(
                run_id, output=output, failed=failed
            )
            self._active.pop(route.task.task_id, None)
            return RoutedSnapshot(route.agent_id, ended)

    async def resume_task(self, run_id: str) -> RoutedSnapshot:
        async with self._lock:
            self._route(run_id)
            raise AgentSyncError("unsupported", "Mock manager cannot resume runs.")

    def _route(self, run_id: str) -> _Route:
        _identifier(run_id)
        route = self._routes.get(run_id)
        if route is None:
            raise AgentSyncError("not_found", "Mock run does not exist.", 404)
        return route

    async def _refresh_running(self) -> None:
        if not self._clock_failed:
            try:
                value = self._clock()
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError
                observed = float(value)
                if self._last_time is not None and observed < self._last_time:
                    raise ValueError
                self._cached_time = observed
                self._last_time = observed
            except Exception:
                # All workers observe one sticky fault, including previously unused workers.
                # Manager-level invalid and regressed clocks are both invalid_clock.
                self._clock_failed = True
                self._cached_time = float("nan")
        for task_id, run_id in list(self._active.items()):
            route = self._routes[run_id]
            run = await self._adapters[route.agent_id].get_status(run_id)
            if run.status != "running":
                self._active.pop(task_id, None)

    def _clock_value(self) -> float:
        """Internal adapters only see the manager's one lock-protected time sample."""
        return self._cached_time

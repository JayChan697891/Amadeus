"""In-memory simulation only: never invokes code, a client, or a Core operation."""

import asyncio
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import replace

from agentsync.adapters.base import (
    AdapterCapabilities,
    AdapterResult,
    AdapterTask,
    AgentAdapter,
    RunSnapshot,
    RunStatus,
    _bounded_text,
    _identifier,
)
from agentsync.errors import AgentSyncError


class MockAdapter(AgentAdapter):
    def __init__(
        self,
        project_id: str,
        session_id: str,
        *,
        max_runs: int = 100,
        cancel_supported: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        _identifier(project_id)
        _identifier(session_id)
        if (
            type(max_runs) is not int
            or not 1 <= max_runs <= 10000
            or type(cancel_supported) is not bool
            or not callable(clock)
        ):
            raise AgentSyncError("validation_error", "Invalid mock adapter configuration.")
        self._project_id = project_id
        self._session_id = session_id
        self._clock = clock
        self._max_runs = max_runs
        self._cancel_supported = cancel_supported
        self._lock = asyncio.Lock()
        self._runs: dict[str, RunSnapshot] = {}
        self._requests: dict[str, tuple[AdapterTask, str]] = {}
        self._results: dict[str, AdapterResult] = {}
        self._last_now: float | None = None
        self._clock_error: str | None = None

    async def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(supports_cancel=self._cancel_supported)

    async def start_task(self, task: AdapterTask) -> RunSnapshot:
        if type(task) is not AdapterTask:
            raise AgentSyncError("validation_error", "Invalid adapter request.")
        # Own a validated immutable value, rather than retaining caller-owned input.
        task = replace(task)
        async with self._lock:
            if task.project_id != self._project_id or task.session_id != self._session_id:
                raise AgentSyncError(
                    "namespace_mismatch", "Request does not match adapter namespace.", 403
                )
            previous = self._requests.get(task.request_id)
            if previous is not None:
                if previous[0] != task:
                    raise AgentSyncError(
                        "idempotency_conflict", "Request ID has different inputs.", 409
                    )
            now = self._refresh()
            if previous is not None:
                return self._runs[previous[1]]
            if now is None:
                raise AgentSyncError(
                    self._clock_error or "invalid_clock", "Mock clock is unavailable.", 409
                )
            if len(self._runs) >= self._max_runs:
                raise AgentSyncError(
                    "capacity_exceeded", "Mock run capacity has been reached.", 409
                )
            deadline = now + task.timeout_seconds
            if not math.isfinite(deadline) or deadline <= now:
                self._clock_fault("invalid_clock")
                raise AgentSyncError(
                    "invalid_clock", "Mock clock cannot represent the deadline.", 409
                )
            snapshot = RunSnapshot(
                task.project_id,
                task.session_id,
                task.task_id,
                task.request_id,
                str(uuid.uuid4()),
                "running",
                now,
                deadline,
            )
            self._runs[snapshot.run_id] = snapshot
            self._requests[task.request_id] = (task, snapshot.run_id)
            return snapshot

    async def get_status(self, run_id: str) -> RunSnapshot:
        async with self._lock:
            self._lookup(run_id)
            self._refresh()
            return self._runs[run_id]

    async def get_result(self, run_id: str) -> AdapterResult:
        async with self._lock:
            self._lookup(run_id)
            self._refresh()
            run = self._runs[run_id]
            if run.status == "running":
                raise AgentSyncError("result_not_ready", "Mock result is not ready.", 409)
            return self._results[run_id]

    async def cancel_task(self, run_id: str) -> RunSnapshot:
        async with self._lock:
            self._lookup(run_id)
            if not self._cancel_supported:
                raise AgentSyncError("unsupported", "Operation is unsupported by this adapter.")
            now = self._refresh()
            return self._finish(self._runs[run_id], "cancelled", now, "", "cancelled")

    async def resume_task(self, run_id: str) -> RunSnapshot:
        async with self._lock:
            self._lookup(run_id)
            raise AgentSyncError("unsupported", "Operation is unsupported by this adapter.")

    async def finish_run(
        self, run_id: str, *, output: str = "", failed: bool = False
    ) -> RunSnapshot:
        """Explicit simulation control, never an execution or verification action."""
        _bounded_text(output, 65536)
        if type(failed) is not bool:
            raise AgentSyncError("validation_error", "Invalid mock finish control.")
        async with self._lock:
            self._lookup(run_id)
            now = self._refresh()
            return self._finish(
                self._runs[run_id],
                "failed" if failed else "succeeded",
                now,
                output,
                "mock_failure" if failed else None,
            )

    def _lookup(self, run_id: str) -> RunSnapshot:
        _identifier(run_id)
        run = self._runs.get(run_id)
        if run is None:
            raise AgentSyncError("not_found", "Mock run does not exist.", 404)
        return run

    def _finish(
        self,
        run: RunSnapshot,
        status: RunStatus,
        now: float | None,
        output: str,
        error_code: str | None,
    ) -> RunSnapshot:
        if run.status != "running":
            raise AgentSyncError("invalid_state", "Mock run is already terminal.", 409)
        changed = replace(run, status=status, finished_at=now, error_code=error_code)
        self._runs[run.run_id] = changed
        self._results[run.run_id] = AdapterResult(changed, output)
        return changed

    def _clock_fault(self, code: str) -> None:
        self._clock_error = code
        for run in list(self._runs.values()):
            if run.status == "running":
                self._finish(run, "failed", self._last_now, "", code)

    def _refresh(self) -> float | None:
        if self._clock_error is not None:
            return None
        try:
            value = self._clock()
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError
            now = float(value)
        except Exception:
            self._clock_fault("invalid_clock")
            return None
        if self._last_now is not None and now < self._last_now:
            self._clock_fault("clock_regressed")
            return None
        self._last_now = now
        for run in list(self._runs.values()):
            if run.status == "running" and now >= run.deadline_at:
                self._finish(run, "timed_out", run.deadline_at, "", "timeout")
        return now

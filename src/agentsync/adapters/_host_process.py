"""Private process lifecycle shared by client-specific protocol adapters.

The trusted host factory supplies fresh owned captures; it is not authorization.
This engine never launches a client, reads credentials, interprets task text or
connects Core. Parent termination, instance ownership and unknown-slot semantics
are unchanged from the original Codex lifecycle. Protocol projections are neutral
data, never event conversion or authenticated client evidence.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Generic, Literal, TypeVar

from agentsync.adapters.base import AdapterTask, AgentAdapter, _identifier
from agentsync.adapters.process_capture import CapturedProcess, CaptureSnapshot, CaptureState
from agentsync.errors import AgentSyncError

_CaptureFactory = Callable[[AdapterTask], Awaitable[CapturedProcess]]
_HostStatus = Literal["starting", "running", "succeeded", "failed", "unknown"]


@dataclass(frozen=True, slots=True)
class _HostMarkers:
    scope: Literal["host_process_protocol"] = field(default="host_process_protocol", init=False)
    provenance: Literal["trusted_host_factory"] = field(default="trusted_host_factory", init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)
    capacity_scope: Literal["instance_protocol_runs"] = field(
        default="instance_protocol_runs", init=False
    )
    tree_cleanup: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class _HostRun(_HostMarkers):
    project_id: str
    session_id: str
    task_id: str
    request_id: str
    run_id: str
    status: _HostStatus
    started_at: float
    finished_at: float | None = None
    capture_id: str | None = None
    capture_state: CaptureState | None = None
    exit_code: int | None = None
    parent_ended: bool = False
    timed_out: bool = False
    slot_held: bool = True
    error_code: str | None = None


_CapabilitiesT = TypeVar("_CapabilitiesT")
_RunT = TypeVar("_RunT", bound=_HostRun)
_ResultT = TypeVar("_ResultT")
_UsageT = TypeVar("_UsageT")


@dataclass(frozen=True, slots=True)
class _ProtocolObservation(Generic[_UsageT]):
    state: Literal["succeeded", "failed", "incomplete"]
    messages: tuple[str, ...]
    usage: _UsageT | None
    client_id: str | None
    error_code: str | None


@dataclass
class _Entry(Generic[_RunT, _ResultT]):
    task: AdapterTask
    view: _RunT
    process: CapturedProcess | None = None
    result: _ResultT | None = None
    driver: asyncio.Task[None] | None = None
    deadline: asyncio.TimerHandle | None = None
    cancel_job: asyncio.Task[None] | None = None
    deadline_job: asyncio.Task[_RunT] | None = None
    stop_code: str | None = None
    timed_out: bool = False


class _HostProcessAdapter(
    AgentAdapter[_CapabilitiesT, _RunT, _ResultT],
    Generic[_CapabilitiesT, _RunT, _ResultT, _UsageT],
):
    def __init__(
        self,
        project_id: str,
        session_id: str,
        *,
        factory: _CaptureFactory | None = None,
        new_capabilities: Callable[[bool, int, int], _CapabilitiesT],
        new_run: Callable[[AdapterTask, str, float], _RunT],
        new_result: Callable[[_RunT, tuple[str, ...], _UsageT | None, str | None], _ResultT],
        parse: Callable[[str], _ProtocolObservation[_UsageT]],
        configuration_error: str,
        max_runs: int = 100,
        running_limit: int = 1,
    ):
        _identifier(project_id)
        _identifier(session_id)
        if (
            (factory is not None and not callable(factory))
            or type(max_runs) is not int
            or not 1 <= max_runs <= 10000
            or type(running_limit) is not int
            or not 1 <= running_limit <= 100
        ):
            raise AgentSyncError("validation_error", configuration_error)
        self._project_id, self._session_id = project_id, session_id
        self._factory = factory
        self._max_runs, self._running_limit = max_runs, running_limit
        self._new_capabilities = new_capabilities
        self._new_run = new_run
        self._new_result = new_result
        self._parse = parse
        self._entries: dict[str, _Entry[_RunT, _ResultT]] = {}
        self._requests: dict[str, str] = {}
        self._capture_owners: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def capabilities(self) -> _CapabilitiesT:
        return self._new_capabilities(
            self._factory is not None, self._max_runs, self._running_limit
        )

    async def start_task(self, task: AdapterTask) -> _RunT:
        if type(task) is not AdapterTask:
            raise AgentSyncError("validation_error", "Invalid adapter request.")
        task = replace(task)
        if task.project_id != self._project_id or task.session_id != self._session_id:
            raise AgentSyncError(
                "namespace_mismatch", "Request does not match adapter namespace.", 403
            )
        if self._factory is None:
            raise AgentSyncError("unsupported", "A trusted host process factory is required.")
        async with self._lock:
            existing = self._requests.get(task.request_id)
            if existing is not None:
                existing_entry = self._entries[existing]
                if existing_entry.task != task:
                    raise AgentSyncError(
                        "idempotency_conflict", "Request ID has different inputs.", 409
                    )
                return existing_entry.view
            if any(
                entry.view.slot_held and entry.task.task_id == task.task_id
                for entry in self._entries.values()
            ):
                raise AgentSyncError(
                    "task_already_active", "Task already has an active adapter run.", 409
                )
            if len(self._entries) >= self._max_runs:
                raise AgentSyncError(
                    "history_capacity_exceeded", "Adapter history capacity is exhausted.", 409
                )
            if sum(entry.view.slot_held for entry in self._entries.values()) >= self._running_limit:
                raise AgentSyncError(
                    "running_capacity_exceeded", "Adapter running capacity is exhausted.", 409
                )
            loop = asyncio.get_running_loop()
            view = self._new_run(task, uuid.uuid4().hex, loop.time())
            entry: _Entry[_RunT, _ResultT] = _Entry(task, view)
            self._entries[view.run_id] = entry
            self._requests[task.request_id] = view.run_id
            entry.driver = asyncio.create_task(self._drive(entry))
            entry.deadline = loop.call_later(task.timeout_seconds, self._schedule_timeout, entry)
            return view

    def _schedule_timeout(self, entry: _Entry[_RunT, _ResultT]) -> None:
        if entry.result is None:
            entry.deadline_job = asyncio.create_task(
                self._request_stop(entry, "adapter_timeout", True)
            )

    async def _drive(self, entry: _Entry[_RunT, _ResultT]) -> None:
        try:
            # Caller cancellation cannot reach this independent background task.
            if entry.result is not None:
                return
            assert self._factory is not None
            process = await self._factory(entry.task)
            if type(process) is not CapturedProcess:
                async with self._lock:
                    self._finish(entry, "unknown", error="factory_invalid_result")
                return
            observed = await process.snapshot()
            async with self._lock:
                if observed.capture_id in self._capture_owners:
                    self._finish(entry, "unknown", error="capture_reused")
                    return
                if observed.started_at <= entry.view.started_at:
                    self._finish(entry, "unknown", error="capture_stale")
                    return
                # At most one capture per bounded history entry. Never kill a
                # rejected handle that may belong to another task or caller.
                self._capture_owners[observed.capture_id] = entry.view.run_id
                entry.process = process
                late = entry.result is not None
                if not late:
                    entry.view = replace(
                        entry.view,
                        status="running",
                        capture_id=observed.capture_id,
                        capture_state=observed.state,
                        exit_code=observed.exit_code,
                        parent_ended=observed.parent_ended,
                    )
            if late:
                # Factory deadline/cancel already froze unknown. Only clean our
                # late parent handle; do not rewrite history or release its slot.
                await process.cancel()
                return
            await process.wait()
            await self._collect(entry)
        except asyncio.CancelledError:
            async with self._lock:
                self._finish(entry, "unknown", error="factory_cancelled")
            if entry.process is not None:
                await entry.process.cancel()
        except Exception:
            async with self._lock:
                self._finish(entry, "unknown", error="factory_failed")
            if entry.process is not None:
                await entry.process.cancel()

    async def _collect(self, entry: _Entry[_RunT, _ResultT]) -> None:
        assert entry.process is not None
        raw = await entry.process.get_result()
        capture = raw.snapshot
        status: _HostStatus = "unknown"
        messages: tuple[str, ...] = ()
        usage: _UsageT | None = None
        client_thread_id = None
        error: str | None = entry.stop_code or capture.error_code or "capture_unknown"
        if capture.state == "exited":
            if capture.exit_code is not None and capture.exit_code != 0:
                status, error = "failed", "process_failed"
            elif capture.exit_code == 0:
                try:
                    report = self._parse(raw.stdout.decode("utf-8"))
                except (UnicodeError, AgentSyncError):
                    error = "protocol_invalid"
                else:
                    error = report.error_code
                    if report.state == "succeeded":
                        status = "succeeded"
                    elif report.state == "failed":
                        status = "failed"
                    if status != "unknown":
                        messages, usage = report.messages, report.usage
                        client_thread_id = report.client_id
        async with self._lock:
            self._finish(
                entry,
                status,
                capture=capture,
                error=error,
                messages=messages,
                usage=usage,
                client_thread_id=client_thread_id,
            )

    def _finish(
        self,
        entry: _Entry[_RunT, _ResultT],
        status: _HostStatus,
        *,
        capture: CaptureSnapshot | None = None,
        error: str | None = None,
        messages: tuple[str, ...] = (),
        usage: _UsageT | None = None,
        client_thread_id: str | None = None,
    ) -> None:
        if entry.result is not None:
            return
        entry.view = replace(
            entry.view,
            status=status,
            finished_at=asyncio.get_running_loop().time(),
            capture_id=capture.capture_id if capture else None,
            capture_state=capture.state if capture else None,
            exit_code=capture.exit_code if capture else None,
            parent_ended=capture.parent_ended if capture else False,
            timed_out=(entry.timed_out or (capture is not None and capture.state == "timed_out"))
            if status == "unknown"
            else False,
            slot_held=status == "unknown",
            error_code=error,
        )
        entry.result = self._new_result(
            entry.view,
            messages if status != "unknown" else (),
            usage if status != "unknown" else None,
            client_thread_id if status != "unknown" else None,
        )
        if entry.deadline is not None:
            entry.deadline.cancel()

    def _entry(self, run_id: str) -> _Entry[_RunT, _ResultT]:
        _identifier(run_id)
        entry = self._entries.get(run_id)
        if entry is None:
            raise AgentSyncError("not_found", "Adapter run was not found.", 404)
        return entry

    async def get_status(self, run_id: str) -> _RunT:
        async with self._lock:
            return self._entry(run_id).view

    async def get_result(self, run_id: str) -> _ResultT:
        async with self._lock:
            result = self._entry(run_id).result
            if result is None:
                raise AgentSyncError("result_not_ready", "Adapter result is not ready.", 409)
            return result

    async def cancel_task(self, run_id: str) -> _RunT:
        async with self._lock:
            entry = self._entry(run_id)
        return await self._request_stop(entry, "local_cancel_requested", False)

    async def _request_stop(
        self, entry: _Entry[_RunT, _ResultT], code: str, timed_out: bool
    ) -> _RunT:
        async with self._lock:
            if entry.result is not None:
                return entry.view
            if entry.stop_code is None:
                entry.stop_code, entry.timed_out = code, timed_out
            if entry.process is None:
                self._finish(entry, "unknown", error="factory_timeout" if timed_out else code)
                return entry.view
            if entry.cancel_job is None:
                entry.cancel_job = asyncio.create_task(self._cancel_parent(entry))
            job = entry.cancel_job
        await asyncio.shield(job)
        return await self.get_status(entry.view.run_id)

    async def _cancel_parent(self, entry: _Entry[_RunT, _ResultT]) -> None:
        assert entry.process is not None
        try:
            await entry.process.cancel()
            await self._collect(entry)
        except Exception:
            async with self._lock:
                self._finish(entry, "unknown", error="parent_cancel_unconfirmed")

    async def resume_task(self, run_id: str) -> _RunT:
        async with self._lock:
            self._entry(run_id)
        raise AgentSyncError("unsupported", "Resume is unsupported.")

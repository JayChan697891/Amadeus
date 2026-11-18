"""Host-injected process/protocol composition; no CLI, authorization or Core wiring.

The host factory is trusted Python code, not a model/tool input or permission.
There is no executable discovery, command builder, credential read or network
client here. Use one asyncio loop and keep it alive through background cleanup.
History and idempotency cover this in-memory instance only, not restarts or other
adapters. Unknown client observations permanently retain their instance slot;
parent termination never proves server cancellation or descendant cleanup.
Each request must receive a fresh, exclusive capture created on this same event
loop after its adapter run began. Capture IDs and timestamps are associations,
not authentication or a claim of cross-instance ownership enforcement.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from agentsync.adapters._host_process import (
    _CaptureFactory,
    _ContextualCaptureFactory,
    _HostProcessAdapter,
    _HostRun,
    _HostStatus,
    _ProtocolObservation,
)
from agentsync.adapters._host_process import (
    _HostMarkers as _Markers,
)
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex_events import CodexUsage, parse_codex_jsonl
from agentsync.errors import AgentSyncError

CaptureFactory = _CaptureFactory
ContextualCaptureFactory = _ContextualCaptureFactory
CodexStatus = _HostStatus


@dataclass(frozen=True, slots=True)
class CodexCapabilities(_Markers):
    supports_start: bool
    max_runs: int
    running_limit: int
    supports_cancel: Literal[True] = field(default=True, init=False)
    supports_server_cancel: Literal[False] = field(default=False, init=False)
    cancel_scope: Literal["owned_parent_only"] = field(default="owned_parent_only", init=False)
    supports_resume: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class CodexRun(_HostRun):
    # Preserve the public status annotation as well as the original field order.
    status: CodexStatus


@dataclass(frozen=True, slots=True)
class CodexResult(_Markers):
    run: CodexRun
    agent_messages: tuple[str, ...] = field(default=(), repr=False)
    usage: CodexUsage | None = None
    client_thread_id: str | None = field(default=None, repr=False)
    tool_item_event_count: int | None = None


@dataclass(frozen=True, slots=True)
class CodexProgress(_Markers):
    """One complete message observed before any terminal event, not a result."""

    run: CodexRun
    capture_id: str
    stdout_sha256: str
    message: str = field(repr=False)


def _new_run(task: AdapterTask, identity: str, started_at: float) -> CodexRun:
    return CodexRun(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        identity,
        "starting",
        started_at,
    )


def _parse(text: str) -> _ProtocolObservation[CodexUsage]:
    report = parse_codex_jsonl(text, exit_code=0)
    return _ProtocolObservation(
        report.state,
        report.agent_messages,
        report.usage,
        report.thread_id,
        report.error_code,
        report.tool_item_event_count,
    )


def _new_result(
    run: CodexRun,
    messages: tuple[str, ...],
    usage: CodexUsage | None,
    client_id: str | None,
    tool_item_event_count: int | None,
) -> CodexResult:
    return CodexResult(run, messages, usage, client_id, tool_item_event_count)


class CodexAdapter(_HostProcessAdapter[CodexCapabilities, CodexRun, CodexResult, CodexUsage]):
    def get_progress(self, run_id: str) -> CodexProgress | None:
        """Read the entire live prefix without yielding or parsing failed stdout."""
        entry = self._entry(run_id)
        process = entry.process
        if (
            process is None
            or entry.result is not None
            or entry.stop_code is not None
            or entry.view.status != "running"
            or asyncio.get_running_loop().time()
            >= entry.view.started_at + entry.task.timeout_seconds
        ):
            return None
        raw = process.progress_snapshot()
        if raw is None or raw.snapshot.capture_id != entry.view.capture_id:
            return None
        size = len(raw.stdout)
        cached = self._progress_cache.get(run_id)
        if cached is not None and cached[0] == size:
            return (
                cached[1]
                if asyncio.get_running_loop().time()
                < min(raw.snapshot.deadline_at, entry.view.started_at + entry.task.timeout_seconds)
                else None
            )
        self._progress_cache[run_id] = (size, None)
        # Do not discard a partial last record: it might already be a terminal.
        if not raw.stdout.endswith(b"\n"):
            return None
        try:
            report = parse_codex_jsonl(raw.stdout.decode("utf-8"), exit_code=None)
        except (UnicodeError, AgentSyncError):
            return None
        if (
            report.state != "incomplete"
            or report.error_code != "incomplete_stream"
            or report.tool_item_event_count != 0
            or len(report.agent_messages) != 1
        ):
            return None
        started = False
        for event in map(json.loads, raw.stdout.decode("utf-8").split("\n")[:-1]):
            if event["type"] == "turn.started":
                started = True
            elif (
                started
                and isinstance(event.get("item"), dict)
                and event["item"].get("type") == "error"
            ):
                return None
        if asyncio.get_running_loop().time() >= min(
            raw.snapshot.deadline_at, entry.view.started_at + entry.task.timeout_seconds
        ):
            return None
        progress = CodexProgress(
            entry.view,
            raw.snapshot.capture_id,
            hashlib.sha256(raw.stdout).hexdigest(),
            report.agent_messages[0],
        )
        self._progress_cache[run_id] = (size, progress)
        return progress

    def __init__(
        self,
        project_id: str,
        session_id: str,
        *,
        factory: CaptureFactory | None = None,
        contextual_factory: ContextualCaptureFactory | None = None,
        max_runs: int = 100,
        running_limit: int = 1,
    ):
        super().__init__(
            project_id,
            session_id,
            factory=factory,
            contextual_factory=contextual_factory,
            max_runs=max_runs,
            running_limit=running_limit,
            new_capabilities=CodexCapabilities,
            new_run=_new_run,
            new_result=_new_result,
            parse=_parse,
            configuration_error="Invalid Codex adapter configuration.",
        )
        self._progress_cache: dict[str, tuple[int, CodexProgress | None]] = {}

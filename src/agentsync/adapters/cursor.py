"""Host-injected Cursor terminal JSON observation, never a Cursor launcher.

A trusted factory supplies a fresh owned capture; task text is never executed.
No credentials, SDK, network, real-client verification or Core dispatch exists.
Cancellation concerns only the owned parent, with shared unknown-slot semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agentsync.adapters._host_process import (
    _CaptureFactory,
    _ContextualCaptureFactory,
    _HostMarkers,
    _HostProcessAdapter,
    _HostRun,
    _HostStatus,
    _ProtocolObservation,
)
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor_events import CursorReportedMetadata, parse_cursor_json

CaptureFactory = _CaptureFactory
ContextualCaptureFactory = _ContextualCaptureFactory
CursorStatus = _HostStatus


@dataclass(frozen=True, slots=True)
class CursorCapabilities(_HostMarkers):
    supports_start: bool
    max_runs: int
    running_limit: int
    supports_cancel: Literal[True] = field(default=True, init=False)
    supports_server_cancel: Literal[False] = field(default=False, init=False)
    cancel_scope: Literal["owned_parent_only"] = field(default="owned_parent_only", init=False)
    supports_resume: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class CursorRun(_HostRun):
    status: CursorStatus


@dataclass(frozen=True, slots=True)
class CursorResult(_HostMarkers):
    run: CursorRun
    result_text: str = field(default="", repr=False)
    metadata: CursorReportedMetadata | None = None
    client_session_id: str | None = field(default=None, repr=False)


def _new_run(task: AdapterTask, identity: str, started_at: float) -> CursorRun:
    return CursorRun(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        identity,
        "starting",
        started_at,
    )


def _new_result(
    run: CursorRun,
    messages: tuple[str, ...],
    metadata: CursorReportedMetadata | None,
    client_id: str | None,
    _tool_block_count: int | None,
) -> CursorResult:
    return CursorResult(run, messages[0] if messages else "", metadata, client_id)


def _parse(text: str) -> _ProtocolObservation[CursorReportedMetadata]:
    # The shared engine invokes this only after observing the owned parent exit 0.
    report = parse_cursor_json(text, exit_code=0)
    return _ProtocolObservation(
        report.state,
        (report.result_text,) if report.state == "succeeded" else (),
        report.metadata,
        report.session_id,
        report.error_code,
    )


class CursorAdapter(
    _HostProcessAdapter[CursorCapabilities, CursorRun, CursorResult, CursorReportedMetadata]
):
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
            new_capabilities=CursorCapabilities,
            new_run=_new_run,
            new_result=_new_result,
            parse=_parse,
            configuration_error="Invalid Cursor adapter configuration.",
        )

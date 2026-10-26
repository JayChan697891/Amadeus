"""Host-injected Claude protocol observation, never a Claude launcher or authority.

Only trusted host code may supply a fresh owned process capture. No executable,
SDK, network, credential/config discovery, task-text execution or Core dispatch
exists here. A supplied factory is not human authorization. Cancellation concerns
only the owned parent; session IDs correlate records and never authenticate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agentsync.adapters._host_process import (
    _CaptureFactory,
    _HostMarkers,
    _HostProcessAdapter,
    _HostRun,
    _HostStatus,
    _ProtocolObservation,
)
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude_events import ClaudeUsage, parse_claude_jsonl

CaptureFactory = _CaptureFactory
ClaudeStatus = _HostStatus


@dataclass(frozen=True, slots=True)
class ClaudeCapabilities(_HostMarkers):
    supports_start: bool
    max_runs: int
    running_limit: int
    supports_cancel: Literal[True] = field(default=True, init=False)
    supports_server_cancel: Literal[False] = field(default=False, init=False)
    cancel_scope: Literal["owned_parent_only"] = field(default="owned_parent_only", init=False)
    supports_resume: Literal[False] = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class ClaudeRun(_HostRun):
    status: ClaudeStatus


@dataclass(frozen=True, slots=True)
class ClaudeResult(_HostMarkers):
    run: ClaudeRun
    result_text: str = field(default="", repr=False)
    usage: ClaudeUsage | None = None
    client_session_id: str | None = field(default=None, repr=False)


def _new_run(task: AdapterTask, identity: str, started_at: float) -> ClaudeRun:
    return ClaudeRun(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        identity,
        "starting",
        started_at,
    )


def _new_result(
    run: ClaudeRun, messages: tuple[str, ...], usage: ClaudeUsage | None, client_id: str | None
) -> ClaudeResult:
    return ClaudeResult(run, messages[0] if messages else "", usage, client_id)


def _parse(text: str) -> _ProtocolObservation[ClaudeUsage]:
    report = parse_claude_jsonl(text, exit_code=0)
    return _ProtocolObservation(
        report.state,
        (report.result_text,) if report.state == "succeeded" else (),
        report.usage,
        report.session_id,
        report.error_code,
    )


class ClaudeAdapter(_HostProcessAdapter[ClaudeCapabilities, ClaudeRun, ClaudeResult, ClaudeUsage]):
    def __init__(
        self,
        project_id: str,
        session_id: str,
        *,
        factory: CaptureFactory | None = None,
        max_runs: int = 100,
        running_limit: int = 1,
    ):
        super().__init__(
            project_id,
            session_id,
            factory=factory,
            max_runs=max_runs,
            running_limit=running_limit,
            new_capabilities=ClaudeCapabilities,
            new_run=_new_run,
            new_result=_new_result,
            parse=_parse,
            configuration_error="Invalid Claude adapter configuration.",
        )

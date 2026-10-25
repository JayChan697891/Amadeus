"""Typed adapter lifecycle, separate from Core task state and authorization."""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from agentsync.errors import AgentSyncError


def _bounded_text(value: str, limit: int, *, identifier: bool = False) -> None:
    if type(value) is not str or len(value) > limit or "\x00" in value:
        raise AgentSyncError("validation_error", "Invalid adapter input.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise AgentSyncError("validation_error", "Invalid adapter input.") from None
    if len(encoded) > limit or (
        identifier and (not value.strip() or any(ord(c) < 32 for c in value))
    ):
        raise AgentSyncError("validation_error", "Invalid adapter input.")


def _identifier(value: str) -> None:
    _bounded_text(value, 200, identifier=True)


@dataclass(frozen=True, slots=True)
class SimulationMarkers:
    simulated: Literal[True] = field(default=True, init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class AdapterTask:
    project_id: str
    session_id: str
    task_id: str
    request_id: str
    instruction: str = ""
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        for value in (self.project_id, self.session_id, self.task_id, self.request_id):
            _identifier(value)
        _bounded_text(self.instruction, 16000)
        try:
            valid = (
                type(self.timeout_seconds) in (int, float)
                and math.isfinite(self.timeout_seconds)
                and 1 <= self.timeout_seconds <= 7200
            )
        except (OverflowError, ValueError, TypeError):
            valid = False
        if not valid:
            raise AgentSyncError("validation_error", "Invalid adapter timeout.")
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))


@dataclass(frozen=True, slots=True)
class AdapterCapabilities(SimulationMarkers):
    adapter: str = "mock"
    supports_cancel: bool = True
    supports_resume: Literal[False] = field(default=False, init=False)
    supports_usage: Literal[False] = field(default=False, init=False)


RunStatus = Literal["running", "succeeded", "failed", "cancelled", "timed_out"]


@dataclass(frozen=True, slots=True)
class RunSnapshot(SimulationMarkers):
    project_id: str
    session_id: str
    task_id: str
    request_id: str
    run_id: str
    status: RunStatus
    started_at: float
    deadline_at: float
    finished_at: float | None = None
    error_code: str | None = None

    @property
    def timed_out(self) -> bool:
        return self.status == "timed_out"


@dataclass(frozen=True, slots=True)
class AdapterResult(SimulationMarkers):
    run: RunSnapshot
    output: str = ""


class AgentAdapter(ABC):
    @abstractmethod
    async def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def start_task(self, task: AdapterTask) -> RunSnapshot: ...

    @abstractmethod
    async def get_status(self, run_id: str) -> RunSnapshot: ...

    @abstractmethod
    async def get_result(self, run_id: str) -> AdapterResult: ...

    @abstractmethod
    async def cancel_task(self, run_id: str) -> RunSnapshot: ...

    @abstractmethod
    async def resume_task(self, run_id: str) -> RunSnapshot: ...

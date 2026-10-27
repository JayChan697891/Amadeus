"""Bounded instance-local accounting of caller-reported adapter observations.

No measurement, authentication, billing, quota, transport calls or persistence
is inferred. Mock records are counted separately and excluded from protocol
metrics. Elapsed time is a rounded adapter lifecycle interval, never client/API
duration. Output/client IDs/Cursor metadata are neither inspected nor retained.
Only normalized scalar identity, terminal status, timestamps and counters define
replay equality. History is never evicted; cumulative metric overflow rejects
admission atomically. Use synchronously from one owner, without concurrent calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn, cast

from agentsync.adapters.base import AdapterResult, RunSnapshot, _identifier
from agentsync.adapters.claude import ClaudeResult, ClaudeRun
from agentsync.adapters.claude_events import ClaudeUsage
from agentsync.adapters.codex import CodexResult, CodexRun
from agentsync.adapters.codex_events import CodexUsage
from agentsync.adapters.cursor import CursorResult, CursorRun
from agentsync.errors import AgentSyncError

_LIMIT = 2**63 - 1
_KINDS = {
    CodexResult: ("codex", CodexRun),
    ClaudeResult: ("claude", ClaudeRun),
    CursorResult: ("cursor", CursorRun),
    AdapterResult: ("mock", RunSnapshot),
}
_STATUSES = ("succeeded", "failed", "unknown", "cancelled", "timed_out")


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid usage result or options.") from None


def _uint(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _LIMIT:
        _invalid()
    return int(value)


def _time(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        _invalid()
    return float(value)


@dataclass(frozen=True, slots=True)
class MetricTotal:
    value: int | None
    known_sum: int | None
    reported_runs: int
    unknown_runs: int


@dataclass(frozen=True, slots=True)
class UsageSummary:
    project_id: str = field(repr=False)
    total_records: int
    protocol_records: int
    simulated_records: int
    protocol_succeeded: int
    protocol_failed: int
    protocol_unknown: int
    protocol_cancelled: int
    protocol_timed_out: int
    input_tokens: MetricTotal
    output_tokens: MetricTotal
    adapter_elapsed_ms: MetricTotal
    failure_rate: float | None
    failure_rate_denominator: int
    failure_rate_complete: bool
    provenance: Literal["caller_reported_adapter_results"] = field(
        default="caller_reported_adapter_results", init=False
    )
    verification: Literal["unverified"] = field(default="unverified", init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    billing_verified: Literal[False] = field(default=False, init=False)
    cost_usd: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True, repr=False)
class _Record:
    kind: str
    identity: tuple[str, ...]
    status: str
    started_at: float
    finished_at: float | None
    counters: tuple[int | None, ...]
    elapsed_ms: int | None

    @property
    def metrics(self) -> tuple[int | None, ...]:
        return self.counters[:2] + (self.elapsed_ms,)


class UsageLedger:
    def __init__(self, project_id: str, max_records: int = 1000) -> None:
        _identifier(project_id)
        if type(max_records) is not int or not 1 <= max_records <= 10000:
            _invalid()
        self._project_id = project_id
        self._max_records = max_records
        self._records: dict[tuple[str, str], _Record] = {}
        self._sums = [0, 0, 0]

    def _normalize(self, result: Any) -> _Record:
        if type(result) not in _KINDS:
            _invalid()
        kind, run_type = _KINDS[type(result)]
        run = result.run
        if type(run) is not run_type:
            _invalid()
        run = cast(CodexRun | ClaudeRun | CursorRun | RunSnapshot, run)
        identity = (run.project_id, run.session_id, run.task_id, run.request_id, run.run_id)
        for value in identity:
            _identifier(value)
        if run.project_id != self._project_id:
            raise AgentSyncError("namespace_mismatch", "Usage result project does not match.", 403)
        if type(run.status) is not str or run.status not in _STATUSES:
            _invalid()
        start = _time(run.started_at)
        finish = None if run.finished_at is None else _time(run.finished_at)
        elapsed = None
        if finish is not None:
            if finish < start or not math.isfinite((finish - start) * 1000):
                _invalid()
            elapsed = _uint(round((finish - start) * 1000))
        counters: tuple[int | None, ...] = (None, None)
        if kind in {"codex", "claude"} and result.usage is not None:
            usage = result.usage
            if type(usage) is not (CodexUsage if kind == "codex" else ClaudeUsage):
                _invalid()
            counters = (_uint(usage.input_tokens), _uint(usage.output_tokens))
            if kind == "codex":
                codex_usage = cast(CodexUsage, usage)
                extra = (codex_usage.cached_input_tokens, codex_usage.reasoning_output_tokens)
                _uint(codex_usage.cached_input_tokens)
            else:
                claude_usage = cast(ClaudeUsage, usage)
                extra = (
                    claude_usage.cache_read_input_tokens,
                    claude_usage.cache_creation_input_tokens,
                )
            counters += tuple(None if value is None else _uint(value) for value in extra)
        return _Record(kind, identity, run.status, start, finish, counters, elapsed)

    def record_result(self, result: object) -> bool:
        try:
            record = self._normalize(result)
        except (AttributeError, TypeError, ValueError, OverflowError, UnicodeError):
            _invalid()
        key = (record.kind, record.identity[-1])
        previous = self._records.get(key)
        if previous is not None:
            if previous != record:
                raise AgentSyncError(
                    "idempotency_conflict", "Usage run has conflicting observations.", 409
                )
            return False
        if len(self._records) >= self._max_records:
            raise AgentSyncError("history_capacity_exceeded", "Usage history is exhausted.", 409)
        sums = list(self._sums)
        if record.kind != "mock":
            for index, value in enumerate(record.metrics):
                if value is not None:
                    sums[index] += value
                    if sums[index] > _LIMIT:
                        raise AgentSyncError(
                            "usage_overflow", "Usage total exceeds its bound.", 409
                        )
        self._records[key] = record
        self._sums = sums
        return True

    def summary(self) -> UsageSummary:
        records = [record for record in self._records.values() if record.kind != "mock"]
        counts = [sum(record.status == status for record in records) for status in _STATUSES]
        totals = []
        for index, known_sum in enumerate(self._sums):
            reported = sum(record.metrics[index] is not None for record in records)
            unknown = len(records) - reported
            totals.append(
                MetricTotal(
                    known_sum if reported and not unknown else None,
                    known_sum if reported else None,
                    reported,
                    unknown,
                )
            )
        denominator = counts[0] + counts[1]
        complete = bool(records) and denominator == len(records)
        return UsageSummary(
            self._project_id,
            len(self._records),
            len(records),
            len(self._records) - len(records),
            counts[0],
            counts[1],
            counts[2],
            counts[3],
            counts[4],
            totals[0],
            totals[1],
            totals[2],
            counts[1] / denominator if complete else None,
            denominator,
            complete,
        )

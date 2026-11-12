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

import json
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
_JSON_LIMIT = 32 * 1024 * 1024
_CHECKPOINT_FIELDS = {
    "schema_version",
    "project_id",
    "max_records",
    "provenance",
    "verification",
    "real_client_verified",
    "billing_verified",
    "cost_usd",
    "records",
}
_RECORD_FIELDS = {"kind", "identity", "status", "started_at", "finished_at", "counters"}
_KINDS = {
    CodexResult: ("codex", CodexRun),
    ClaudeResult: ("claude", ClaudeRun),
    CursorResult: ("cursor", CursorRun),
    AdapterResult: ("mock", RunSnapshot),
}
_RUN_KINDS = frozenset(kind for kind, _ in _KINDS.values())
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


def _json_preflight(text: str) -> None:
    if type(text) is not str or len(text) > _JSON_LIMIT:
        _invalid()
    if len(text.encode("utf-8")) > _JSON_LIMIT:
        _invalid()
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "{[":
            depth += 1
            if depth > 8:
                _invalid()
        elif char in "}]":
            depth -= 1
            if depth < 0:
                _invalid()


def _json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _json_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        _invalid()
    return value


def _json_constant(_text: str) -> NoReturn:
    _invalid()


def _fields(value: Any, expected: set[str]) -> None:
    if type(value) is not dict or set(value) != expected:
        _invalid()


def _checkpoint_result(record: Any) -> object:
    _fields(record, _RECORD_FIELDS)
    kind, identity, counters = record["kind"], record["identity"], record["counters"]
    if (
        type(kind) is not str
        or kind not in _RUN_KINDS
        or type(identity) is not list
        or len(identity) != 5
        or type(counters) is not list
        or len(counters) not in (2, 4)
    ):
        _invalid()
    if len(counters) == 2:
        if any(value is not None for value in counters):
            _invalid()
    elif kind not in {"codex", "claude"}:
        _invalid()
    args = dict(
        zip(("project_id", "session_id", "task_id", "request_id", "run_id"), identity, strict=True)
    )
    args.update(
        status=record["status"], started_at=record["started_at"], finished_at=record["finished_at"]
    )
    if kind == "codex":
        usage = (
            None
            if len(counters) == 2
            else CodexUsage(counters[0], counters[2], counters[1], counters[3])
        )
        return CodexResult(CodexRun(**args), usage=usage)
    if kind == "claude":
        claude_usage = None if len(counters) == 2 else ClaudeUsage(*counters)
        return ClaudeResult(ClaudeRun(**args), usage=claude_usage)
    if kind == "cursor":
        return CursorResult(CursorRun(**args))
    return AdapterResult(RunSnapshot(**args, deadline_at=record["started_at"]))


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


@dataclass(frozen=True, slots=True)
class UsageRunSummary:
    kind: str
    run_id: str = field(repr=False)
    status: str
    simulated: bool
    input_tokens: int | None
    output_tokens: int | None
    adapter_elapsed_ms: int | None
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

    def to_json(self) -> str:
        """Export unverified normalized observations, without output/client metadata.

        This performs no I/O. Caller-supplied identity text is retained verbatim;
        it is not authenticated or guaranteed to be free of caller secrets.
        """
        document = {
            "schema_version": 1,
            "project_id": self._project_id,
            "max_records": self._max_records,
            "provenance": "caller_reported_adapter_results",
            "verification": "unverified",
            "real_client_verified": False,
            "billing_verified": False,
            "cost_usd": None,
            "records": [
                {
                    "kind": record.kind,
                    "identity": record.identity,
                    "status": record.status,
                    "started_at": record.started_at,
                    "finished_at": record.finished_at,
                    "counters": record.counters,
                }
                for record in self._records.values()
            ],
        }
        try:
            text = json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            _json_preflight(text)
            return text
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
            _invalid()

    @classmethod
    def from_json(cls, project_id: str, text: str) -> UsageLedger:
        """Restore a new private ledger; validate and recompute every total.

        Checkpoints are bounded to 32 MiB UTF-8 and depth eight. They convey
        caller observations, without authentication, billing verification or I/O.
        """
        try:
            _identifier(project_id)
        except AgentSyncError:
            _invalid()
        try:
            _json_preflight(text)
            document = json.loads(
                text,
                object_pairs_hook=_json_members,
                parse_float=_json_float,
                parse_constant=_json_constant,
            )
            _fields(document, _CHECKPOINT_FIELDS)
            if (
                type(document["schema_version"]) is not int
                or document["schema_version"] != 1
                or document["provenance"] != "caller_reported_adapter_results"
                or document["verification"] != "unverified"
                or document["real_client_verified"] is not False
                or document["billing_verified"] is not False
                or document["cost_usd"] is not None
                or type(document["records"]) is not list
            ):
                _invalid()
            _identifier(document["project_id"])
            if document["project_id"] != project_id:
                raise AgentSyncError(
                    "namespace_mismatch", "Usage result project does not match.", 403
                )
            ledger = cls(project_id, document["max_records"])
            if len(document["records"]) > ledger._max_records:
                _invalid()
            for record in document["records"]:
                if not ledger.record_result(_checkpoint_result(record)):
                    _invalid()
            return ledger
        except AgentSyncError as exc:
            if exc.code == "validation_error":
                _invalid()
            raise
        except (TypeError, ValueError, OverflowError, UnicodeError, RecursionError):
            _invalid()

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
        return self._record(record)

    def merged_with(self, other: UsageLedger) -> tuple[UsageLedger, int]:
        """Return a merged copy and its number of newly admitted observations."""
        if type(other) is not UsageLedger:
            _invalid()
        if self._project_id != other._project_id:
            raise AgentSyncError("namespace_mismatch", "Usage result project does not match.", 403)
        merged = UsageLedger(self._project_id, self._max_records)
        merged._records = self._records.copy()
        merged._sums = self._sums.copy()
        added = sum(merged._record(record) for record in other._records.values())
        return merged, added

    def _record(self, record: _Record) -> bool:
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

    def get_run(self, kind: str, run_id: str) -> UsageRunSummary:
        """Read one normalized observation without exposing its other identifiers."""
        if type(kind) is not str or kind not in _RUN_KINDS:
            _invalid()
        _identifier(run_id)
        record = self._records.get((kind, run_id))
        if record is None:
            raise AgentSyncError("not_found", "Usage run was not found.", 404)
        simulated = kind == "mock"
        input_tokens, output_tokens = record.counters[:2]
        return UsageRunSummary(
            kind,
            run_id,
            record.status,
            simulated,
            input_tokens,
            output_tokens,
            None if simulated else record.elapsed_ms,
        )

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

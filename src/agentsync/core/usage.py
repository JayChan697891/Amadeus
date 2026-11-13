"""Project-owner persistence for adapter and local model-provider observations."""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from agentsync.adapters.approved_launch import ClientKind, digest
from agentsync.errors import AgentSyncError
from agentsync.model_usage import FlatRate
from agentsync.models import StrictModel
from agentsync.providers.base import ProviderKind
from agentsync.usage import (
    _LIMIT,
    MetricTotal,
    UsageLedger,
    _json_constant,
    _json_float,
    _json_members,
    _json_preflight,
)

_MAX_IMPORT_BYTES = 48 * 1024
_MAX_STORED_BYTES = 512 * 1024
_PROVIDER_TERMINAL_HEADROOM = 320  # Reserve space for a terminal update before any call.
RELAY_USAGE_SOURCE = "controlled_relay_receipts"
PROVIDER_USAGE_SOURCE = "local_provider_calls"
_METRICS = ("input_tokens", "output_tokens", "adapter_elapsed_ms")
_PROVIDER_COUNTERS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_tokens",
)
_PROVIDER_METRICS = (*_PROVIDER_COUNTERS, "elapsed_ms", "estimated_cost_picodollars")
_Digest = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
_Counter = Annotated[int, Field(ge=0, le=_LIMIT)]
_Rate = Annotated[int, Field(ge=0, le=10**12)]
_ESTIMATE_LIMIT = 2 * _LIMIT * 10**12


class ProviderCallObservation(StrictModel):
    call_id: _Digest
    binding_sha256: _Digest
    provider: ProviderKind | Literal["mock"]
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    kind: Literal["decomposition", "roles", "handoff"]
    input_rate: _Rate | None = None
    output_rate: _Rate | None = None
    status: Literal["unknown", "succeeded", "failed", "cancelled"] = "unknown"
    remote_outcome: Literal[
        "unknown", "response_received", "http_error", "not_sent", "simulated"
    ] = "unknown"
    error_code: str | None = Field(default=None, pattern=r"^[a-z_]{1,64}$")
    http_status: int | None = Field(default=None, ge=100, le=599)
    retry_after_seconds: int | None = Field(default=None, ge=0, le=2**31 - 1)
    input_tokens: _Counter | None = None
    output_tokens: _Counter | None = None
    total_tokens: _Counter | None = None
    cache_read_input_tokens: _Counter | None = None
    cache_creation_input_tokens: _Counter | None = None
    reasoning_tokens: _Counter | None = None
    elapsed_ms: _Counter | None = None

    @model_validator(mode="after")
    def consistent_observation(self) -> "ProviderCallObservation":
        if (
            (self.input_rate is None) != (self.output_rate is None)
            or (self.status == "unknown") != (self.elapsed_ms is None)
            or (self.status in {"failed", "cancelled"}) != (self.error_code is not None)
            or (self.remote_outcome == "http_error") != (self.http_status is not None)
            or (self.retry_after_seconds is not None and self.http_status not in {429, 503})
            or (self.status == "unknown" and self.remote_outcome != "unknown")
            or (
                self.status == "succeeded"
                and self.remote_outcome not in {"response_received", "simulated"}
            )
            or (self.provider == "mock" and self.remote_outcome not in {"unknown", "simulated"})
            or (self.provider != "mock" and self.remote_outcome == "simulated")
            or (self.provider == "mock" and self.input_rate is not None)
            or (
                self.remote_outcome != "response_received"
                and any(getattr(self, name) is not None for name in _PROVIDER_COUNTERS)
            )
        ):
            raise ValueError("Invalid provider usage observation.")
        return self

    @property
    def estimated_cost_picodollars(self) -> int | None:
        if self.input_rate is None or self.output_rate is None:
            return None
        return FlatRate(self.input_rate, self.output_rate).estimate(
            self.input_tokens, self.output_tokens
        )

    def public(self) -> dict[str, Any]:
        return self.model_dump(exclude={"binding_sha256"}) | {
            "provenance": PROVIDER_USAGE_SOURCE,
            "field_provenance": {
                "elapsed_ms": "local_monotonic" if self.elapsed_ms is not None else "unknown",
                **{
                    name: "provider_reported" if getattr(self, name) is not None else "unknown"
                    for name in _PROVIDER_COUNTERS
                },
                "estimated_cost_picodollars": "caller_flat_rates"
                if self.estimated_cost_picodollars is not None
                else "unknown",
            },
            "estimated_cost_picodollars": self.estimated_cost_picodollars,
            "estimate_rate_unit": "microdollars_per_million_reported_tokens"
            if self.input_rate is not None
            else None,
            "verification": "unverified",
            "billing_verified": False,
            "cost_usd": None,
        }


class RelayUsageObservation(StrictModel):
    task_id: str = Field(min_length=1, max_length=200)
    leg: Literal["first", "second"]
    kind: ClientKind
    agent_sha256: _Digest
    session_sha256: _Digest
    launch_request_sha256: _Digest
    launch_plan_sha256: _Digest
    consent_sha256: _Digest
    binding: Literal["dispatch_pinned", "legacy_two_leg"]
    terminal_sha256: _Digest | None
    run_sha256: _Digest | None
    status: Literal["succeeded", "failed", "unknown", "timed_out"]
    input_tokens: _Counter | None
    output_tokens: _Counter | None
    adapter_elapsed_ms: _Counter | None

    @model_validator(mode="after")
    def consistent_observation(self) -> "RelayUsageObservation":
        if (
            (self.terminal_sha256 is None) != (self.run_sha256 is None)
            or (
                self.terminal_sha256 is None
                and (
                    self.status != "unknown"
                    or any(getattr(self, name) is not None for name in _METRICS)
                )
            )
            or (
                self.kind == "cursor"
                and (self.input_tokens is not None or self.output_tokens is not None)
            )
        ):
            raise ValueError("Invalid relay usage observation.")
        return self

    def key(self, project_id: str) -> str:
        return digest([project_id, self.task_id, self.leg, self.launch_request_sha256])

    def binding_fields(self) -> tuple[str, ...]:
        return (
            self.task_id,
            self.leg,
            self.kind,
            self.agent_sha256,
            self.session_sha256,
            self.launch_request_sha256,
            self.launch_plan_sha256,
            self.consent_sha256,
            self.binding,
        )

    def public(self, project_id: str) -> dict[str, Any]:
        return {
            "run_id": self.key(project_id),
            "task_id": self.task_id,
            "leg": self.leg,
            "kind": self.kind,
            "status": self.status,
            "terminal_recorded": self.terminal_sha256 is not None,
            "binding": self.binding,
            "started_at": None,
            "finished_at": None,
            **{name: getattr(self, name) for name in _METRICS},
            "field_provenance": {
                "started_at": "unavailable",
                "finished_at": "unavailable",
                **{
                    name: (
                        "adapter_lifecycle" if name == "adapter_elapsed_ms" else "client_reported"
                    )
                    if getattr(self, name) is not None
                    else "unavailable"
                    for name in _METRICS
                },
            },
            **_relay_provenance(),
        }


def _relay_provenance() -> dict[str, Any]:
    return {
        "provenance": RELAY_USAGE_SOURCE,
        "verification": "unverified",
        "real_client_verified": False,
        "billing_verified": False,
        "cost_usd": None,
    }


def _metric(values: list[int | None], *, limit: int = _LIMIT) -> MetricTotal:
    known = [value for value in values if value is not None]
    total = sum(known)
    if total > limit:
        raise AgentSyncError("usage_overflow", "Usage total exceeds its bound.", 409)
    unknown = len(values) - len(known)
    return MetricTotal(
        total if known and not unknown else None, total if known else None, len(known), unknown
    )


@dataclass(slots=True)
class _ProjectUsage:
    caller: UsageLedger
    relay: dict[tuple[str, str], RelayUsageObservation] = field(default_factory=dict)
    provider: dict[str, ProviderCallObservation] = field(default_factory=dict)

    @classmethod
    def load(cls, db: sqlite3.Connection, project_id: str) -> "_ProjectUsage":
        row = db.execute(
            "SELECT checkpoint FROM project_usage WHERE project_id=?", (project_id,)
        ).fetchone()
        if row is None:
            return cls(UsageLedger(project_id))
        try:
            raw = row["checkpoint"]
            if type(raw) is not str or len(raw.encode("utf-8")) > _MAX_STORED_BYTES:
                raise ValueError
            _json_preflight(raw)
            document = json.loads(
                raw,
                object_pairs_hook=_json_members,
                parse_float=_json_float,
                parse_constant=_json_constant,
            )
            if (
                type(document) is dict
                and type(document.get("schema_version")) is int
                and document["schema_version"] in (2, 3)
            ):
                v3 = document["schema_version"] == 3
                fields = {"schema_version", "caller", RELAY_USAGE_SOURCE}
                if v3:
                    fields.add(PROVIDER_USAGE_SOURCE)
                if (
                    set(document) != fields
                    or type(document[RELAY_USAGE_SOURCE]) is not list
                    or (v3 and type(document[PROVIDER_USAGE_SOURCE]) is not list)
                ):
                    raise ValueError
                caller = UsageLedger.from_json(
                    project_id, json.dumps(document["caller"], ensure_ascii=False)
                )
                history = cls(caller)
                for item in document[RELAY_USAGE_SOURCE]:
                    record = RelayUsageObservation.model_validate(item)
                    index = (record.task_id, record.leg)
                    if index in history.relay:
                        raise ValueError
                    history.relay[index] = record
                for item in document.get(PROVIDER_USAGE_SOURCE, []):
                    call = ProviderCallObservation.model_validate(item)
                    if call.call_id in history.provider:
                        raise ValueError
                    history.provider[call.call_id] = call
                history._validate_totals()
                return history
            return cls(UsageLedger.from_json(project_id, raw))
        except (AgentSyncError, ValueError, RecursionError):
            raise AgentSyncError("storage_error", "Stored usage history is invalid.", 503) from None

    def _relay_totals(self) -> dict[str, MetricTotal]:
        return {
            name: _metric([getattr(record, name) for record in self.relay.values()])
            for name in _METRICS
        }

    def _provider_totals(self) -> dict[str, MetricTotal]:
        records = [record for record in self.provider.values() if record.provider != "mock"]
        # Bound the sum by the number and maximum size of admitted records. A
        # provider response must never overflow and strand its already-sent call.
        return {
            name: _metric(
                [getattr(record, name) for record in records],
                limit=(
                    _ESTIMATE_LIMIT if name == "estimated_cost_picodollars" else _LIMIT
                ) * self.caller._max_records,
            )
            for name in _PROVIDER_METRICS
        }

    def _validate_totals(self) -> None:
        if (
            self.caller.summary().total_records + len(self.relay) + len(self.provider)
            > self.caller._max_records
        ):
            raise AgentSyncError("history_capacity_exceeded", "Usage history is exhausted.", 409)
        self._relay_totals()
        self._provider_totals()

    def save(self, db: sqlite3.Connection, project_id: str, now: float) -> None:
        self._validate_totals()
        document = self.caller.to_json()
        if self.relay or self.provider:
            stored: dict[str, Any] = {
                "schema_version": 3 if self.provider else 2,
                "caller": json.loads(document),
                RELAY_USAGE_SOURCE: [record.model_dump() for record in self.relay.values()],
            }
            if self.provider:
                stored[PROVIDER_USAGE_SOURCE] = [
                    record.model_dump() for record in self.provider.values()
                ]
            document = json.dumps(
                stored,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        headroom = _PROVIDER_TERMINAL_HEADROOM * sum(
            call.status == "unknown" for call in self.provider.values()
        )
        if len(document.encode("utf-8")) + headroom > _MAX_STORED_BYTES:
            raise AgentSyncError("history_capacity_exceeded", "Usage history is exhausted.", 409)
        db.execute(
            "INSERT INTO project_usage(project_id,checkpoint,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET "
            "checkpoint=excluded.checkpoint, updated_at=excluded.updated_at",
            (project_id, document, now),
        )

    def merge_relay(self, record: RelayUsageObservation) -> str:
        index = (record.task_id, record.leg)
        previous = self.relay.get(index)
        if previous is None:
            self.relay[index] = record
            return "added"
        if previous.binding_fields() == record.binding_fields():
            if previous == record or record.terminal_sha256 is None:
                return "unchanged"
            if previous.terminal_sha256 is None:
                self.relay[index] = record
                return "updated"
        raise AgentSyncError(
            "idempotency_conflict", "Relay usage has conflicting observations.", 409
        )

    def summary(self) -> dict[str, Any]:
        records = list(self.relay.values())
        counts = {
            status: sum(record.status == status for record in records)
            for status in ("succeeded", "failed", "unknown", "timed_out")
        }
        failures = counts["failed"] + counts["timed_out"]
        denominator = counts["succeeded"] + failures
        complete = denominator > 0 and counts["unknown"] == 0
        provider_counts = {
            status: sum(
                call.status == status for call in self.provider.values() if call.provider != "mock"
            )
            for status in ("succeeded", "failed", "cancelled", "unknown")
        }
        provider_denominator = provider_counts["succeeded"] + provider_counts["failed"]
        provider_complete = bool(provider_denominator) and not (
            provider_counts["unknown"] or provider_counts["cancelled"]
        )
        return {
            **asdict(self.caller.summary()),
            RELAY_USAGE_SOURCE: {
                "total_records": len(records),
                "terminal_records": sum(record.terminal_sha256 is not None for record in records),
                "statuses": counts,
                "failure_rate": failures / denominator if complete else None,
                "failure_rate_denominator": denominator,
                "failure_rate_complete": complete,
                **{name: asdict(total) for name, total in self._relay_totals().items()},
                **_relay_provenance(),
            },
            PROVIDER_USAGE_SOURCE: {
                "total_records": len(self.provider),
                "simulated_records": sum(
                    call.provider == "mock" for call in self.provider.values()
                ),
                "simulated_statuses": {
                    status: sum(
                        call.status == status for call in self.provider.values()
                        if call.provider == "mock"
                    )
                    for status in provider_counts
                },
                "statuses": provider_counts,
                "remote_unknown": sum(
                    call.remote_outcome == "unknown"
                    for call in self.provider.values()
                    if call.provider != "mock"
                ),
                "local_failure_rate": provider_counts["failed"] / provider_denominator
                if provider_complete
                else None,
                "local_failure_rate_denominator": provider_denominator,
                "local_failure_rate_complete": provider_complete,
                **{name: asdict(total) for name, total in self._provider_totals().items()},
                "provenance": PROVIDER_USAGE_SOURCE,
                "estimate_basis": "caller_flat_rates",
                "billing_verified": False,
                "cost_usd": None,
            },
        }


class UsageMixin:
    """Use the same authenticated owner transaction as other owner operations."""

    @staticmethod
    def _owner_import_usage_checkpoint(
        db: sqlite3.Connection, p: dict[str, Any], now: float
    ) -> dict[str, Any]:
        project_id, checkpoint = p["project_id"], p["checkpoint"]
        if len(checkpoint.encode("utf-8")) > _MAX_IMPORT_BYTES:
            raise AgentSyncError("validation_error", "Usage checkpoint exceeds the import limit.")
        incoming = UsageLedger.from_json(project_id, checkpoint)
        history = _ProjectUsage.load(db, project_id)
        history.caller, added = history.caller.merged_with(incoming)
        if added:
            history.save(db, project_id, now)
        return {
            "added_records": added,
            "duplicate_records": incoming.summary().total_records - added,
        }

    @staticmethod
    def _owner_get_usage_summary(
        db: sqlite3.Connection, p: dict[str, Any], _: float
    ) -> dict[str, Any]:
        return _ProjectUsage.load(db, p["project_id"]).summary()

    @staticmethod
    def _owner_get_usage_run(db: sqlite3.Connection, p: dict[str, Any], _: float) -> dict[str, Any]:
        project_id, kind, run_id = p["project_id"], p["kind"], p["run_id"]
        history = _ProjectUsage.load(db, project_id)
        if p["provenance"] != RELAY_USAGE_SOURCE:
            return asdict(history.caller.get_run(kind, run_id))
        for record in history.relay.values():
            if record.kind == kind and record.key(project_id) == run_id:
                return record.public(project_id)
        raise AgentSyncError("not_found", "Usage run was not found.", 404)

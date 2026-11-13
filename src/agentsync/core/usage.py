"""Project-owner persistence for unverified adapter usage observations."""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from agentsync.adapters.approved_launch import ClientKind, digest
from agentsync.errors import AgentSyncError
from agentsync.models import StrictModel
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
RELAY_USAGE_SOURCE = "controlled_relay_receipts"
_METRICS = ("input_tokens", "output_tokens", "adapter_elapsed_ms")
_Digest = Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]
_Counter = Annotated[int, Field(ge=0, le=_LIMIT)]


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


def _relay_metric(records: list[RelayUsageObservation], name: str) -> MetricTotal:
    known = [value for record in records if (value := getattr(record, name)) is not None]
    total = sum(known)
    if total > _LIMIT:
        raise AgentSyncError("usage_overflow", "Usage total exceeds its bound.", 409)
    unknown = len(records) - len(known)
    return MetricTotal(
        total if known and not unknown else None, total if known else None, len(known), unknown
    )


@dataclass(slots=True)
class _ProjectUsage:
    caller: UsageLedger
    relay: dict[tuple[str, str], RelayUsageObservation] = field(default_factory=dict)

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
                and document["schema_version"] == 2
            ):
                if (
                    set(document) != {"schema_version", "caller", RELAY_USAGE_SOURCE}
                    or type(document[RELAY_USAGE_SOURCE]) is not list
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
                history._validate_totals()
                return history
            return cls(UsageLedger.from_json(project_id, raw))
        except (AgentSyncError, ValueError, RecursionError):
            raise AgentSyncError("storage_error", "Stored usage history is invalid.", 503) from None

    def _validate_totals(self) -> dict[str, MetricTotal]:
        if self.caller.summary().total_records + len(self.relay) > self.caller._max_records:
            raise AgentSyncError("history_capacity_exceeded", "Usage history is exhausted.", 409)
        records = list(self.relay.values())
        return {name: _relay_metric(records, name) for name in _METRICS}

    def save(self, db: sqlite3.Connection, project_id: str, now: float) -> None:
        self._validate_totals()
        document = self.caller.to_json()
        if self.relay:
            document = json.dumps(
                {
                    "schema_version": 2,
                    "caller": json.loads(document),
                    RELAY_USAGE_SOURCE: [record.model_dump() for record in self.relay.values()],
                },
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        if len(document.encode("utf-8")) > _MAX_STORED_BYTES:
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
        return {
            **asdict(self.caller.summary()),
            RELAY_USAGE_SOURCE: {
                "total_records": len(records),
                "terminal_records": sum(record.terminal_sha256 is not None for record in records),
                "statuses": counts,
                "failure_rate": failures / denominator if complete else None,
                "failure_rate_denominator": denominator,
                "failure_rate_complete": complete,
                **{name: asdict(total) for name, total in self._validate_totals().items()},
                **_relay_provenance(),
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

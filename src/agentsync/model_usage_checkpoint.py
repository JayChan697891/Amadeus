"""Round-trip sanitized model usage observations, without restoring a call budget."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, NoReturn

from agentsync.adapters.base import _identifier
from agentsync.errors import AgentSyncError
from agentsync.model_usage import ModelCallMeter, ModelUsageSummary

MODEL_CHECKPOINT_LIMIT = 4096
_COUNT_LIMIT = 4096
_TOKENS_LIMIT = _COUNT_LIMIT * (2**63 - 1)
_ESTIMATE_LIMIT = 2 * _TOKENS_LIMIT * 10**12
_COUNT_FIELDS = (
    "completed_invocations",
    "in_flight",
    "responses",
    "failures",
    "cancelled",
    "mock_responses",
    "response_tokens_unknown",
    "estimate_unknown_invocations",
)
_OPTIONAL_TOTALS = {
    "reported_input_tokens": _TOKENS_LIMIT,
    "reported_output_tokens": _TOKENS_LIMIT,
    "estimated_cost_picodollars": _ESTIMATE_LIMIT,
}
_ENVELOPE = {"schema_version", "project_id", "provenance", "verification", "summary"}
_MARKERS = {"billing_verified": False, "cost_usd": None, "estimate_basis": "caller_flat_rates"}
_SUMMARY_FIELDS = set(_COUNT_FIELDS) | _OPTIONAL_TOTALS.keys() | _MARKERS.keys() | {"elapsed_ms"}
_PROVENANCE = "local_model_meter_observation"


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid model usage checkpoint.") from None


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _uint(value: object, limit: int) -> int:
    if type(value) is not int or not 0 <= value <= limit:
        _invalid()
    return value


def dump_model_usage(project_id: str, meter: ModelCallMeter) -> str:
    """Export counts only; in-flight calls are historical observations on readback."""
    _identifier(project_id)
    if type(meter) is not ModelCallMeter:
        _invalid()
    summary = asdict(meter.summary())
    del summary["local_failure_rate"]  # Recomputed from counts on readback.
    return json.dumps(
        {
            "schema_version": 1,
            "project_id": project_id,
            "provenance": _PROVENANCE,
            "verification": "unverified",
            "summary": summary,
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def load_model_usage(project_id: str, text: str) -> ModelUsageSummary:
    """Load one project-labeled snapshot; never resume calls, billing or allowance."""
    _identifier(project_id)
    if type(text) is not str or len(text) > MODEL_CHECKPOINT_LIMIT or not text.isascii():
        _invalid()
    try:
        document = json.loads(text, object_pairs_hook=_members)
    except (ValueError, RecursionError):
        _invalid()
    if (
        type(document) is not dict
        or set(document) != _ENVELOPE
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["project_id"] != project_id
        or document["provenance"] != _PROVENANCE
        or document["verification"] != "unverified"
    ):
        _invalid()
    row = document["summary"]
    if (
        type(row) is not dict
        or set(row) != _SUMMARY_FIELDS
        or any(
            type(row[key]) is not type(value) or row[key] != value
            for key, value in _MARKERS.items()
        )
    ):
        _invalid()
    counts = {key: _uint(row[key], _COUNT_LIMIT) for key in _COUNT_FIELDS}
    totals = {
        key: None if row[key] is None else _uint(row[key], limit)
        for key, limit in _OPTIONAL_TOTALS.items()
    }
    completed, active, responses = (counts[key] for key in _COUNT_FIELDS[:3])
    failures, cancelled, mock = (counts[key] for key in _COUNT_FIELDS[3:6])
    tokens_unknown, estimate_unknown = (counts[key] for key in _COUNT_FIELDS[6:])
    external = responses - mock
    unavoidable_unknown = failures + cancelled + active
    estimate = totals["estimated_cost_picodollars"]
    input_tokens = totals["reported_input_tokens"]
    output_tokens = totals["reported_output_tokens"]
    elapsed_ms = _uint(row["elapsed_ms"], 2**63 - 1)
    if (
        completed + active > _COUNT_LIMIT
        or completed != responses + failures + cancelled
        or not 0 <= tokens_unknown <= external
        or not unavoidable_unknown + tokens_unknown
        <= estimate_unknown
        <= unavoidable_unknown + external
        or (estimate is not None) != (external > 0 and estimate_unknown == 0)
        or (external == 0 and (input_tokens is not None or output_tokens is not None))
        or (
            external > 0 and tokens_unknown == 0 and (input_tokens is None or output_tokens is None)
        )
        or (
            external > 0
            and (input_tokens is None or output_tokens is None)
            and tokens_unknown != external
        )
        or (completed == 0 and elapsed_ms != 0)
    ):
        _invalid()
    observed = responses + failures
    return ModelUsageSummary(
        completed_invocations=completed,
        in_flight=active,
        responses=responses,
        failures=failures,
        cancelled=cancelled,
        mock_responses=mock,
        local_failure_rate=failures / observed if observed else None,
        elapsed_ms=elapsed_ms,
        reported_input_tokens=input_tokens,
        reported_output_tokens=output_tokens,
        response_tokens_unknown=tokens_unknown,
        estimated_cost_picodollars=estimate,
        estimate_unknown_invocations=estimate_unknown,
    )

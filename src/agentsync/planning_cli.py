"""Bounded stdin-only dispatch advice; no state, authentication or execution."""

import json
import math
import sys
from dataclasses import asdict
from typing import Any

from agentsync.dispatch_planning import plan_dispatches
from agentsync.errors import AgentSyncError
from agentsync.retry_planning import RetryPolicy, plan_retry

MAX_INPUT_BYTES = 1024 * 1024
_REQUIRED = {"state", "project_id", "worker_agent_ids", "now"}
_OPTIONAL = {"global_limit", "per_agent_limit", "limit", "required_capabilities"}
_RETRY_REQUIRED = {"attempts_used", "failure_kind", "outcome_confirmed", "now"}
_RETRY_OPTIONAL = {"deadline", "retry_after_seconds", "remaining_attempt_budget"}
_RETRY_POLICY = {"max_attempts", "base_delay_seconds", "max_delay_seconds"}


def invalid_input() -> int:
    print(json.dumps({"error": {"code": "invalid_input", "message": "Invalid planning input."}}))
    return 2


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_text: str) -> None:
    raise ValueError


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError
    return value


def _read_payload(limit: int) -> dict[str, Any]:
    raw = sys.stdin.buffer.read(limit + 1)
    if len(raw) > limit:
        raise ValueError
    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_members,
        parse_constant=_constant,
        parse_float=_finite,
    )
    if type(payload) is not dict:
        raise ValueError
    return payload


def run_plan_cli() -> int:
    try:
        payload = _read_payload(MAX_INPUT_BYTES)
        if (
            not _REQUIRED <= payload.keys()
            or payload.keys() - _REQUIRED - _OPTIONAL
            or type(payload["worker_agent_ids"]) is not list
        ):
            raise ValueError
        options = {key: payload[key] for key in _OPTIONAL if key in payload}
        if "required_capabilities" in options:
            requirements = options["required_capabilities"]
            if type(requirements) is not dict or any(
                type(value) is not list for value in requirements.values()
            ):
                raise ValueError
            options["required_capabilities"] = {
                key: tuple(value) for key, value in requirements.items()
            }
        plan = plan_dispatches(
            payload["state"],
            project_id=payload["project_id"],
            worker_agent_ids=tuple(payload["worker_agent_ids"]),
            now=payload["now"],
            **options,
        )
        output = json.dumps(asdict(plan), allow_nan=False)
    except (
        AgentSyncError,
        AttributeError,
        OSError,
        ValueError,
        TypeError,
        UnicodeError,
        OverflowError,
        RecursionError,
    ):
        return invalid_input()
    print(output)
    return 0


def run_retry_plan_cli() -> int:
    """Emit retry advice from a caller observation without waiting or dispatching."""
    try:
        payload = _read_payload(16 * 1024)
        policy = payload.pop("policy", {})
        if (
            not _RETRY_REQUIRED <= payload.keys()
            or payload.keys() - _RETRY_REQUIRED - _RETRY_OPTIONAL
            or type(policy) is not dict
            or policy.keys() - _RETRY_POLICY
        ):
            raise ValueError
        decision = plan_retry(RetryPolicy(**policy), **payload)
        output = json.dumps(asdict(decision), allow_nan=False)
    except (
        AgentSyncError,
        AttributeError,
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
    ):
        return invalid_input()
    print(output)
    return 0

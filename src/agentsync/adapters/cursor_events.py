"""Bounded standalone Cursor ``--print --output-format json`` observations.

Only the documented successful terminal object is supported, never stream-json,
tool events or deltas. Caller-reported identifiers and timings are not authority,
authentication, billing evidence or proof that a real Cursor client ran.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn

from agentsync.errors import AgentSyncError


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid Cursor JSON input.") from None


def _unsupported() -> NoReturn:
    raise AgentSyncError("unsupported_event", "Unsupported Cursor JSON subset.") from None


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    _invalid()


def _json(text: str) -> dict[str, Any] | None:
    if type(text) is not str:
        _invalid()
    try:
        if len(text) > 1024 * 1024 or len(text.encode("utf-8")) > 1024 * 1024 or "\x00" in text:
            _invalid()
    except UnicodeError:
        _invalid()
    if not text.strip():
        return None
    try:
        value = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError):
        _invalid()
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            _invalid()
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for pair in item.items() for v in pair)
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            try:
                if len(item.encode("utf-8")) > 65536 or "\x00" in item:
                    _invalid()
            except UnicodeError:
                _invalid()
        elif isinstance(item, float) and not math.isfinite(item):
            _invalid()
    if type(value) is not dict:
        _invalid()
    return value


def _identifier(value: Any) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or any(ord(c) < 32 for c in value)
        or len(value.encode("utf-8")) > 200
    ):
        _invalid()
    return str(value)


def _uint(value: Any) -> int:
    if type(value) is not int or not 0 <= value < 2**63:
        _invalid()
    return int(value)


@dataclass(frozen=True, slots=True)
class CursorReportedMetadata:
    """Caller-reported elapsed milliseconds and optional correlation ID only."""

    duration_ms: int
    duration_api_ms: int
    request_id: str | None = field(default=None, repr=False)
    caller_reported: Literal[True] = field(default=True, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)


@dataclass(frozen=True, slots=True)
class CursorReport:
    session_id: str | None = field(repr=False)
    state: Literal["succeeded", "failed", "incomplete"]
    result_text: str = field(repr=False)
    metadata: CursorReportedMetadata | None
    error_code: str | None
    protocol_only: Literal[True] = field(default=True, init=False)
    provenance: Literal["caller_supplied"] = field(default="caller_supplied", init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)


def parse_cursor_json(text: str, *, exit_code: int | None = None) -> CursorReport:
    """Require a supported terminal object plus observed exit zero for success.

    Input is capped at 1 MiB, strings at 64 KiB and nesting at depth 32.
    Unsupported schemas raise instead of being treated as successful responses.
    Empty stdout is allowed because unsuccessful clients may emit stderr only.
    """
    if exit_code is not None and (type(exit_code) is not int or not -(2**63) <= exit_code < 2**63):
        _invalid()
    value = _json(text)
    if value is None:
        if exit_code is not None and exit_code != 0:
            return CursorReport(None, "failed", "", None, "process_failed")
        return CursorReport(None, "incomplete", "", None, "incomplete_response")
    kind = _identifier(value.get("type"))
    if kind != "result":
        _unsupported()
    if _identifier(value.get("subtype")) != "success":
        _unsupported()
    if type(value.get("is_error")) is not bool:
        _invalid()
    if value["is_error"]:
        _unsupported()
    if type(value.get("result")) is not str:
        _invalid()
    session_id = _identifier(value.get("session_id"))
    metadata = CursorReportedMetadata(
        _uint(value.get("duration_ms")),
        _uint(value.get("duration_api_ms")),
        _identifier(value["request_id"]) if "request_id" in value else None,
    )
    if exit_code is not None and exit_code != 0:
        return CursorReport(session_id, "failed", "", metadata, "process_failed")
    if exit_code is None:
        return CursorReport(session_id, "incomplete", "", metadata, "process_unknown")
    return CursorReport(session_id, "succeeded", value["result"], metadata, None)

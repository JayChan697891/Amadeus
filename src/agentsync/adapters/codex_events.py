"""Caller-supplied Codex JSONL projection; no client execution or task verification.

Fixtures and parsed events are protocol evidence only, never authenticated client
captures. This bounded single-turn subset does not execute tool contents, retain
commands/errors, authorize Core actions, or interpret usage as verified billing.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn

from agentsync.errors import AgentSyncError

_ITEM_TYPES = frozenset(
    {
        "agent_message",
        "reasoning",
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "todo_list",
        "error",
    }
)


def _sequence_error() -> NoReturn:
    raise AgentSyncError("invalid_event_sequence", "Invalid Codex event sequence.")


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid Codex event input.") from None


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _invalid()
        value[key] = item
    return value


def _constant(_value: str) -> Any:
    _invalid()


def _validate_json(value: Any) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            _invalid()
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
            pending.extend((key, depth + 1) for key in item)
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            try:
                item.encode("utf-8")
            except UnicodeError:
                _invalid()
            if "\x00" in item:
                _invalid()
        elif isinstance(item, float) and not math.isfinite(item):
            _invalid()


def _identifier(value: Any) -> str:
    if type(value) is not str or not value.strip() or any(ord(c) < 32 for c in value):
        _invalid()
    if len(value.encode("utf-8")) > 200:
        _invalid()
    return str(value)


def _usage(value: Any) -> CodexUsage:
    if type(value) is not dict:
        _invalid()
    for name in ("input_tokens", "cached_input_tokens", "output_tokens"):
        number = value.get(name)
        if type(number) is not int or not 0 <= number <= 2**63 - 1:
            _invalid()
    reasoning = value.get("reasoning_output_tokens")
    if "reasoning_output_tokens" in value and (
        type(reasoning) is not int or not 0 <= reasoning <= 2**63 - 1
    ):
        _invalid()
    if value["cached_input_tokens"] > value["input_tokens"]:
        _invalid()
    return CodexUsage(
        value["input_tokens"], value["cached_input_tokens"], value["output_tokens"], reasoning
    )


@dataclass(frozen=True, slots=True)
class CodexUsage:
    """Unverified caller-supplied counters, never an estimate or billing record."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CodexEventReport:
    thread_id: str | None
    state: Literal["succeeded", "failed", "incomplete"]
    agent_messages: tuple[str, ...]
    usage: CodexUsage | None
    event_count: int
    item_event_count: int
    non_message_item_event_count: int
    error_code: str | None
    protocol_only: Literal[True] = field(default=True, init=False)
    provenance: Literal["caller_supplied"] = field(default="caller_supplied", init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)


def parse_codex_jsonl(text: str, *, exit_code: int | None) -> CodexEventReport:
    """Project one bounded single-turn stream; protocol success is not task acceptance.

    Missing usage is unknown, never zero or a billing estimate. Counts measure
    events, including repeated lifecycle events for one item, not API calls.
    Non-message item counts include reasoning and error items as well as tools.
    Unknown event/item types fail unsupported; extra fields on supported records
    are checked as bounded JSON but otherwise ignored. No raw errors are retained.
    """
    if type(text) is not str or (
        exit_code is not None
        and (type(exit_code) is not int or not -(2**63) <= exit_code <= 2**63 - 1)
    ):
        _invalid()
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        _invalid()
    if size > 1024 * 1024 or "\x00" in text:
        _invalid()
    raw_lines = text.split("\n") if text else []
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()
    if len(raw_lines) > 8192:
        _invalid()
    events: list[dict[str, Any]] = []
    for line in raw_lines:
        if not line.strip() or len(line.encode("utf-8")) > 65536:
            _invalid()
        try:
            event = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except (ValueError, RecursionError):
            _invalid()
        _validate_json(event)
        if type(event) is not dict:
            _invalid()
        events.append(event)
    thread_id = None
    started = False
    terminal = None
    messages = []
    usage = None
    item_count = tool_count = 0
    output_size = 0
    items: dict[str, tuple[str, bool]] = {}
    for event in events:
        kind = _identifier(event.get("type"))
        if terminal is not None:
            _sequence_error()
        if kind == "thread.started":
            if thread_id is not None or started:
                _sequence_error()
            thread_id = _identifier(event.get("thread_id"))
        elif kind == "turn.started":
            if thread_id is None or started:
                _sequence_error()
            started = True
        elif kind in {"item.started", "item.updated", "item.completed"}:
            if not started:
                _sequence_error()
            item = event.get("item")
            if type(item) is not dict:
                _invalid()
            identity, item_type = _identifier(item.get("id")), _identifier(item.get("type"))
            if item_type not in _ITEM_TYPES:
                raise AgentSyncError("unsupported_event", "Unsupported Codex event subset.")
            old = items.get(identity)
            if old is not None and (old[0] != item_type or old[1] or kind == "item.started"):
                _sequence_error()
            if kind == "item.updated" and old is None:
                _sequence_error()
            items[identity] = (item_type, kind == "item.completed")
            item_count += 1
            if item_type != "agent_message":
                tool_count += 1
            elif kind == "item.completed":
                message = item.get("text")
                if type(message) is not str:
                    _invalid()
                output_size += len(message.encode("utf-8"))
                if output_size > 65536:
                    _invalid()
                messages.append(message)
        elif kind in {"turn.completed", "turn.failed"}:
            if not started:
                _sequence_error()
            if kind == "turn.completed" and any(not value[1] for value in items.values()):
                _sequence_error()
            terminal = kind
            if kind == "turn.completed" and event.get("usage") is not None:
                usage = _usage(event["usage"])
            elif kind == "turn.failed":
                failure = event.get("error")
                if type(failure) is not dict or type(failure.get("message")) is not str:
                    _invalid()
        elif kind == "error":
            if type(event.get("message")) is not str:
                _invalid()
            terminal = kind
        else:
            raise AgentSyncError("unsupported_event", "Unsupported Codex event subset.")
    state: Literal["succeeded", "failed", "incomplete"]
    error_code = None
    if terminal in {"turn.failed", "error"}:
        state, error_code = "failed", "upstream_error"
    elif exit_code is not None and exit_code != 0:
        state, error_code = "failed", "process_failed"
    elif terminal != "turn.completed":
        state, error_code = "incomplete", "incomplete_stream"
    elif exit_code is None:
        state, error_code = "incomplete", "process_unknown"
    else:
        state = "succeeded"
    return CodexEventReport(
        thread_id,
        state,
        tuple(messages),
        usage,
        len(events),
        item_count,
        tool_count,
        error_code,
    )

"""Bounded caller-supplied Claude JSONL projection, never client execution.

Only an explicitly limited main-session, non-partial subset is supported.
Parsing is not authentication, Core acceptance, authorization or billing proof.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn

from agentsync.errors import AgentSyncError


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid Claude event input.") from None


def _sequence() -> NoReturn:
    raise AgentSyncError("invalid_event_sequence", "Invalid Claude event sequence.") from None


def _unsupported() -> NoReturn:
    raise AgentSyncError("unsupported_event", "Unsupported Claude event subset.") from None


def _id(value: Any) -> str:
    if type(value) is not str or not value.strip() or any(ord(c) < 32 for c in value):
        _invalid()
    if len(value.encode("utf-8")) > 200:
        _invalid()
    return str(value)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            _invalid()
        obj[key] = value
    return obj


def _constant(_value: str) -> Any:
    _invalid()


def _json(text: str) -> list[dict[str, Any]]:
    if type(text) is not str:
        _invalid()
    try:
        if len(text.encode("utf-8")) > 1024 * 1024 or "\x00" in text:
            _invalid()
    except UnicodeError:
        _invalid()
    lines = text.split("\n") if text else []
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > 8192:
        _invalid()
    events = []
    for line in lines:
        if not line.strip() or len(line.encode("utf-8")) > 65536:
            _invalid()
        try:
            event = json.loads(line, object_pairs_hook=_object, parse_constant=_constant)
        except (ValueError, RecursionError):
            _invalid()
        pending = [(event, 0)]
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
                    item.encode("utf-8")
                except UnicodeError:
                    _invalid()
                if "\x00" in item:
                    _invalid()
            elif isinstance(item, float) and not math.isfinite(item):
                _invalid()
        if type(event) is not dict:
            _invalid()
        events.append(event)
    return events


def _uint(value: Any) -> int:
    if type(value) is not int or not 0 <= value < 2**63:
        _invalid()
    return int(value)


def _usage(value: Any) -> ClaudeUsage | None:
    if value is None:
        return None
    if type(value) is not dict:
        _invalid()
    return ClaudeUsage(
        _uint(value.get("input_tokens")),
        _uint(value.get("output_tokens")),
        _uint(value["cache_read_input_tokens"]) if "cache_read_input_tokens" in value else None,
        _uint(value["cache_creation_input_tokens"])
        if "cache_creation_input_tokens" in value
        else None,
    )


def _assistant(event: dict[str, Any]) -> tuple[int, int, bool, str | None]:
    message = event.get("message")
    if type(message) is not dict or type(message.get("content")) is not list:
        _invalid()
    stop_reason = message.get("stop_reason")
    if stop_reason is not None:
        stop_reason = _id(stop_reason)
        if stop_reason not in {"end_turn", "stop_sequence", "max_tokens", "refusal", "tool_use"}:
            _unsupported()
    tools = text_bytes = 0
    for block in message["content"]:
        if type(block) is not dict:
            _invalid()
        kind = _id(block.get("type"))
        if kind == "text":
            if type(block.get("text")) is not str:
                _invalid()
            text_bytes += len(block["text"].encode("utf-8"))
        elif kind == "thinking":
            if type(block.get("thinking")) is not str or type(block.get("signature")) is not str:
                _invalid()
        elif kind in {"tool_use", "server_tool_use"}:
            _id(block.get("id"))
            _id(block.get("name"))
            if type(block.get("input")) is not dict:
                _invalid()
            tools += 1
        elif kind in {"tool_result", "advisor_tool_result"}:
            _id(block.get("tool_use_id"))
            tools += 1
        else:
            _unsupported()
    error = event.get("error")
    if error is not None:
        if _id(error) not in {
            "authentication_failed",
            "billing_error",
            "rate_limit",
            "invalid_request",
            "server_error",
            "max_output_tokens",
            "unknown",
        }:
            _unsupported()
    return tools, text_bytes, error is not None, stop_reason


def _validate_result(event: dict[str, Any]) -> None:
    for name in ("duration_ms", "duration_api_ms", "num_turns"):
        if name in event:
            _uint(event[name])
    if event.get("api_error_status") is not None:
        code = _uint(event["api_error_status"])
        if not 100 <= code <= 599:
            _invalid()
    cost = event.get("total_cost_usd")
    if cost is not None and (type(cost) not in {int, float} or cost < 0):
        _invalid()
    for name in ("permission_denials", "errors"):
        if event.get(name) is not None and type(event[name]) is not list:
            _invalid()
    if any(type(e) is not str for e in event.get("errors") or []):
        _invalid()
    deferred = event.get("deferred_tool_use")
    if deferred is not None:
        if type(deferred) is not dict or type(deferred.get("input")) is not dict:
            _invalid()
        _id(deferred.get("id"))
        _id(deferred.get("name"))
    if event.get("terminal_reason") is not None and _id(event["terminal_reason"]) not in {
        "completed",
        "max_turns",
        "max_budget_usd",
        "aborted_tools",
        "aborted_streaming",
    }:
        _unsupported()
    if event.get("stop_reason") is not None and _id(event["stop_reason"]) not in {
        "end_turn",
        "stop_sequence",
        "max_tokens",
        "refusal",
        "tool_use",
    }:
        _unsupported()


@dataclass(frozen=True, slots=True)
class ClaudeUsage:
    """Unverified reported counters; absent optional counters stay unknown."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ClaudeEventReport:
    session_id: str | None
    state: Literal["succeeded", "failed", "incomplete"]
    result_text: str = field(repr=False)
    usage: ClaudeUsage | None
    event_count: int
    assistant_message_count: int
    tool_block_count: int
    error_code: str | None
    protocol_only: Literal[True] = field(default=True, init=False)
    provenance: Literal["caller_supplied"] = field(default="caller_supplied", init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)


def parse_claude_jsonl(text: str, *, exit_code: int | None) -> ClaudeEventReport:
    """Project a caller stream; only final success text can be returned."""
    if exit_code is not None and (type(exit_code) is not int or not -(2**63) <= exit_code < 2**63):
        _invalid()
    events = _json(text)
    session = None
    final = None
    assistants = tools = text_bytes = 0
    assistant_error = False
    last_assistant_stop = None
    usage = None
    for event in events:
        kind = _id(event.get("type"))
        if kind == "system":
            if _id(event.get("subtype")) != "init":
                _unsupported()
            if session is not None or final is not None:
                _sequence()
            session = _id(event.get("session_id"))
        elif kind in {"assistant", "result"}:
            if session is None or final is not None:
                _sequence()
            event_session = event.get("session_id")
            if kind == "result" or event_session is not None:
                if _id(event_session) != session:
                    _sequence()
            if event.get("parent_tool_use_id") is not None:
                _unsupported()
            if kind == "assistant":
                assistants += 1
                tool_count, text_size, has_error, last_assistant_stop = _assistant(event)
                tools += tool_count
                text_bytes += text_size
                assistant_error |= has_error
                if text_bytes > 65536:
                    _invalid()
            else:
                if _id(event.get("subtype")) not in {
                    "success",
                    "error_max_turns",
                    "error_max_budget_usd",
                    "error_during_execution",
                }:
                    _unsupported()
                if type(event.get("is_error")) is not bool:
                    _invalid()
                if (
                    event["subtype"] == "success"
                    and not event["is_error"]
                    and type(event.get("result")) is not str
                ):
                    _invalid()
                origin = event.get("origin")
                if origin is not None:
                    if type(origin) is not dict or type(origin.get("kind")) is not str:
                        _invalid()
                    if origin["kind"] != "human":
                        _unsupported()
                _validate_result(event)
                usage = _usage(event.get("usage"))
                final = event
        else:
            _unsupported()
    state: Literal["succeeded", "failed", "incomplete"] = "succeeded"
    code = None
    if assistant_error or (
        final is not None
        and (
            final["is_error"]
            or final["subtype"] != "success"
            or final.get("errors")
            or final.get("api_error_status") is not None
        )
    ):
        state, code = "failed", "upstream_error"
    elif exit_code is not None and exit_code != 0:
        state, code = "failed", "process_failed"
    elif final is None:
        state, code = "incomplete", "incomplete_stream"
    elif exit_code is None:
        state, code = "incomplete", "process_unknown"
    elif final.get("terminal_reason") in {"aborted_tools", "aborted_streaming"}:
        state, code = "incomplete", "interrupted"
    elif (
        last_assistant_stop in {"max_tokens", "refusal", "tool_use"}
        or final.get("stop_reason") in {"max_tokens", "refusal", "tool_use"}
        or final.get("terminal_reason") in {"max_turns", "max_budget_usd"}
    ):
        state, code = "incomplete", "incomplete_response"
    elif final.get("permission_denials"):
        state, code = "failed", "permission_denied"
    elif final.get("deferred_tool_use") is not None:
        state, code = "incomplete", "deferred_tool_use"
    return ClaudeEventReport(
        session,
        state,
        final["result"] if state == "succeeded" and final else "",
        usage,
        len(events),
        assistants,
        tools,
        code,
    )

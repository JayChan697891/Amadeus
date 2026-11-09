"""Summarize an explicitly supplied local Claude JSONL file without its raw text.

Exit zero means parsing completed, even for failed/incomplete reported states.
Caller-supplied events and process status do not prove client execution, task
acceptance, authorization or billing. No client is launched or files searched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentsync.adapters.claude_events import parse_claude_jsonl
from agentsync.errors import AgentSyncError

if __package__:
    from ._capture_inspection import MAX_INPUT_BYTES, exit_code, read_capture
else:
    from _capture_inspection import MAX_INPUT_BYTES, exit_code, read_capture


def _markers() -> dict[str, Any]:
    return {
        "schema": "agentsync.claude-event-inspection.v1",
        "protocol_only": True,
        "provenance": "caller_supplied",
        "real_client_verified": False,
        "execution_connected": False,
        "formal_acceptance": False,
        "verification": "unverified",
        "core_authorization": "unverified",
        "billing_verified": False,
    }


def _error(code: str) -> int:
    print(json.dumps({**_markers(), "error_code": code}, allow_nan=False))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Explicit existing JSONL file")
    parser.add_argument(
        "--exit-code",
        type=exit_code,
        default=None,
        help="Caller-provided process status; omitted means unknown, never assumed zero",
    )
    args = parser.parse_args(argv)
    try:
        raw = read_capture(args.input)
    except (OSError, ValueError):
        return _error("input_unavailable")
    if len(raw) > MAX_INPUT_BYTES:
        return _error("input_too_large")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        return _error("invalid_utf8")
    try:
        report = parse_claude_jsonl(text, exit_code=args.exit_code)
    except AgentSyncError as exc:
        code = (
            exc.code
            if exc.code in {"validation_error", "invalid_event_sequence", "unsupported_event"}
            else "validation_error"
        )
        return _error(code)
    usage = (
        {
            **asdict(report.usage),
            "provenance": "caller_supplied",
            "verification": "unverified",
            "billing_verified": False,
        }
        if report.usage is not None
        else None
    )
    encoded_result = report.result_text.encode("utf-8")
    value = {
        **_markers(),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "exit_code": args.exit_code,
        "exit_code_provenance": "caller_provided",
        "state": report.state,
        "session_present": report.session_id is not None,
        "event_count": report.event_count,
        "assistant_message_count": report.assistant_message_count,
        "tool_block_count": report.tool_block_count,
        "result_text": {
            "utf8_size": len(encoded_result),
            "sha256": hashlib.sha256(encoded_result).hexdigest(),
        },
        "usage": usage,
        "error_code": report.error_code,
    }
    print(json.dumps(value, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

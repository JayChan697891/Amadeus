"""Summarize an explicitly supplied local JSONL file without exposing its text.

Exit zero means protocol parsing succeeded, even when the reported state is
failed or incomplete. Neither the file nor caller-provided process exit status
proves a real client run, task acceptance, authorization, usage or billing.
No client/process is started, no default files are searched and input is not
modified. Message summaries contain only UTF-8 sizes and SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentsync.adapters.codex_events import parse_codex_jsonl
from agentsync.errors import AgentSyncError

MAX_INPUT_BYTES = 1024 * 1024


def _exit_code(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a signed 64-bit integer.") from None
    if not -(2**63) <= number <= 2**63 - 1:
        raise argparse.ArgumentTypeError("Expected a signed 64-bit integer.")
    return number


def _markers() -> dict[str, Any]:
    return {
        "schema": "agentsync.codex-event-inspection.v1",
        "protocol_only": True,
        "provenance": "caller_supplied",
        "real_client_verified": False,
        "execution_connected": False,
        "formal_acceptance": False,
        "verification": "unverified",
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
        type=_exit_code,
        default=None,
        help="Caller-provided process status; omitted means unknown, never assumed zero",
    )
    args = parser.parse_args(argv)
    try:
        if not args.input.is_file():
            return _error("input_unavailable")
        with args.input.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError):
        return _error("input_unavailable")
    if len(raw) > MAX_INPUT_BYTES:
        return _error("input_too_large")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        return _error("invalid_utf8")
    try:
        report = parse_codex_jsonl(text, exit_code=args.exit_code)
    except AgentSyncError as exc:
        code = (
            exc.code
            if exc.code in {"validation_error", "invalid_event_sequence", "unsupported_event"}
            else "validation_error"
        )
        return _error(code)
    usage = (
        {**asdict(report.usage), "provenance": "caller_supplied", "billing_verified": False}
        if report.usage is not None
        else None
    )
    value = {
        **_markers(),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "exit_code": args.exit_code,
        "exit_code_provenance": "caller_provided",
        "state": report.state,
        "thread_present": report.thread_id is not None,
        "event_count": report.event_count,
        "item_event_count": report.item_event_count,
        "non_message_item_event_count": report.non_message_item_event_count,
        "agent_messages": [
            {
                "utf8_size": len(message.encode("utf-8")),
                "sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            }
            for message in report.agent_messages
        ],
        "usage": usage,
        "error_code": report.error_code,
    }
    print(json.dumps(value, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

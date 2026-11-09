"""Summarize an explicit Cursor terminal JSON capture without exposing its text.

The input and exit code are caller observations. Parsing never launches Cursor
and cannot establish client execution, task acceptance, or billing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agentsync.adapters.cursor_events import parse_cursor_json
from agentsync.errors import AgentSyncError

if __package__:
    from ._capture_inspection import MAX_INPUT_BYTES, exit_code, read_capture
else:
    from _capture_inspection import MAX_INPUT_BYTES, exit_code, read_capture

_MARKERS = {
    "schema": "agentsync.cursor-event-inspection.v1",
    "protocol_only": True,
    "provenance": "caller_supplied",
    "real_client_verified": False,
    "execution_connected": False,
    "formal_acceptance": False,
    "verification": "unverified",
    "core_authorization": "unverified",
    "billing_verified": False,
}


def inspect_capture(raw: bytes, *, exit_code: int | None) -> dict[str, Any]:
    """Use the production adapter parser and omit session, request and result text."""
    if len(raw) > MAX_INPUT_BYTES:
        raise AgentSyncError("input_too_large", "Cursor capture exceeds its limit.")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise AgentSyncError("invalid_utf8", "Cursor capture is not UTF-8.") from None
    report = parse_cursor_json(text, exit_code=exit_code)
    metadata = report.metadata
    result = report.result_text.encode("utf-8")
    return {
        **_MARKERS,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "exit_code": exit_code,
        "exit_code_provenance": "caller_provided",
        "state": report.state,
        "session_present": report.session_id is not None,
        "reported_timing": None if metadata is None else {
            "duration_ms": metadata.duration_ms,
            "duration_api_ms": metadata.duration_api_ms,
            "request_present": metadata.request_id is not None,
            "provenance": "caller_supplied",
        },
        "result_text": {"utf8_size": len(result), "sha256": hashlib.sha256(result).hexdigest()},
        "usage": None,
        "error_code": report.error_code,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Explicit terminal JSON capture")
    parser.add_argument("--exit-code", type=exit_code, help="Observed process exit code if available")
    args = parser.parse_args(argv)
    try:
        raw = read_capture(args.input)
        report = inspect_capture(raw, exit_code=args.exit_code)
    except (OSError, ValueError):
        print(json.dumps({**_MARKERS, "error_code": "input_unavailable"}))
        return 1
    except AgentSyncError as exc:
        print(json.dumps({**_MARKERS, "error_code": exc.code}))
        return 1
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

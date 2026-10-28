"""Offline checkpoint summary, with no files, Core or client execution.

The CLI accepts only ``usage --project-id ID`` with a bounded UTF-8 checkpoint
on stdin. Other usage arguments, including --help, return a fixed input error.
Caller observations and unknown costs retain the ledger's unverified markers.
"""

import json
import sys
from dataclasses import asdict

from agentsync.errors import AgentSyncError
from agentsync.usage import UsageLedger

MAX_INPUT_BYTES = 1024 * 1024


def invalid_input() -> int:
    print(json.dumps({"error": {"code": "invalid_input", "message": "Invalid usage input."}}))
    return 2


def run_usage_cli(project_id: str) -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError
        ledger = UsageLedger.from_json(project_id, raw.decode("utf-8"))
        output = json.dumps(asdict(ledger.summary()), allow_nan=False)
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

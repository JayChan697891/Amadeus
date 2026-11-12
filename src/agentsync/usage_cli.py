"""Offline checkpoint summaries, with no files, Core or client execution.

Both ``usage`` and ``model-usage`` require ``--project-id ID`` and a bounded
UTF-8 checkpoint on stdin. Invalid arguments return a fixed input error.
Caller observations and unknown costs retain the ledger's unverified markers.
"""

import json
import sys
from dataclasses import asdict

from agentsync.errors import AgentSyncError
from agentsync.model_usage_checkpoint import MODEL_CHECKPOINT_LIMIT, load_model_usage
from agentsync.usage import UsageLedger

MAX_INPUT_BYTES = 1024 * 1024


def invalid_input() -> int:
    print(json.dumps({"error": {"code": "invalid_input", "message": "Invalid usage input."}}))
    return 2


def run_usage_cli(project_id: str, *, model: bool = False) -> int:
    try:
        limit = MODEL_CHECKPOINT_LIMIT if model else MAX_INPUT_BYTES
        raw = sys.stdin.buffer.read(limit + 1)
        if len(raw) > limit:
            raise ValueError
        text = raw.decode("utf-8")
        if model:
            observation = asdict(load_model_usage(project_id, text))
            observation.update(
                project_id=project_id, verification="unverified", historical_snapshot=True
            )
        else:
            observation = asdict(UsageLedger.from_json(project_id, text).summary())
        output = json.dumps(observation, allow_nan=False)
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

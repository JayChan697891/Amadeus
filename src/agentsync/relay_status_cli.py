"""Project-owner inspection of a local relay journal."""

import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentsync.controlled_relay import ControlledRelay
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.relay_queue import RelayQueue
from agentsync.sdk import error_envelope
from agentsync.workspaces.git import physical

_INPUT_LIMIT = 8192


def run_relay_status_cli(
    data_dir: Path,
    scratch_root: Path,
    receipts: Path,
    *,
    history: bool,
    limit: int,
    before: str | None,
) -> int:
    try:
        raw = sys.stdin.buffer.read(_INPUT_LIMIT + 1)
        if len(raw) > _INPUT_LIMIT:
            raise ValueError
        credentials = json.loads(raw.decode("utf-8"))
        if (
            type(credentials) is not dict
            or set(credentials) != {"project_id", "admin_token"}
            or any(type(value) is not str for value in credentials.values())
            or not all(path.is_absolute() for path in (data_dir, scratch_root, receipts))
        ):
            raise ValueError
        for path in (data_dir, scratch_root, receipts):
            physical(path)
            if not path.is_dir():
                raise ValueError
        data_dir = data_dir.resolve(strict=True)
        scratch_root = scratch_root.resolve(strict=True)
        receipts = receipts.resolve(strict=True)
        if (
            receipts == scratch_root
            or not receipts.is_relative_to(scratch_root)
            or not data_dir.is_relative_to(scratch_root)
            or data_dir.is_relative_to(receipts)
        ):
            raise ValueError
        database = data_dir / "agentsync.db"
        physical(database)
        if not database.is_file():
            raise ValueError

        queue = RelayQueue(ControlledRelay(Core(data_dir), scratch_root, receipts))
        result: dict[str, Any] | None
        if history:
            result = asdict(queue.owner_history(**credentials, limit=limit, before=before))
        else:
            pending = queue.owner_observe_pending(**credentials)
            result = None if pending is None else asdict(pending)
        response = {"ok": True, "data": result}
    except AgentSyncError as error:
        response = error_envelope(error)
    except sqlite3.Error:
        response = error_envelope(AgentSyncError("storage_error", "The local Core database is unavailable."))
    except (OSError, ValueError, RecursionError):
        response = error_envelope(
            AgentSyncError("validation_error", "Invalid credentials input or local relay paths.")
        )
    print(json.dumps(response, ensure_ascii=True))
    return 0 if response["ok"] else 1

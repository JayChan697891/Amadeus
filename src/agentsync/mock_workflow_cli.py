"""Run a caller-described Mock DAG in an explicitly selected scratch directory."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

from agentsync.errors import AgentSyncError
from agentsync.mock_workflow import MockWorkflowTask, MockWorkflowWorker, run_mock_workflow

_MAX_INPUT_BYTES = 64 * 1024
_WORKFLOW_OPTIONS = {
    "max_attempts_per_task",
    "attempt_budget",
    "max_elapsed_seconds",
    "parallel_limit",
}
_TASK_REQUIRED = {"label", "priority", "capability"}
_TASK_OPTIONAL = {"dependencies", "fail_first_attempt", "handoff_on_success"}


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    members: dict[str, Any] = {}
    for key, value in pairs:
        if key in members:
            raise ValueError("Duplicate JSON field.")
        members[key] = value
    return members


def _invalid_constant(_text: str) -> NoReturn:
    raise ValueError("Invalid JSON constant.")


def _task(row: Any) -> MockWorkflowTask:
    if (
        type(row) is not dict
        or not _TASK_REQUIRED <= row.keys()
        or row.keys() - _TASK_REQUIRED - _TASK_OPTIONAL
    ):
        raise ValueError("Invalid workflow task fields.")
    dependencies = row.get("dependencies", [])
    if type(dependencies) is not list:
        raise ValueError("Workflow dependencies must be an array.")
    return MockWorkflowTask(
        label=row["label"],
        priority=row["priority"],
        capability=row["capability"],
        dependencies=tuple(dependencies),
        fail_first_attempt=row.get("fail_first_attempt", False),
        handoff_on_success=row.get("handoff_on_success", False),
    )


def _worker(row: Any) -> MockWorkflowWorker:
    if type(row) is not dict or row.keys() != {"label", "capabilities"}:
        raise ValueError("Invalid workflow worker fields.")
    capabilities = row["capabilities"]
    if type(capabilities) is not list:
        raise ValueError("Workflow worker capabilities must be an array.")
    return MockWorkflowWorker(label=row["label"], capabilities=tuple(capabilities))


def _error(code: str, message: str) -> int:
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
    return 2 if code == "invalid_input" else 1


def run_mock_workflow_cli(scratch_parent: Path) -> int:
    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
        if len(raw) > _MAX_INPUT_BYTES:
            raise ValueError("Workflow input is too large.")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_members,
            parse_constant=_invalid_constant,
        )
        if (
            type(payload) is not dict
            or "tasks" not in payload
            or payload.keys() - _WORKFLOW_OPTIONS - {"tasks", "workers"}
            or type(payload["tasks"]) is not list
            or not 1 <= len(payload["tasks"]) <= 16
        ):
            raise ValueError("Invalid workflow document.")
        tasks = tuple(_task(row) for row in payload["tasks"])
        options = {name: payload[name] for name in _WORKFLOW_OPTIONS if name in payload}
        if "workers" in payload:
            workers = payload["workers"]
            if type(workers) is not list or not 2 <= len(workers) <= 8:
                raise ValueError("Invalid workflow worker roster.")
            options["workers"] = tuple(_worker(row) for row in workers)
        result = asyncio.run(run_mock_workflow(scratch_parent, tasks=tasks, **options))
    except (ValueError, RecursionError, OverflowError):
        return _error("invalid_input", "Invalid Mock workflow input or scratch directory.")
    except (AgentSyncError, OSError, RuntimeError):
        return _error("workflow_failed", "Mock workflow could not complete.")
    print(json.dumps(result, allow_nan=False))
    return 0

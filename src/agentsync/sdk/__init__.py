"""In-process SDK; every operation is dispatched through the shared Core."""

from pathlib import Path
from typing import Any

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError


def error_envelope(error: AgentSyncError) -> dict[str, Any]:
    return {"ok": False, "error": {"code": error.code, "message": error.message}}


class AgentSyncClient:
    def __init__(self, data_dir: str | Path | None = None):
        self.core = Core(data_dir=data_dir)

    def call(self, operation: str, **payload: Any) -> dict[str, Any]:
        try:
            return {"ok": True, "data": self.core.execute(operation, payload)}
        except AgentSyncError as error:
            return error_envelope(error)

    def owner_call(self, operation: str, **payload: Any) -> dict[str, Any]:
        """Use the separate project-owner authority; never expose this as an MCP tool."""
        try:
            return {"ok": True, "data": self.core.execute_owner(operation, payload)}
        except AgentSyncError as error:
            return error_envelope(error)

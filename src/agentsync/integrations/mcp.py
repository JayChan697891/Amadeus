"""Official MCP SDK v2 tools backed by the same in-process Core."""

from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from pydantic import Field

from agentsync.sdk import AgentSyncClient


def build_server(data_dir: str | Path | None = None) -> MCPServer:
    client = AgentSyncClient(data_dir)
    server = MCPServer("AgentSync")

    @server.tool()
    def create_project(name: str, root_path: str) -> dict[str, Any]:
        """Create a project; save its one-time administrator token privately."""
        return client.call(
            "create_project", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def register_agent(
        project_id: str,
        admin_token: str,
        name: str,
        capabilities: Annotated[list[str], Field(default_factory=list)],
    ) -> dict[str, Any]:
        """Register an agent session using the project administrator token."""
        return client.call(
            "register_agent", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def heartbeat(project_id: str, session_id: str, session_token: str) -> dict[str, Any]:
        """Renew an authenticated session heartbeat."""
        return client.call(
            "heartbeat", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def create_task(
        project_id: str,
        session_id: str,
        session_token: str,
        title: str,
        request_id: str,
        dependencies: Annotated[list[str], Field(default_factory=list)],
        description: str = "",
        priority: int = 0,
    ) -> dict[str, Any]:
        """Create an idempotent task, optionally depending on other tasks."""
        return client.call(
            "create_task", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def list_tasks(project_id: str, session_id: str, session_token: str) -> dict[str, Any]:
        """List project tasks without credentials or lease tokens."""
        return client.call(
            "list_tasks", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def get_project_state(project_id: str, session_id: str, session_token: str) -> dict[str, Any]:
        """Read project collaboration state without credentials."""
        return client.call(
            "get_project_state",
            **{key: value for key, value in locals().items() if key != "client"},
        )

    @server.tool()
    def claim_task(
        project_id: str,
        session_id: str,
        session_token: str,
        task_id: str,
        expected_version: int,
        request_id: str,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        """Atomically claim a pending task with a version and expiring lease."""
        return client.call(
            "claim_task", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def renew_lease(
        project_id: str,
        session_id: str,
        session_token: str,
        task_id: str,
        lease_token: str,
        expected_version: int,
        request_id: str,
        lease_seconds: int = 300,
    ) -> dict[str, Any]:
        """Renew the current owner's unexpired task lease."""
        return client.call(
            "renew_lease", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def update_task(
        project_id: str,
        session_id: str,
        session_token: str,
        task_id: str,
        lease_token: str,
        expected_version: int,
        status: Literal["running", "review", "blocked", "failed", "cancelled"],
        request_id: str,
        result: str = "",
    ) -> dict[str, Any]:
        """Update an owned task; review status still requires independent review."""
        return client.call(
            "update_task", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def review_task(
        project_id: str,
        session_id: str,
        session_token: str,
        task_id: str,
        expected_version: int,
        accept: bool,
        evidence: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Review another agent's submission using a reviewer assertion, not automatic verification."""
        return client.call(
            "review_task", **{key: value for key, value in locals().items() if key != "client"}
        )

    @server.tool()
    def reclaim_expired(project_id: str, session_id: str, session_token: str) -> dict[str, Any]:
        """Return expired leased tasks to pending and invalidate their leases."""
        return client.call(
            "reclaim_expired", **{key: value for key, value in locals().items() if key != "client"}
        )

    return server

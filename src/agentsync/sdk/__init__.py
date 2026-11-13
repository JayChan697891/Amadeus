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
            if operation in {
                "preview_candidate_integration",
                "approve_candidate_integration",
                "integrate_candidate",
                "get_candidate_integration_status",
            }:
                from agentsync.verification.candidate_integration import OwnerCandidateIntegration

                integration = OwnerCandidateIntegration(self.core)
                handlers = {
                    "preview_candidate_integration": integration.preview,
                    "approve_candidate_integration": integration.approve,
                    "integrate_candidate": integration.integrate_once,
                    "get_candidate_integration_status": integration.status,
                }
                return {"ok": True, "data": handlers[operation](**payload)}
            if operation == "sync_relay_usage":
                from agentsync.relay_usage import sync_relay_usage

                return {"ok": True, "data": sync_relay_usage(self.core, payload)}
            if operation in {
                "start_mock_workflow",
                "resume_mock_workflow",
                "status_mock_workflow",
                "cancel_mock_workflow",
            }:
                from agentsync.durable_mock_workflow import OwnerMockWorkflow

                workflow = OwnerMockWorkflow(self.core)
                return {
                    "ok": True,
                    "data": getattr(workflow, operation.removesuffix("_mock_workflow"))(**payload),
                }
            if operation in (
                "preview_candidate_delivery",
                "get_candidate_delivery_status",
                "approve_candidate_delivery",
                "publish_candidate_delivery",
            ):
                from agentsync.verification.candidate_delivery import OwnerCandidateDelivery

                service = OwnerCandidateDelivery(self.core)
                if operation == "preview_candidate_delivery":
                    return {"ok": True, "data": service.preview(**payload)}
                if operation == "get_candidate_delivery_status":
                    return {"ok": True, "data": service.status(**payload)}
                if operation == "publish_candidate_delivery":
                    return {"ok": True, "data": service.publish_once(**payload)}
                return {"ok": True, "data": service.approve(**payload)}
            return {"ok": True, "data": self.core.execute_owner(operation, payload)}
        except AgentSyncError as error:
            return error_envelope(error)

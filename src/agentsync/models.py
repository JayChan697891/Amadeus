from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class CreateProject(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    root_path: str


class RegisterAgent(StrictModel):
    project_id: str
    admin_token: str
    name: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=list)


class Auth(StrictModel):
    project_id: str
    session_id: str
    session_token: str


class CreateTask(Auth):
    title: str = Field(min_length=1, max_length=1000)
    description: str = ""
    priority: int = Field(default=0, ge=-(2**63), le=2**63 - 1)
    dependencies: list[str] = Field(default_factory=list)
    request_id: str = Field(min_length=1, max_length=200)


class ClaimTask(Auth):
    task_id: str
    expected_version: int = Field(ge=1, le=2**63 - 2)
    lease_seconds: int = Field(default=300, ge=1, le=3600)
    request_id: str = Field(min_length=1, max_length=200)


class RenewLease(ClaimTask):
    lease_token: str


class UpdateTask(Auth):
    task_id: str
    lease_token: str
    expected_version: int = Field(ge=1, le=2**63 - 2)
    status: Literal["running", "review", "blocked", "failed", "cancelled"]
    result: str = ""
    request_id: str = Field(min_length=1, max_length=200)


class ReviewTask(Auth):
    task_id: str
    expected_version: int = Field(ge=1, le=2**63 - 2)
    accept: bool
    evidence: str = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=200)


OPERATIONS: dict[str, type[StrictModel]] = {
    "create_project": CreateProject,
    "register_agent": RegisterAgent,
    "heartbeat": Auth,
    "create_task": CreateTask,
    "list_tasks": Auth,
    "get_project_state": Auth,
    "claim_task": ClaimTask,
    "renew_lease": RenewLease,
    "update_task": UpdateTask,
    "review_task": ReviewTask,
    "reclaim_expired": Auth,
}

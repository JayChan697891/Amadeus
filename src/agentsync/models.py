from typing import Annotated, Literal

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


ContextKind = Literal["requirement", "decision", "constraint", "progress", "note"]
MetadataText = Annotated[str, Field(min_length=1, max_length=4000)]


class PublishContext(Auth):
    kind: ContextKind
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=65536)
    summary: str = Field(default="", max_length=4000)
    source: str = Field(default="", max_length=4000)
    context_id: str | None = None
    expected_version: int = Field(default=0, ge=0, le=2**63 - 2)
    request_id: str = Field(min_length=1, max_length=200)


class GetContext(Auth):
    context_id: str
    version: int | None = Field(default=None, ge=1, le=2**63 - 1)


class SearchContext(Auth):
    query: str = Field(min_length=1, max_length=500)
    kind: ContextKind | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


class ContextRef(StrictModel):
    context_id: str
    version: int = Field(ge=1, le=2**63 - 1)


class HandoffPackage(StrictModel):
    summary: str = Field(min_length=1, max_length=2000)
    completed_work: str = Field(default="", max_length=20000)
    changed_files: list[MetadataText] = Field(default_factory=list, max_length=100)
    open_questions: list[MetadataText] = Field(default_factory=list, max_length=100)
    evidence: list[MetadataText] = Field(default_factory=list, max_length=100)
    context_refs: list[ContextRef] = Field(default_factory=list, max_length=100)


class SubmitHandoff(Auth):
    task_id: str
    lease_token: str
    expected_version: int = Field(ge=1, le=2**63 - 2)
    target_agent_id: str
    package: HandoffPackage
    request_id: str = Field(min_length=1, max_length=200)


class GetHandoff(Auth):
    handoff_id: str


class ResolveHandoff(GetHandoff):
    expected_version: int = Field(ge=1, le=2**63 - 2)
    accept: bool
    reason: str = Field(default="", max_length=2000)
    request_id: str = Field(min_length=1, max_length=200)


class WithdrawHandoff(GetHandoff):
    expected_version: int = Field(ge=1, le=2**63 - 2)
    reason: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=1, max_length=200)


class InspectPath(Auth):
    path: str = Field(min_length=1, max_length=4096)


class VerifyFileVersion(InspectPath):
    expected_sha256: str | None = Field(pattern=r"^[0-9a-fA-F]{64}$")


class AcquireFileLock(InspectPath):
    kind: Literal["file", "directory"] = "file"
    lease_seconds: int = Field(default=300, ge=1, le=3600)
    request_id: str = Field(min_length=1, max_length=200)


class ReleaseFileLock(Auth):
    lock_id: str
    lease_token: str
    expected_version: int = Field(ge=1, le=2**63 - 2)
    request_id: str = Field(min_length=1, max_length=200)


class RenewFileLock(ReleaseFileLock):
    lease_seconds: int = Field(default=300, ge=1, le=3600)


class ListFileLocks(Auth):
    include_expired: bool = False
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


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
    "publish_context": PublishContext,
    "get_context": GetContext,
    "search_context": SearchContext,
    "submit_handoff": SubmitHandoff,
    "get_handoff": GetHandoff,
    "resolve_handoff": ResolveHandoff,
    "withdraw_handoff": WithdrawHandoff,
    "inspect_path": InspectPath,
    "verify_file_version": VerifyFileVersion,
    "acquire_file_lock": AcquireFileLock,
    "renew_file_lock": RenewFileLock,
    "release_file_lock": ReleaseFileLock,
    "list_file_locks": ListFileLocks,
}

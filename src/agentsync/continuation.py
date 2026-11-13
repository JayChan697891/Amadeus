"""One owner-approved continuation of a confirmed failed, ended proposal attempt.

Progress remains inert and unverified. Source attempts are never restarted. A
new task, isolated worktree, queue wave and exact launch consent are required.
The original dependency graph is transferred transactionally; no failed task is
represented as completed. No model output or credential is stored in receipts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from agentsync.adapters.approved_launch import _check_execution_deadline, digest
from agentsync.adapters.base import _bounded_text, _identifier
from agentsync.controlled_relay import (
    ContinuationInput,
    ContinuationPin,
    ControlledRelay,
    ProposalContextPin,
    RelayActor,
    _proposal_contract,
    _proposal_request_id,
)
from agentsync.core.collaboration import revision
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS
from agentsync.proposal_handoff import HandoffReceiver, HandoffWorkspace
from agentsync.proposals import parse_proposal, proposal_paths
from agentsync.relay_queue import ContinuationQueueItem, RelayQueue
from agentsync.storage.database import connect

_OPERATION = "continue_failed_task"


def _reject() -> NoReturn:
    raise AgentSyncError(
        "continuation_boundary", "The unfinished-work continuation no longer matches.", 409
    )


def confirmed_failure(
    relay: ControlledRelay, db: sqlite3.Connection, project_id: str, task_id: str
) -> dict[str, Any] | None:
    """Require the original, exactly bound local capture, not caller usage or expiry."""
    from agentsync.relay_usage import _observe_leg

    relay._check_receipt_anchor(project_id, require_existing=True)
    if (
        db.execute(
            "SELECT 1 FROM tasks WHERE project_id=? AND id=?", (project_id, task_id)
        ).fetchone()
        is None
    ):
        return None
    key = relay._task_receipt_key(project_id, task_id)
    admission = relay._read_receipt(key, "incomplete", durable=True)
    if not admission or admission.get("mode") not in ("codex_proposal", "proposal_continuation"):
        return None
    try:
        observed, _ = _observe_leg(relay, db, project_id, task_id, key, "first")
    except AgentSyncError:
        return None
    stopped = relay._read_receipt(key, "first-stopped", durable=True)
    if (
        observed is None
        or observed.status != "failed"
        or observed.binding != "dispatch_pinned"
        or not stopped
        or stopped.get("parent_ended") is not True
        or stopped.get("timed_out") is not False
        or type(stopped.get("exit_code")) is not int
        or stopped.get("status") not in ("failed", "reply_mismatch")
        or observed.terminal_sha256 != digest(stopped)
        or observed.launch_request_sha256 != stopped.get("launch_request_sha256")
        or type(stopped.get("time")) not in (int, float)
        or not math.isfinite(stopped["time"])
    ):
        return None
    capture = db.execute(
        "SELECT session_id,response FROM idempotency WHERE project_id=? AND operation='renew_lease' AND request_id=?",
        (project_id, f"relay:{key}:first:capture"),
    ).fetchall()
    matching = [
        json.loads(row["response"])
        for row in capture
        if digest(row["session_id"]) == observed.session_sha256
    ]
    if len(matching) != 1:
        return None
    witness = matching[0]
    if (
        witness.get("id") != task_id
        or witness.get("project_id") != project_id
        or witness.get("status") != "running"
        or type(witness.get("version")) is not int
        or not isinstance(admission.get("worktree_id"), str)
        or not isinstance(admission.get("base_head"), str)
    ):
        return None
    current = db.execute(
        "SELECT * FROM tasks WHERE project_id=? AND id=?", (project_id, task_id)
    ).fetchone()
    saved = _saved(db, project_id, observed.launch_request_sha256)
    same_capture = (
        current is not None
        and current["status"] == "running"
        and current["version"] == witness["version"]
        and digest(current["owner_session_id"]) == observed.session_sha256
    )
    own_transition = (
        current is not None
        and saved is not None
        and saved.get("source_task_id") == task_id
        and current["status"] == "failed"
        and current["version"] == witness["version"] + 1 == saved.get("source_version")
        and current["owner_session_id"] is None
        and current["lease_hash"] is None
    )
    if not same_capture and not own_transition:
        return None
    return {
        "launch_sha256": observed.launch_request_sha256,
        "terminal_sha256": observed.terminal_sha256,
        "agent_sha256": observed.agent_sha256,
        "session_sha256": observed.session_sha256,
        "wave_sha256": admission.get("wave_sha256"),
        "terminal_at": stopped["time"],
        "capture_version": witness["version"],
        "initial_version": admission.get("initial_task_version"),
        "worktree_id": admission["worktree_id"],
        "base_head": admission["base_head"],
        "paths_sha256": admission.get("paths_sha256"),
    }


def _progress(
    relay: ControlledRelay,
    db: sqlite3.Connection,
    project_id: str,
    pin: ContinuationPin,
    receiver_agent_id: str,
) -> tuple[str, dict[str, Any]]:
    failed = confirmed_failure(relay, db, project_id, pin.source_task_id)
    if failed is None or any(
        failed[name] != getattr(pin, name) for name in ("launch_sha256", "terminal_sha256")
    ):
        _reject()
    context = revision(db, project_id, pin.context_id, pin.context_version)
    content = context["content"]
    _bounded_text(content, 65536)
    if (
        context["source"] != "amadeus:task-proposal"
        or context["kind"] != "note"
        or hashlib.sha256(content.encode("utf-8")).hexdigest() != pin.content_sha256
        or digest(context["author_agent_id"]) != failed["agent_sha256"]
        or digest(context["author_session_id"]) != failed["session_sha256"]
        or context["author_agent_id"] == receiver_agent_id
        or context["created_at"] > failed["terminal_at"]
    ):
        _reject()
    try:
        body = json.loads(content)
        if not isinstance(body, dict):
            _reject()
        paths = proposal_paths([item["path"] for item in body["files"]])
        parse_proposal(json.dumps({"files": body["files"]}), list(paths))
    except (ValueError, KeyError, TypeError, RecursionError):
        _reject()
    if (
        body.get("format") != "amadeus-source-proposal-v1"
        or body.get("project_id") != project_id
        or body.get("task_id") != pin.source_task_id
        or body.get("execution_provenance") != "unverified"
        or type(body.get("task_version")) is not int
        or not 1 <= body["task_version"] <= failed["capture_version"]
        or type(failed["initial_version"]) is not int
        or body["task_version"] <= failed["initial_version"]
        or body.get("worktree_id") != failed["worktree_id"]
        or body.get("base_head") != failed["base_head"]
        or digest(paths) != failed["paths_sha256"]
    ):
        _reject()
    # Core's publication response proves the task/lease association. Merely
    # putting a task ID in a generic context or model output is insufficient.
    witnesses = db.execute(
        "SELECT response FROM idempotency WHERE project_id=? AND session_id=? AND operation='publish_task_proposal'",
        (project_id, context["author_session_id"]),
    ).fetchall()
    expected = {
        "context_id": pin.context_id,
        "context_version": pin.context_version,
        "content_sha256": pin.content_sha256,
        "task_id": pin.source_task_id,
        "task_version": body["task_version"],
        "worktree_id": body.get("worktree_id"),
        "base_head": body.get("base_head"),
        "verification": "unverified",
        "execution_provenance": "unverified",
    }
    if not any(json.loads(row["response"]) == expected for row in witnesses):
        _reject()
    key = relay._task_receipt_key(project_id, pin.source_task_id)
    admission = relay._read_receipt(key, "incomplete", durable=True)
    if admission is None:
        _reject()
    try:
        source_pin = (
            ProposalContextPin(**admission["input_context"])
            if "input_context" in admission
            else None
        )
        prior = (
            ContinuationPin(**admission["continuation"])
            if admission["mode"] == "proposal_continuation"
            else None
        )
        contract = _proposal_contract(
            body["worktree_id"],
            body["base_head"],
            admission["initial_task_version"],
            paths,
            admission.get("submit_for_review", False),
            admission.get("wave_sha256"),
            source_pin,
            None,
            prior,
            admission.get("continuation_client") if prior is not None else None,
        )
    except (TypeError, KeyError, ValueError):
        _reject()
    expected_launch = digest(
        [
            project_id,
            context["author_session_id"],
            pin.source_task_id,
            _proposal_request_id(key, contract),
        ]
    )
    if expected_launch != failed["launch_sha256"]:
        _reject()
    tree = db.execute(
        "SELECT * FROM managed_worktrees WHERE project_id=? AND id=? AND task_id=? AND creator_session_id=?",
        (project_id, body["worktree_id"], pin.source_task_id, context["author_session_id"]),
    ).fetchone()
    if tree is None:
        _reject()
    return content, {
        "snapshot_id": tree["snapshot_id"],
        "base_head": body["base_head"],
        "paths": paths,
    }


def _saved(db: sqlite3.Connection, project: str, launch: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT response FROM owner_idempotency WHERE project_id=? AND operation=? AND request_id=?",
        (project, _OPERATION, launch),
    ).fetchone()
    return json.loads(row["response"]) if row else None


def reject_managed_target(relay: ControlledRelay, project: str, task_id: str) -> None:
    """Ordinary relay modes cannot dispatch an owner-managed continuation task."""
    with connect(relay._core.db_path) as db:
        rows = db.execute(
            "SELECT response FROM owner_idempotency WHERE project_id=? AND operation=?",
            (project, _OPERATION),
        )
        if any(json.loads(row["response"]).get("task_id") == task_id for row in rows):
            _reject()


@dataclass(slots=True)
class _StartRight:
    task_id: str
    wave: str
    receipt_name: str
    intent: dict[str, Any]
    consumed: bool = False


def check_start(
    relay: ControlledRelay,
    actor: RelayActor,
    spec: ContinuationInput,
    wave: str | None,
    authority: object | None,
    *,
    selection: str | None = None,
    consume: bool = False,
    running: bool = False,
) -> None:
    """A saved intent cannot recreate the ephemeral right to dispatch its call."""
    if (
        type(authority) is not _StartRight
        or authority is not relay._continuation_start
        or authority.task_id != spec.task_id
        or authority.wave != wave
        or authority.consumed != running
        or authority.intent.get("worktree_id") != actor.worktree_id
        or (selection is not None and authority.intent.get("selection_sha256") != selection)
    ):
        _reject()
    relay._check_receipt_anchor(actor.profile.project_id, require_existing=True)
    if relay._receipt_store.read(authority.receipt_name, durable=True) != authority.intent:
        _reject()
    queue = RelayQueue(relay)
    project_key = queue._checked_journal_key(actor.profile.project_id)
    if consume or running:
        row = queue._journal.get(project_key, authority.wave)
        if row is None or row[0] != "admitted" or row[1] != [spec.task_id]:
            _reject()
    if consume:
        authority.consumed = True


def continuation_source(
    relay: ControlledRelay,
    db: sqlite3.Connection,
    actor: RelayActor,
    spec: ContinuationInput,
    snapshot_id: str,
) -> str:
    pin = spec.continuation
    project = actor.profile.project_id
    saved = _saved(db, project, pin.launch_sha256)
    if (
        not saved
        or saved["task_id"] != spec.task_id
        or saved["pin"] != asdict(pin)
        or saved["version"] != spec.expected_version
        or saved["receiver_agent_id"] != actor.agent_id
        or saved["receiver_session_id"] != actor.profile.session_id
        or saved["snapshot_id"] != snapshot_id
        or saved["instruction_sha256"] != digest(spec.instruction)
        or saved["allowed_paths"] != list(spec.allowed_paths)
        or saved["execution_seconds"] != spec.timeout_seconds
    ):
        _reject()
    source = db.execute(
        "SELECT * FROM tasks WHERE project_id=? AND id=?", (project, pin.source_task_id)
    ).fetchone()
    if (
        source is None
        or source["status"] != "failed"
        or source["version"] != pin.source_task_version
    ):
        _reject()
    content, progress = _progress(relay, db, project, pin, actor.agent_id)
    if progress["snapshot_id"] != snapshot_id or progress["base_head"] != actor.expected_head:
        _reject()
    return content


@dataclass(frozen=True, slots=True)
class ContinuationRequest:
    receiver: HandoffReceiver = field(repr=False)
    source: ContinuationPin
    instruction: str = field(repr=False)
    allowed_paths: tuple[str, ...]
    title: str = "Continue unfinished work"
    required_capabilities: tuple[str, ...] = ()
    execution_seconds: int = 90

    def __post_init__(self) -> None:
        if type(self.receiver) is not HandoffReceiver or type(self.source) is not ContinuationPin:
            _reject()
        _bounded_text(self.instruction, 1500)
        _bounded_text(self.title, 500)
        if (
            not self.instruction.strip()
            or not self.title.strip()
            or type(self.allowed_paths) is not tuple
        ):
            _reject()
        object.__setattr__(self, "allowed_paths", proposal_paths(list(self.allowed_paths)))
        if type(self.required_capabilities) is not tuple or len(self.required_capabilities) > 16:
            _reject()
        for capability in self.required_capabilities:
            _identifier(capability)
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            _reject()
        if type(self.execution_seconds) is not int or not 1 <= self.execution_seconds <= 180:
            _reject()


class OwnerContinuation:
    """Explicit owner request; one new adapter call at most for each failed attempt."""

    def __init__(self, core: Core, scratch: Path, receipts: Path) -> None:
        self._core = core
        self._relay = ControlledRelay(core, scratch, receipts)
        self._queue = RelayQueue(self._relay)

    def pin_failed_progress(
        self,
        project_id: str,
        task_id: str,
        *,
        context_id: str,
        context_version: int,
        content_sha256: str,
        admin_token: str,
    ) -> ContinuationPin:
        """Bind an existing public Core checkpoint to an ended failed attempt."""
        with connect(self._core.db_path) as db:
            db.execute("BEGIN")
            self._core._authenticate_owner(
                db, {"project_id": project_id, "admin_token": admin_token}
            )
            task = self._core._task(db, {"project_id": project_id, "task_id": task_id})
            failed = confirmed_failure(self._relay, db, project_id, task_id)
            if (
                failed is None
                or task["version"] != failed["capture_version"]
                or task["status"] != "running"
            ):
                _reject()
            pin = ContinuationPin(
                task_id,
                task["version"],
                context_id,
                context_version,
                content_sha256,
                failed["launch_sha256"],
                failed["terminal_sha256"],
            )
            _progress(self._relay, db, project_id, pin, "")
            return pin

    @staticmethod
    def _config(request: ContinuationRequest) -> dict[str, Any]:
        return {
            "source": asdict(request.source),
            "receiver_agent_id": request.receiver.agent_id,
            "receiver_session_id": request.receiver.session_id,
            "instruction_sha256": digest(request.instruction),
            "title_sha256": digest(request.title),
            "allowed_paths": list(request.allowed_paths),
            "required_capabilities": list(request.required_capabilities),
            "execution_seconds": request.execution_seconds,
        }

    def _plan(
        self, db: sqlite3.Connection, request: ContinuationRequest, admin_token: str
    ) -> dict[str, Any]:
        receiver, pin = request.receiver, request.source
        project = receiver.project_id
        self._core._authenticate_owner(db, {"project_id": project, "admin_token": admin_token})
        session = self._core._authenticate(db, receiver.authentication(), time.time())
        self._core._authorize_session(db, "create_task", session)
        if session["agent_id"] != receiver.agent_id:
            _reject()
        task = self._core._task(db, {"project_id": project, "task_id": pin.source_task_id})
        if task["version"] != pin.source_task_version or task["status"] not in (
            "running",
            "blocked",
            "failed",
        ):
            _reject()
        failed = confirmed_failure(self._relay, db, project, task["id"])
        if (
            failed is None
            or task["version"] != failed["capture_version"]
            or task["status"] != "running"
            or not isinstance(task["owner_session_id"], str)
            or digest(task["owner_session_id"]) != failed["session_sha256"]
        ):
            _reject()
        if db.execute(
            "SELECT 1 FROM mock_workflow_tasks WHERE task_id=?", (task["id"],)
        ).fetchone():
            _reject()
        content, progress = _progress(self._relay, db, project, pin, receiver.agent_id)
        del content
        if progress["paths"] != request.allowed_paths:
            _reject()
        # Existing execution intents are never released by a coding continuation.
        if db.execute(
            "SELECT 1 FROM candidate_execution_intents i JOIN candidate_verification_jobs j ON j.id=i.job_id AND j.project_id=i.project_id "
            "WHERE i.project_id=? AND (j.left_task_id=? OR j.right_task_id=?)",
            (project, task["id"], task["id"]),
        ).fetchone():
            _reject()
        dependents = []
        for child in db.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY id", (project,)):
            if task["id"] not in json.loads(child["dependencies"]):
                continue
            if (
                child["status"] != "pending"
                or child["version"] >= 2**63 - 2
                or db.execute(
                    "SELECT 1 FROM mock_workflow_tasks WHERE task_id=?", (child["id"],)
                ).fetchone()
            ):
                _reject()
            dependents.append(
                {
                    "task_id": child["id"],
                    "version": child["version"],
                    "dependencies": json.loads(child["dependencies"]),
                }
            )
        return {
            "schema_version": 1,
            "project_id": project,
            **self._config(request),
            "snapshot_id": progress["snapshot_id"],
            "base_head": progress["base_head"],
            "dependencies": json.loads(task["dependencies"]),
            "priority": task["priority"],
            "dependents": dependents,
            "verification": "unverified",
        }

    def preview(self, request: ContinuationRequest, *, admin_token: str) -> dict[str, Any]:
        if type(request) is not ContinuationRequest:
            _reject()
        with connect(self._core.db_path) as db:
            db.execute("BEGIN")
            plan = self._plan(db, request, admin_token)
            return {"plan": plan, "plan_sha256": digest(plan), "model_calls": 0}

    def _prepare(
        self, request: ContinuationRequest, admin_token: str, expected_plan_sha256: str
    ) -> dict[str, Any]:
        project = request.receiver.project_id
        self._relay._authorize_project_owner(project, admin_token)
        try:
            return self._prepare_transaction(request, admin_token, expected_plan_sha256)
        except AgentSyncError as error:
            self._core._audit_denial(
                (project, "owner", project),
                _OPERATION,
                {
                    "project_id": project,
                    "request_id": request.source.launch_sha256,
                    "expected_version": request.source.source_task_version,
                },
                error.code,
            )
            raise

    def _prepare_transaction(
        self, request: ContinuationRequest, admin_token: str, expected_plan_sha256: str
    ) -> dict[str, Any]:
        receiver = request.receiver
        project, launch = receiver.project_id, request.source.launch_sha256
        with connect(self._core.db_path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._core._authenticate_owner(db, {"project_id": project, "admin_token": admin_token})
            old = _saved(db, project, launch)
            if old is not None:
                if (
                    old["config_sha256"] != digest(self._config(request))
                    or old["plan_sha256"] != expected_plan_sha256
                ):
                    _reject()
                return old
            plan = self._plan(db, request, admin_token)
            if digest(plan) != expected_plan_sha256:
                _reject()
            now = time.time()
            session = self._core._authenticate(db, receiver.authentication(), now)
            payload = self._core._validated_payload(
                OPERATIONS["create_task"],
                {
                    **receiver.authentication(),
                    "title": request.title,
                    "description": "Continuation of confirmed failed task "
                    + request.source.source_task_id,
                    "priority": plan["priority"],
                    "dependencies": plan["dependencies"],
                    "request_id": "continuation:" + launch,
                },
            )
            created = self._core._create_task(db, payload, now, session)
            self._core._audit_event(
                db,
                project,
                "agent",
                receiver.agent_id,
                "create_task",
                payload,
                "success",
                "ok",
                created,
            )
            next_version = request.source.source_task_version + 1
            db.execute(
                "UPDATE tasks SET status='failed',version=?,owner_session_id=NULL,lease_hash=NULL,lease_expires_at=NULL,updated_at=? WHERE project_id=? AND id=?",
                (next_version, now, project, request.source.source_task_id),
            )
            for child in plan["dependents"]:
                dependencies = [
                    created["id"] if value == request.source.source_task_id else value
                    for value in child["dependencies"]
                ]
                db.execute(
                    "UPDATE tasks SET dependencies=?,version=version+1,updated_at=? WHERE project_id=? AND id=?",
                    (json.dumps(dependencies), now, project, child["task_id"]),
                )
                self._core._audit_event(
                    db,
                    project,
                    "owner",
                    project,
                    _OPERATION,
                    {"request_id": launch, "expected_version": child["version"]},
                    "success",
                    "dependency_transferred",
                    {"id": child["task_id"], "version": child["version"] + 1},
                )
            pin = asdict(request.source) | {"source_task_version": next_version}
            result = {
                **self._config(request),
                "config_sha256": digest(self._config(request)),
                "plan_sha256": expected_plan_sha256,
                "task_id": created["id"],
                "version": created["version"],
                "source_task_id": request.source.source_task_id,
                "source_version": next_version,
                "snapshot_id": plan["snapshot_id"],
                "base_head": plan["base_head"],
                "pin": pin,
                "transferred_dependents": plan["dependents"],
                "verification": "unverified",
            }
            db.execute(
                "INSERT INTO owner_idempotency VALUES(?,?,?,?,?)",
                (project, _OPERATION, launch, digest(plan), json.dumps(result, sort_keys=True)),
            )
            self._core._audit_event(
                db,
                project,
                "owner",
                project,
                _OPERATION,
                {"request_id": launch, "expected_version": request.source.source_task_version},
                "success",
                "confirmed_failure_continued",
                {"id": request.source.source_task_id, "version": next_version},
            )
            return result

    def status(self, project_id: str, launch_sha256: str, *, admin_token: str) -> dict[str, Any]:
        _identifier(project_id)
        if type(launch_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", launch_sha256) is None:
            _reject()
        with connect(self._core.db_path) as db:
            self._core._authenticate_owner(
                db, {"project_id": project_id, "admin_token": admin_token}
            )
            saved = _saved(db, project_id, launch_sha256)
            if saved is None:
                return {"state": "not_prepared", "verification": "unverified"}
            self._relay._check_receipt_anchor(project_id, require_existing=True)
            self._queue._checked_journal_key(project_id)
            task = self._core._task(db, {"project_id": project_id, "task_id": saved["task_id"]})
            key = self._relay._task_receipt_key(project_id, saved["task_id"])
            admission = self._relay._read_receipt(key, "incomplete", durable=True)
            publication = None
            if admission is not None:
                stored = self._relay._observe_proposal_storage(
                    project_id,
                    saved["task_id"],
                    key,
                    admission,
                    lambda context_id, version: revision(db, project_id, context_id, version),
                )
                if stored is not None:
                    record = stored
                    publication = {
                        "context_id": record["context_id"],
                        "context_version": record["context_version"],
                        "content_sha256": record["content_sha256"],
                        "publication_task_version": record["task_version"],
                        "publication_session_id": saved["receiver_session_id"],
                        "publication_request_id": f"relay:{key}:proposal:publish",
                        "verification": "unverified",
                    }
        prefix = "continuation-" + digest([project_id, launch_sha256])
        intent = self._relay._receipt_store.read(prefix + "-dispatch.json", durable=True)
        state, wave = "prepared", None
        if intent is not None:
            if (
                type(intent) is not dict
                or intent.get("task_id") != saved["task_id"]
                or intent.get("plan_sha256") != saved["plan_sha256"]
            ):
                _reject()
            self._queue._checked_journal_key(project_id)
            row = self._queue._journal.get(
                digest(project_id), digest(["relay-queue-v1", project_id, prefix + "-wave"])
            )
            if row is None:
                state = "unknown"
            else:
                wave = self._queue._outcome(row[1], row[2])
                state = wave.state
        return {
            "state": state,
            "task_id": saved["task_id"],
            "task_status": task["status"],
            "task_version": task["version"],
            "source_task_id": saved["source_task_id"],
            "publication": publication,
            "wave": asdict(wave) if wave is not None else None,
            "verification": "unverified",
        }

    async def run_once(
        self,
        request: ContinuationRequest,
        *,
        admin_token: str,
        expected_plan_sha256: str,
        build_receiver: Callable[[HandoffReceiver, HandoffWorkspace], RelayActor],
        execution_budget_seconds: int = 240,
    ) -> dict[str, Any]:
        if (
            type(request) is not ContinuationRequest
            or type(expected_plan_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256) is None
            or type(execution_budget_seconds) is not int
            or not 1 <= execution_budget_seconds <= 600
        ):
            _reject()
        deadline = asyncio.get_running_loop().time() + execution_budget_seconds
        receiver, launch = request.receiver, request.source.launch_sha256
        project = receiver.project_id
        prefix = "continuation-" + digest([project, launch])
        with connect(self._core.db_path) as db:
            db.execute("BEGIN")
            self._core._authenticate_owner(db, {"project_id": project, "admin_token": admin_token})
            old = _saved(db, project, launch)
            if old is not None and (
                old["config_sha256"] != digest(self._config(request))
                or old["plan_sha256"] != expected_plan_sha256
            ):
                _reject()
            if old is None and digest(self._plan(db, request, admin_token)) != expected_plan_sha256:
                _reject()
        if (
            old is not None
            and self._relay._receipt_store.read(prefix + "-dispatch.json", durable=True) is not None
        ):
            return self.status(project, launch, admin_token=admin_token)
        # A different unfinished member of the prior wave must keep its fence.
        pending = self._queue.owner_observe_pending(project, admin_token=admin_token)
        if pending is not None:
            with connect(self._core.db_path) as db:
                failed = confirmed_failure(self._relay, db, project, request.source.source_task_id)
            if failed is None or failed["wave_sha256"] != pending.wave_id:
                _reject()
            outcome = self._queue.reconcile_pending_from_session(
                project_id=project,
                session_id=receiver.session_id,
                session_token=receiver.session_token,
                expected_wave_id=pending.wave_id,
                admin_token=admin_token,
            )
            if outcome.state != "resolved":
                return {"state": "blocked_by_prior_wave", "verification": "unverified"}
        _check_execution_deadline(deadline)
        saved = self._prepare(request, admin_token, expected_plan_sha256)
        existing = self._relay._receipt_store.read(prefix + "-dispatch.json", durable=True)
        if existing is not None:
            return self.status(project, launch, admin_token=admin_token)
        tree = self._core.execute(
            "create_worktree",
            {
                **receiver.authentication(),
                "task_id": saved["task_id"],
                "snapshot_id": saved["snapshot_id"],
                "request_id": prefix + "-tree",
            },
        )
        tree = self._core.execute(
            "inspect_owned_worktree",
            {
                **receiver.authentication(),
                "task_id": saved["task_id"],
                "worktree_id": tree["worktree_id"],
            },
        )
        if (
            tree["dirty"]
            or tree["snapshot_id"] != saved["snapshot_id"]
            or tree["head_sha"] != saved["base_head"]
        ):
            _reject()
        workspace = HandoffWorkspace(
            saved["task_id"],
            saved["version"],
            tree["worktree_id"],
            tree["head_sha"],
            Path(tree["path"]),
        )
        actor = build_receiver(receiver, workspace)
        if type(actor) is not RelayActor or (
            actor.agent_id,
            actor.profile.project_id,
            actor.profile.session_id,
            actor.session_token,
            actor.worktree_id,
            actor.expected_head,
            actor.profile.root,
        ) != (
            receiver.agent_id,
            project,
            receiver.session_id,
            receiver.session_token,
            workspace.worktree_id,
            workspace.head_sha,
            workspace.path,
        ):
            _reject()
        item = ContinuationQueueItem(
            actor,
            ContinuationInput(
                workspace.task_id,
                workspace.task_version,
                request.instruction,
                request.allowed_paths,
                request.execution_seconds,
                True,
                continuation=ContinuationPin(**saved["pin"]),
            ),
            request.required_capabilities,
        )
        preview = self._queue.preview((item,), admin_token=admin_token, parallel_limit=1)
        if preview.state != "selected":
            return {
                "state": "not_ready",
                "task_id": workspace.task_id,
                "verification": "unverified",
            }
        # Includes the continuation proof in the new exact launch request. The
        # adapter's normal approval/capture callback rechecks it after consent.
        self._queue._check_review_input(
            item, admin_token, self._queue._key(actor, prefix + "-wave")
        )
        _check_execution_deadline(deadline)
        await asyncio.sleep(0)
        intent: dict[str, Any] = {
            "task_id": workspace.task_id,
            "worktree_id": workspace.worktree_id,
            "plan_sha256": expected_plan_sha256,
            "selection_sha256": preview.selection_sha256,
        }
        try:
            self._relay._receipt_store.write(prefix + "-dispatch.json", intent)
        except AgentSyncError as error:
            if error.code != "attempt_already_reserved":
                raise
            if self._relay._receipt_store.read(prefix + "-dispatch.json", durable=True) != intent:
                _reject()
            return self.status(project, launch, admin_token=admin_token)
        _check_execution_deadline(deadline)
        authority = _StartRight(
            workspace.task_id,
            self._queue._key(actor, prefix + "-wave"),
            prefix + "-dispatch.json",
            intent,
        )
        self._relay._continuation_start = authority
        try:
            await self._queue.run_ready_once(
                (item,),
                request_id=prefix + "-wave",
                admin_token=admin_token,
                parallel_limit=1,
                expected_selection_sha256=preview.selection_sha256,
                _execution_deadline=deadline,
                _continuation_authority=authority,
            )
        finally:
            self._relay._continuation_start = None
        return self.status(project, launch, admin_token=admin_token)

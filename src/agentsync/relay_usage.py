"""Explicit local owner reconciliation of controlled-relay usage observations."""

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from agentsync.adapters.approved_launch import _admission_receipts, _valid_digest, digest
from agentsync.controlled_relay import ControlledRelay
from agentsync.core.service import Core
from agentsync.core.usage import RELAY_USAGE_SOURCE, RelayUsageObservation, _ProjectUsage
from agentsync.errors import AgentSyncError
from agentsync.models import AdminAuth
from agentsync.storage.admission import database_admission
from agentsync.storage.database import connect
from agentsync.workspaces.git import physical

_OPERATION = "sync_relay_usage"
_Leg = Literal["first", "second"]


class _SyncRelayUsage(AdminAuth):
    task_id: str = Field(min_length=1, max_length=200)
    scratch_root: str = Field(min_length=1, max_length=4096)
    receipts: str = Field(min_length=1, max_length=4096)


def _boundary() -> AgentSyncError:
    return AgentSyncError(
        "relay_usage_boundary", "Relay usage receipts do not match the saved task and launch.", 409
    )


def _historical_sessions(
    db: sqlite3.Connection, project_id: str, task_id: str, key: str, leg: _Leg
) -> dict[str, tuple[str, str, bool]]:
    """Read Core's own task/session witnesses without reopening a historical session."""
    rows = db.execute(
        "SELECT s.id, s.agent_id, i.operation, i.response FROM idempotency i "
        "JOIN sessions s ON s.id=i.session_id AND s.project_id=i.project_id "
        "JOIN agents a ON a.id=s.agent_id AND a.project_id=i.project_id "
        "WHERE i.project_id=? AND ((i.operation='update_task' AND i.request_id=?) "
        "OR (i.operation='renew_lease' AND i.request_id=?))",
        (project_id, f"relay:{key}:{leg}:running", f"relay:{key}:{leg}:capture"),
    )
    sessions = {}
    captured = set()
    for row in rows:
        session_id = row["id"]
        reply = json.loads(row["response"])
        if type(reply) is not dict or (
            reply.get("id"),
            reply.get("project_id"),
            reply.get("owner_session_id"),
            reply.get("status"),
        ) != (task_id, project_id, session_id, "running"):
            continue
        if row["operation"] == "update_task":
            sessions[session_id] = row["agent_id"]
        else:
            captured.add(session_id)
    return {
        digest(session): (session, digest(agent), session in captured)
        for session, agent in sessions.items()
    }


def _bound_dispatch(
    db: sqlite3.Connection,
    project_id: str,
    task_id: str,
    key: str,
    leg: _Leg,
    mode: str,
    dispatch: dict[str, Any],
) -> tuple[str, Literal["dispatch_pinned", "legacy_two_leg"], bool]:
    launch = dispatch.get("launch_request_sha256")
    agent = dispatch.get("agent_sha256")
    if not _valid_digest(launch) or not _valid_digest(agent):
        raise _boundary()
    sessions = _historical_sessions(db, project_id, task_id, key, leg)
    if "relay_request_id" not in dispatch and "session_sha256" not in dispatch:
        # Historical two-leg request IDs were deterministic and are recoverable
        # from Core's saved running operation. Single/proposal requests depended
        # on an exact reply or proposal contract that is not always recoverable.
        if mode != "two_leg":
            raise AgentSyncError(
                "relay_usage_unsupported",
                "This historical dispatch lacks an exact launch binding.",
                409,
            )
        matches = [
            (pin, captured)
            for pin, (session, owner, captured) in sessions.items()
            if owner == agent
            and digest([project_id, session, task_id, f"relay:{key}:{leg}:launch"]) == launch
        ]
        if len(matches) != 1:
            raise _boundary()
        return matches[0][0], "legacy_two_leg", matches[0][1]

    pin = dispatch.get("session_sha256")
    request = dispatch.get("relay_request_id")
    suffix = {
        "two_leg": f"{leg}:launch",
        "single_codex": r"single-codex:[0-9a-f]{64}",
        "codex_proposal": r"codex-proposal:[0-9a-f]{64}",
        "proposal_review": r"proposal-review:[0-9a-f]{64}",
        "proposal_continuation": r"proposal-continuation:[0-9a-f]{64}",
    }[mode]
    if (
        type(pin) is not str
        or pin not in sessions
        or type(request) is not str
        or re.fullmatch(f"relay:{key}:{suffix}", request) is None
    ):
        raise _boundary()
    session, owner, captured = sessions[pin]
    if owner != agent or digest([project_id, session, task_id, request]) != launch:
        raise _boundary()
    return pin, "dispatch_pinned", captured


def _observe_leg(
    relay: ControlledRelay,
    db: sqlite3.Connection,
    project_id: str,
    task_id: str,
    key: str,
    leg: _Leg,
) -> tuple[RelayUsageObservation | None, str]:
    dispatch = relay._read_receipt(key, leg + "-dispatched", durable=True)
    observed = relay._read_receipt(key, leg + "-observed", durable=True)
    stopped = relay._read_receipt(key, leg + "-stopped", durable=True)
    if dispatch is None and observed is None and stopped is None:
        return None, "not_dispatched"
    incomplete = relay._read_receipt(key, "incomplete", durable=True)
    if not dispatch or not incomplete or (observed is not None and stopped is not None):
        raise _boundary()
    mode = incomplete.get("mode", "two_leg")
    client = dispatch.get("client")
    if (
        mode
        not in (
            "two_leg",
            "single_codex",
            "codex_proposal",
            "proposal_review",
            "proposal_continuation",
        )
        or client not in ("codex", "claude", "cursor")
        or (mode != "two_leg" and leg != "first")
        or (mode in ("single_codex", "codex_proposal") and client != "codex")
        or (mode == "proposal_review" and client != incomplete.get("review_client"))
        or (mode == "proposal_continuation" and client != incomplete.get("continuation_client"))
    ):
        raise _boundary()
    session, binding, captured = _bound_dispatch(db, project_id, task_id, key, leg, mode, dispatch)
    launch = dispatch["launch_request_sha256"]
    admission, consent = _admission_receipts(relay._receipt_store, launch, client, durable=True)
    if admission.state == "unknown":
        raise _boundary()
    if admission.state != "both_reservations_recorded":
        if observed is not None or (stopped is not None and stopped.get("status") != "unknown"):
            raise _boundary()
        return None, admission.state

    attempt = relay._attempt_observation(leg, dispatch, observed, stopped, admission)
    terminal = observed if observed is not None else stopped
    status: Literal["succeeded", "failed", "unknown", "timed_out"] = "unknown"
    if terminal is not None:
        expected = {
            "two_leg": "expected_reply",
            "single_codex": "expected_reply",
            "codex_proposal": "proposal_received",
            "proposal_review": "dependent_review_received",
            "proposal_continuation": "continuation_proposal_received",
        }[mode]
        if (
            attempt.state != "terminal_recorded"
            or attempt.session_sha256 != session
            or attempt.run_sha256 is None
            or attempt.parent_ended is None
            or attempt.timed_out is None
            or (
                (binding == "dispatch_pinned" or "launch_request_sha256" in terminal)
                and terminal.get("launch_request_sha256") != launch
            )
            or (observed is not None and attempt.status != expected)
            or (
                not captured
                and (
                    attempt.status != "unknown"
                    or attempt.parent_ended
                    or attempt.exit_code is not None
                    or attempt.reported_input_tokens is not None
                    or attempt.reported_output_tokens is not None
                )
            )
        ):
            raise _boundary()
        if observed is not None:
            if attempt.timed_out:
                raise _boundary()
            status = "succeeded"
        elif attempt.status in ("failed", "reply_mismatch"):
            if attempt.parent_ended is not True or attempt.exit_code is None or attempt.timed_out:
                raise _boundary()
            status = "failed"
        elif attempt.status == "succeeded":
            # An adapter success observed while stopping is not a matched relay reply.
            if attempt.parent_ended is not True or attempt.exit_code != 0 or attempt.timed_out:
                raise _boundary()
        elif attempt.timed_out and attempt.parent_ended:
            status = "timed_out"
    assert admission.plan_sha256 is not None and consent is not None
    return RelayUsageObservation(
        task_id=task_id,
        leg=leg,
        kind=client,
        agent_sha256=dispatch["agent_sha256"],
        session_sha256=session,
        launch_request_sha256=launch,
        launch_plan_sha256=admission.plan_sha256,
        consent_sha256=consent,
        binding=binding,
        terminal_sha256=digest(terminal) if terminal is not None else None,
        run_sha256=attempt.run_sha256,
        status=status,
        input_tokens=attempt.reported_input_tokens,
        output_tokens=attempt.reported_output_tokens,
        adapter_elapsed_ms=attempt.adapter_elapsed_ms,
    ), "recorded"


def sync_relay_usage(core: Core, payload: dict[str, Any]) -> dict[str, Any]:
    p = core._validated_payload(_SyncRelayUsage, payload)
    project_id, task_id = p["project_id"], p["task_id"]
    with database_admission(core.db_path):
        db = connect(core.db_path)
        actor = None
        try:
            db.execute("BEGIN IMMEDIATE")
            core._authenticate_owner(db, p)
            actor = (project_id, "owner", project_id)
            core._task(db, p)
            scratch, receipts = Path(p["scratch_root"]), Path(p["receipts"])
            for path in (scratch, receipts):
                if not path.is_absolute() or ".." in path.parts:
                    raise _boundary()
                physical(path)
            relay = ControlledRelay(core, scratch, receipts)
            relay._check_receipt_anchor(project_id, require_existing=True)
            key = relay._task_receipt_key(project_id, task_id)
            history = _ProjectUsage.load(db, project_id)
            results = []
            legs: tuple[_Leg, _Leg] = ("first", "second")
            for leg in legs:
                record, state = _observe_leg(relay, db, project_id, task_id, key, leg)
                result: dict[str, Any] = {"leg": leg, "state": state}
                if record is not None:
                    result.update(
                        state=history.merge_relay(record),
                        kind=record.kind,
                        run_id=record.key(project_id),
                    )
                results.append(result)
            now = time.time()
            if any(result["state"] in ("added", "updated") for result in results):
                history.save(db, project_id, now)
            response = {"task_id": task_id, "provenance": RELAY_USAGE_SOURCE, "attempts": results}
            core._audit_event(db, *actor, _OPERATION, p, "success", "ok", response)
            db.commit()
            return response
        except AgentSyncError as error:
            db.rollback()
            core._audit_denial(actor, _OPERATION, p, error.code)
            raise
        except (ValueError, OSError, RecursionError):
            db.rollback()
            boundary_error = _boundary()
            core._audit_denial(actor, _OPERATION, p, boundary_error.code)
            raise boundary_error from None
        except sqlite3.Error:
            db.rollback()
            raise AgentSyncError("storage_error", "Database operation failed.", 503) from None
        finally:
            db.close()

"""Owner-only persistent simulation, one run per dedicated Core project."""

from __future__ import annotations

import asyncio
import json
import math
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, NoReturn

from pydantic import Field

from agentsync.adapters import AdapterTask
from agentsync.core.service import Core, canonical, digest, identifier
from agentsync.dispatch_planning import plan_dispatches
from agentsync.errors import AgentSyncError
from agentsync.mock_run_manager import MockRunManager, MockWorker
from agentsync.mock_workflow import _MARKER, _WORKERS, MockWorkflowTask, _copy_tasks, _copy_workers
from agentsync.mock_workflow_cli import _decompose, _task, _worker
from agentsync.models import AdminAuth
from agentsync.retry_planning import RetryPolicy, plan_retry
from agentsync.storage.admission import database_admission
from agentsync.storage.database import connect

_DRIVER_LEASE = 5.0
_COUNTERS = ("steps", "calls", "requested_output", "estimated_tokens", "estimated_cost")
_TERMINAL = {"completed", "stopped", "cancelled", "unknown"}
_WORKFLOW_AUDIT = "mock_workflow_transition"


class _Write(AdminAuth):
    request_id: str = Field(min_length=1, max_length=200)


class _Change(_Write):
    expected_version: int = Field(ge=1, le=2**63 - 2)


class _Start(_Write):
    config: dict[str, Any]


def _error(code: str, message: str) -> NoReturn:
    raise AgentSyncError(code, message, 409)


def _budget(config: dict[str, Any]) -> dict[str, int]:
    value = config.get("budget")
    if type(value) is not dict or set(value) != {*_COUNTERS, "concurrency"}:
        raise ValueError
    for key, maximum in zip(
        (*_COUNTERS, "concurrency"), (64, 64, 262144, 4000000, 10**15, 8), strict=True
    ):
        if type(value[key]) is not int or not 0 <= value[key] <= maximum:
            raise ValueError
    return value


def _config(value: dict[str, Any]) -> dict[str, Any]:
    if len(value.keys() & {"tasks", "decomposition"}) != 1 or value.keys() - {
        "tasks",
        "decomposition",
        "workers",
        "budget",
        "deadline_seconds",
        "max_attempts_per_task",
    }:
        raise ValueError
    workers = value.get(
        "workers",
        [asdict(worker) | {"capabilities": list(worker.capabilities)} for worker in _WORKERS],
    )
    if type(workers) is not list:
        raise ValueError
    roster = tuple(_worker(row) for row in workers)
    deadline = value.get("deadline_seconds", 60)
    attempts = value.get("max_attempts_per_task", 2)
    if (
        type(deadline) is not int
        or not 1 <= deadline <= 3600
        or type(attempts) is not int
        or not 1 <= attempts <= 3
    ):
        raise ValueError
    if "tasks" in value:
        if type(value["tasks"]) is not list:
            raise ValueError
        tasks = _copy_tasks(tuple(_task(row) for row in value["tasks"]))
        _copy_workers(roster, tasks)
    else:
        _copy_workers(roster, ())
        document = value["decomposition"]
        if type(document) is not dict or set(document) != {"goal", "mock_response", "task_options"}:
            raise ValueError
        if any(type(document[key]) is not str for key in ("goal", "mock_response")):
            raise ValueError
        if (
            type(document["task_options"]) is not list
            or not 1 <= len(document["task_options"]) <= 16
        ):
            raise ValueError
        if any("dependencies" in row for row in document["task_options"]):
            raise ValueError
        _copy_workers(roster, tuple(_task(row) for row in document["task_options"]))
    _budget(value)
    value = value | {
        "workers": workers,
        "deadline_seconds": deadline,
        "max_attempts_per_task": attempts,
    }
    encoded = canonical(value).encode("utf-8")
    if len(encoded) > 60 * 1024:
        raise ValueError
    return json.loads(encoded)


def _charge(kind: str) -> dict[str, int]:
    # A fixed synthetic tariff and input/output estimates charged at reservation.
    # The estimates are planning units, not token upper bounds or provider billing.
    output = 1024 if kind == "decomposition" else 32
    estimate = output + (16384 if kind == "decomposition" else 64)
    return dict(zip(_COUNTERS, (1, 1, output, estimate, estimate * 10), strict=True))


@dataclass(frozen=True, slots=True)
class _Driver:
    run_id: str
    generation: int
    deadline: float
    monotonic_until: float
    credentials: dict[str, dict[str, str]] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _Effect:
    request_id: str
    task_id: str | None
    sequence: int
    agent_id: str | None = None
    task_version: int | None = None
    lease: str | None = field(default=None, repr=False)
    task_label: str | None = None


class OwnerMockWorkflow:
    """Persist simulation state beside Core and drive only an existing dedicated project."""

    def __init__(self, core: Core):
        self._core = core

    @contextmanager
    def _transaction(
        self, payload: dict[str, Any], *, write: bool = True
    ) -> Iterator[tuple[sqlite3.Connection, float]]:
        with database_admission(self._core.db_path):
            db = connect(self._core.db_path)
            actor = None
            try:
                db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                self._core._authenticate_owner(db, payload)
                actor = (payload["project_id"], "owner", payload["project_id"])
                now = time.time()
                if not math.isfinite(now) or not 0 <= now < 2**48:
                    _error("invalid_clock", "Workflow clock is unavailable.")
                yield db, now
                db.commit()
            except AgentSyncError as error:
                db.rollback()
                if write and error.code != "invalid_clock":
                    self._core._audit_denial(actor, _WORKFLOW_AUDIT, payload, error.code)
                raise
            except sqlite3.Error:
                _error("storage_error", "Workflow storage operation failed.")
            finally:
                db.close()

    @staticmethod
    def _run(db: sqlite3.Connection, payload: dict[str, Any]) -> sqlite3.Row:
        run = db.execute(
            "SELECT * FROM mock_workflows WHERE project_id=?", (payload["project_id"],)
        ).fetchone()
        if run is None:
            _error("not_found", "This project has no durable Mock workflow.")
        return run

    @staticmethod
    def _configuration(run: sqlite3.Row) -> dict[str, Any]:
        raw = run["config"]
        if digest(raw) != run["config_sha256"]:
            _error("workflow_boundary", "Stored workflow configuration has changed.")
        try:
            config = _config(json.loads(raw))
            spent = json.loads(run["spent"])
            if (
                set(spent) != set(_COUNTERS)
                or any(
                    type(spent[key]) is not int or not 0 <= spent[key] <= config["budget"][key]
                    for key in _COUNTERS
                )
                or not all(
                    math.isfinite(run[key]) and run[key] >= 0 for key in ("deadline", "last_wall")
                )
                or (
                    run["driver_until"] is not None
                    and (not math.isfinite(run["driver_until"]) or run["driver_until"] < 0)
                )
            ):
                raise ValueError
        except (ValueError, TypeError, RecursionError, KeyError, OverflowError):
            _error("workflow_boundary", "Stored workflow configuration is invalid.")
        return config

    @staticmethod
    def _clock(run: sqlite3.Row, now: float) -> None:
        if now < run["last_wall"]:
            _error("clock_regressed", "Workflow time moved backward.")

    @staticmethod
    def _record_request(
        db: sqlite3.Connection, run: sqlite3.Row, payload: dict[str, Any], operation: str
    ) -> bool:
        request = digest(payload["request_id"])
        pin = digest(canonical([operation, payload.get("expected_version"), run["config_sha256"]]))
        prior = db.execute(
            "SELECT operation,input_sha256 FROM mock_workflow_requests WHERE run_id=? AND request_sha256=?",
            (run["id"], request),
        ).fetchone()
        if prior is not None:
            if tuple(prior) != (operation, pin):
                _error("idempotency_conflict", "Workflow request has different inputs.")
            return False
        if "expected_version" in payload and run["version"] != payload["expected_version"]:
            _error("version_conflict", "Workflow version has changed.")
        count = db.execute(
            "SELECT COUNT(*) FROM mock_workflow_requests WHERE run_id=?", (run["id"],)
        ).fetchone()[0]
        if count >= (256 if operation == "cancel" else 255):
            _error("workflow_capacity", "Workflow request capacity has been reached.")
        db.execute(
            "INSERT INTO mock_workflow_requests VALUES(?,?,?,?)",
            (run["id"], request, operation, pin),
        )
        return True

    def _observe(self, db: sqlite3.Connection, run: sqlite3.Row, now: float) -> dict[str, Any]:
        config = self._configuration(run)
        attempts = [
            dict(row)
            for row in db.execute(
                "SELECT task_id,sequence,kind,state,retry_at,evidence_sha256 FROM mock_workflow_attempts WHERE run_id=? ORDER BY task_id,sequence",
                (run["id"],),
            )
        ]
        active = run["driver_until"] is not None and run["driver_until"] > now
        if not active:
            for row in attempts:
                if row["state"] == "dispatch_intent":
                    row["state"] = "unknown"
        state = "unknown" if any(row["state"] == "unknown" for row in attempts) else run["state"]
        return {
            "run_id": run["id"],
            "project_id": run["project_id"],
            "config_sha256": run["config_sha256"],
            "version": run["version"],
            "generation": run["generation"],
            "state": state,
            "reason": "dispatch_outcome_unknown" if state == "unknown" else run["reason"],
            "deadline": run["deadline"],
            "driver_until": run["driver_until"] if active else None,
            "cancelled": bool(run["cancelled"]),
            "clock_regressed": now < run["last_wall"],
            "budget": config["budget"],
            "reserved": json.loads(run["spent"]),
            "attempts": attempts,
            "tasks": [
                dict(row)
                for row in db.execute(
                    "SELECT t.id,m.label,t.status,t.version FROM mock_workflow_tasks m JOIN tasks t ON t.id=m.task_id WHERE m.run_id=? ORDER BY m.label",
                    (run["id"],),
                )
            ],
            "agent_ids": [
                row[0]
                for row in db.execute(
                    "SELECT agent_id FROM mock_workflow_members WHERE run_id=? ORDER BY position",
                    (run["id"],),
                )
            ],
            "simulation_only": True,
            "verification": "unverified",
            "billing_verified": False,
            "cost_usd": None,
            "estimate_basis": "fixed_mock_v1_10_picodollars_per_estimated_token",
        }

    def status(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(AdminAuth, payload)
        with self._transaction(p, write=False) as (db, now):
            return self._observe(db, self._run(db, p), now)

    def start(self, **payload: Any) -> dict[str, Any]:
        self._sync_context()
        p = self._core._validated_payload(_Start, payload)
        try:
            config = _config(p["config"])
            raw = canonical(config)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
            _error("validation_error", "Invalid durable Mock workflow configuration.")
        with self._transaction(p) as (db, now):
            if p["admin_token"] in raw:
                _error(
                    "validation_error",
                    "Do not include owner credentials in workflow configuration.",
                )
            previous = db.execute(
                "SELECT * FROM mock_workflows WHERE project_id=?", (p["project_id"],)
            ).fetchone()
            if previous is not None:
                if previous["start_request_sha256"] != digest(p["request_id"]) or previous[
                    "config_sha256"
                ] != digest(raw):
                    _error("workflow_exists", "A dedicated project can own only one workflow.")
                return self._observe(db, previous, now)
            if any(
                db.execute(
                    f"SELECT 1 FROM {table} WHERE project_id=? LIMIT 1", (p["project_id"],)
                ).fetchone()
                for table in ("agents", "tasks")
            ):
                _error(
                    "workflow_project_not_empty",
                    "Start requires a dedicated project without agents or tasks.",
                )
            identity = identifier()
            db.execute(
                "INSERT INTO mock_workflows VALUES(?,?,?,?,?,'ready',NULL,1,0,NULL,?,?,?,0)",
                (
                    identity,
                    p["project_id"],
                    digest(p["request_id"]),
                    raw,
                    digest(raw),
                    now + config["deadline_seconds"],
                    now,
                    canonical(dict.fromkeys(_COUNTERS, 0)),
                ),
            )
            run = self._run(db, p)
            self._record_request(db, run, p, "start")
            for position, worker in enumerate(config["workers"]):
                actor = self._core._register_agent(
                    db,
                    p | {"name": worker["label"], "capabilities": worker["capabilities"]},
                    now,
                    None,
                )
                self._core._owner_set_agent_roles(
                    db,
                    p
                    | {
                        "agent_id": actor["agent_id"],
                        "roles": ["worker", "reviewer"],
                        "expected_version": 1,
                    },
                    now,
                )
                for operation in ("register_agent", "set_agent_roles"):
                    self._core._audit_event(
                        db,
                        p["project_id"],
                        "owner",
                        p["project_id"],
                        operation,
                        {"request_id": p["request_id"]},
                        "success",
                        "ok",
                        {"agent_id": actor["agent_id"]},
                    )
                db.execute(
                    "INSERT INTO mock_workflow_members VALUES(?,?,?,?)",
                    (identity, position, actor["agent_id"], actor["session_id"]),
                )
            if "decomposition" in config:
                self._schedule(db, identity, None, 1, "decomposition", now)
            driver = self._take_driver(db, run, config, now)
            if "tasks" in config:
                self._create_tasks(
                    db, driver, _copy_tasks(tuple(_task(row) for row in config["tasks"])), now
                )
            self._audit(db, p, "start", driver.run_id)
        return self._drive(p, driver, config)

    def resume(self, **payload: Any) -> dict[str, Any]:
        self._sync_context()
        p = self._core._validated_payload(_Change, payload)
        with self._transaction(p) as (db, now):
            run = self._run(db, p)
            config = self._configuration(run)
            self._clock(run, now)
            if not self._record_request(db, run, p, "resume") or run["state"] in _TERMINAL:
                return self._observe(db, run, now)
            if run["driver_until"] is not None and now < run["driver_until"]:
                _error("workflow_driver_active", "A workflow driver still holds its reservation.")
            if self._close_interrupted(db, run, now):
                return self._observe(db, self._run(db, p), now)
            driver = self._take_driver(db, run, config, now)
            self._audit(db, p, "resume", driver.run_id)
        return self._drive(p, driver, config)

    def cancel(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_Change, payload)
        with self._transaction(p) as (db, now):
            run = self._run(db, p)
            self._configuration(run)
            if (
                not self._record_request(db, run, p, "cancel")
                or run["state"] in _TERMINAL
                or run["cancelled"]
            ):
                return self._observe(db, run, now)
            db.execute(
                "UPDATE mock_workflows SET cancelled=1,version=version+1,last_wall=? WHERE id=?",
                (max(now, run["last_wall"]), run["id"]),
            )
            self._audit(db, p, "cancel", run["id"])
            run = self._run(db, p)
            if run["driver_until"] is None or now >= run["driver_until"]:
                self._close_interrupted(db, run, now)
            return self._observe(db, self._run(db, p), now)

    @staticmethod
    def _sync_context() -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        _error(
            "workflow_async_context", "Use the synchronous workflow driver outside the event loop."
        )

    def _audit(
        self,
        db: sqlite3.Connection,
        p: dict[str, Any],
        phase: str,
        run_id: str,
        request_id: str | None = None,
    ) -> None:
        self._core._audit_event(
            db,
            p["project_id"],
            "owner",
            p["project_id"],
            _WORKFLOW_AUDIT,
            {"request_id": request_id or p["request_id"]},
            "success",
            phase,
            {"id": run_id},
        )

    def _members(
        self, db: sqlite3.Connection, run: sqlite3.Row, config: dict[str, Any]
    ) -> list[sqlite3.Row]:
        rows = db.execute(
            "SELECT m.*,a.project_id,a.name,a.capabilities,p.roles,s.expires_at,s.agent_id AS session_agent,s.project_id AS session_project "
            "FROM mock_workflow_members m JOIN agents a ON a.id=m.agent_id "
            "JOIN agent_memberships p ON p.agent_id=m.agent_id AND p.project_id=a.project_id "
            "JOIN sessions s ON s.id=m.session_id WHERE m.run_id=? ORDER BY m.position",
            (run["id"],),
        ).fetchall()
        if len(rows) != len(config["workers"]):
            _error("workflow_boundary", "Workflow membership has changed.")
        for row, worker in zip(rows, config["workers"], strict=True):
            if (
                row["project_id"] != run["project_id"]
                or row["session_project"] != run["project_id"]
                or row["session_agent"] != row["agent_id"]
                or row["name"] != worker["label"]
                or json.loads(row["capabilities"]) != worker["capabilities"]
                or set(json.loads(row["roles"])) != {"worker", "reviewer"}
            ):
                _error(
                    "workflow_membership_changed",
                    "Workflow member authority or configuration has changed.",
                )
        return rows

    def _take_driver(
        self, db: sqlite3.Connection, run: sqlite3.Row, config: dict[str, Any], now: float
    ) -> _Driver:
        credentials = {}
        for row in self._members(db, run, config):
            db.execute(
                "UPDATE sessions SET token_hash=?,expires_at=0 WHERE id=?",
                (digest(secrets.token_urlsafe(32)), row["session_id"]),
            )
            identity, token = identifier(), secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                (identity, run["project_id"], row["agent_id"], digest(token), now, now, now + 3600),
            )
            db.execute(
                "UPDATE mock_workflow_members SET session_id=? WHERE run_id=? AND agent_id=?",
                (identity, run["id"], row["agent_id"]),
            )
            # Keep an accepted transfer tied to the same member when an old
            # session is retired. This changes only this run's pending tasks.
            db.execute(
                "UPDATE handoffs SET reservation_expires_at=? WHERE assigned_agent_id=? AND status='accepted' "
                "AND task_id IN (SELECT t.id FROM tasks t JOIN mock_workflow_tasks m ON m.task_id=t.id "
                "WHERE m.run_id=? AND t.status='pending' AND t.version=handoffs.task_version)",
                (min(run["deadline"], now + 300), row["agent_id"], run["id"]),
            )
            credentials[row["agent_id"]] = {
                "project_id": run["project_id"],
                "session_id": identity,
                "session_token": token,
            }
        generation = run["generation"] + 1
        db.execute(
            "UPDATE mock_workflows SET state='running',reason=NULL,generation=?,driver_until=?,last_wall=?,version=version+1 WHERE id=?",
            (generation, now + _DRIVER_LEASE, now, run["id"]),
        )
        return _Driver(
            run["id"],
            generation,
            run["deadline"],
            time.monotonic() + (run["deadline"] - now),
            credentials,
        )

    def _core_call(
        self,
        db: sqlite3.Connection,
        driver: _Driver,
        agent: str,
        operation: str,
        now: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        from agentsync.models import OPERATIONS

        payload = self._core._validated_payload(
            OPERATIONS[operation], driver.credentials[agent] | kwargs
        )
        session = self._core._authenticate(db, payload, now)
        self._core._authorize_session(db, operation, session)
        result: dict[str, Any] = getattr(self._core, "_" + operation)(db, payload, now, session)
        self._core._audit_event(
            db, payload["project_id"], "agent", agent, operation, payload, "success", "ok", result
        )
        return result

    @staticmethod
    def _revoke_sessions(db: sqlite3.Connection, run_id: str) -> None:
        sessions = db.execute(
            "SELECT session_id FROM mock_workflow_members WHERE run_id=?", (run_id,)
        )
        for session in sessions:
            db.execute(
                "UPDATE sessions SET token_hash=?,expires_at=0 WHERE id=?",
                (digest(secrets.token_urlsafe(32)), session[0]),
            )

    @staticmethod
    def _schedule(
        db: sqlite3.Connection,
        run_id: str,
        task_id: str | None,
        sequence: int,
        kind: str,
        retry_at: float,
    ) -> None:
        request = "mock-workflow-" + digest(canonical([run_id, task_id, sequence, kind]))
        db.execute(
            "INSERT INTO mock_workflow_attempts VALUES(?,?,?,?,?,'scheduled',?,NULL,NULL,NULL)",
            (run_id, request, task_id, sequence, kind, retry_at),
        )

    def _create_tasks(
        self,
        db: sqlite3.Connection,
        driver: _Driver,
        tasks: tuple[MockWorkflowTask, ...],
        now: float,
    ) -> None:
        actor = next(iter(driver.credentials))
        known: dict[str, str] = {}
        for task in tasks:
            record = self._core_call(
                db,
                driver,
                actor,
                "create_task",
                now,
                title=task.label,
                description=_MARKER,
                priority=task.priority,
                dependencies=[known[label] for label in task.dependencies],
                request_id=f"{driver.run_id}:{task.label}",
            )
            task_id = known[task.label] = record["id"]
            db.execute(
                "INSERT INTO mock_workflow_tasks VALUES(?,?,?)",
                (driver.run_id, task_id, task.label),
            )
            self._schedule(db, driver.run_id, task_id, 1, "task", now)

    @staticmethod
    def _finish_run(
        db: sqlite3.Connection, run: sqlite3.Row, now: float, state: str, reason: str | None = None
    ) -> None:
        db.execute(
            "UPDATE mock_workflows SET state=?,reason=?,driver_until=NULL,last_wall=?,version=version+1 WHERE id=?",
            (state, reason, max(now, run["last_wall"]), run["id"]),
        )
        if state in _TERMINAL:
            OwnerMockWorkflow._revoke_sessions(db, run["id"])

    def _close_interrupted(self, db: sqlite3.Connection, run: sqlite3.Row, now: float) -> bool:
        unknown = db.execute(
            "SELECT 1 FROM mock_workflow_attempts WHERE run_id=? AND state IN ('dispatch_intent','unknown') LIMIT 1",
            (run["id"],),
        ).fetchone()
        if unknown is not None:
            db.execute(
                "UPDATE mock_workflow_attempts SET state='unknown' WHERE run_id=? AND state='dispatch_intent'",
                (run["id"],),
            )
            self._finish_run(db, run, now, "unknown", "dispatch_outcome_unknown")
        elif run["cancelled"]:
            self._finish_run(db, run, now, "cancelled", "owner_cancelled")
        elif now >= run["deadline"]:
            self._finish_run(db, run, now, "stopped", "deadline_exhausted")
        else:
            return False
        db.execute(
            "UPDATE mock_workflow_attempts SET state='abandoned' WHERE run_id=? AND state IN ('scheduled','reserved')",
            (run["id"],),
        )
        return True

    def _release_driver(self, p: dict[str, Any], driver: _Driver) -> None:
        # If Python unwinds normally after an interruption, durably release this
        # generation after cleaning up its local simulations. Process death still
        # relies on expiry, and any unresolved intent remains fenced either way.
        with self._transaction(p) as (db, now):
            run = self._run(db, p)
            if run["generation"] != driver.generation or run["driver_until"] is None:
                return
            if not self._close_interrupted(db, run, now):
                self._finish_run(db, run, now, "ready")

    def _driver_run(
        self, db: sqlite3.Connection, p: dict[str, Any], driver: _Driver, now: float
    ) -> sqlite3.Row:
        run = self._run(db, p)
        self._clock(run, now)
        if (
            run["id"] != driver.run_id
            or run["generation"] != driver.generation
            or run["driver_until"] is None
            or now >= run["driver_until"]
        ):
            _error("workflow_driver_lost", "The workflow driver reservation is no longer current.")
        return run

    def _deadline(self, driver: _Driver, now: float) -> bool:
        return now >= driver.deadline or time.monotonic() >= driver.monotonic_until

    @staticmethod
    def _specifications(config: dict[str, Any]) -> dict[str, MockWorkflowTask]:
        definitions = config.get("tasks")
        if definitions is None:
            definitions = config["decomposition"]["task_options"]
        return {row["label"]: _task(row) for row in definitions}

    def _reserve(
        self,
        db: sqlite3.Connection,
        run: sqlite3.Row,
        rows: list[sqlite3.Row],
        config: dict[str, Any],
        now: float,
    ) -> tuple[list[str], str | None]:
        budget = config["budget"]
        spent = json.loads(run["spent"])
        result: list[str] = []
        blocked = None
        for row in rows:
            if len(result) == budget["concurrency"]:
                blocked = "concurrency_budget_exhausted"
                break
            if row["state"] == "scheduled":
                charge = _charge(row["kind"])
                over = next(
                    (name for name in _COUNTERS if spent[name] + charge[name] > budget[name]), None
                )
                if over is not None:
                    blocked = over + "_budget_exhausted"
                    break
                spent = {name: spent[name] + charge[name] for name in _COUNTERS}
            db.execute(
                "UPDATE mock_workflow_attempts SET state='reserved',generation=? WHERE request_id=?",
                (run["generation"], row["request_id"]),
            )
            result.append(row["request_id"])
        db.execute(
            "UPDATE mock_workflows SET spent=?,driver_until=?,last_wall=?,version=version+1 WHERE id=?",
            (canonical(spent), now + _DRIVER_LEASE, now, run["id"]),
        )
        return result, blocked

    def _next_batch(self, p: dict[str, Any], driver: _Driver, config: dict[str, Any]) -> list[str]:
        with self._transaction(p) as (db, now):
            run = self._driver_run(db, p, driver, now)
            if run["cancelled"] or self._deadline(driver, now):
                self._stop(
                    db, run, now, "owner_cancelled" if run["cancelled"] else "deadline_exhausted"
                )
                return []
            self._members(db, run, config)
            outstanding = db.execute(
                "SELECT * FROM mock_workflow_attempts WHERE run_id=? AND state IN ('scheduled','reserved') ORDER BY retry_at,request_id",
                (run["id"],),
            ).fetchall()
            if not outstanding:
                failed = db.execute(
                    "SELECT 1 FROM mock_workflow_attempts WHERE run_id=? AND kind='decomposition' AND state='failed' UNION ALL SELECT 1 FROM mock_workflow_tasks m JOIN tasks t ON t.id=m.task_id WHERE m.run_id=? AND t.status!='completed'",
                    (run["id"], run["id"]),
                ).fetchone()
                if failed:
                    self._stop(db, run, now, "task_attempts_exhausted")
                else:
                    self._finish_run(db, run, now, "completed")
                return []
            if any(
                not isinstance(row["retry_at"], (float, int))
                or not math.isfinite(row["retry_at"])
                or not 0 <= row["retry_at"] <= run["deadline"]
                for row in outstanding
            ):
                _error("workflow_boundary", "Stored retry timing is invalid.")
            if outstanding[0]["kind"] == "decomposition":
                candidates = outstanding
            else:
                state = self._core._get_project_state(db, p, now, None)
                members = set(driver.credentials)
                current_sessions = {item["session_id"] for item in driver.credentials.values()}
                state["agents"] = [row for row in state["agents"] if row["id"] in members]
                state["sessions"] = [
                    row for row in state["sessions"] if row["id"] in current_sessions
                ]
                tasks = db.execute(
                    "SELECT task_id,label FROM mock_workflow_tasks WHERE run_id=?", (run["id"],)
                ).fetchall()
                specs = self._specifications(config)
                requirements: dict[str, tuple[str, ...]] = {
                    row["task_id"]: (specs[row["label"]].capability,) for row in tasks
                }
                pending = {row["task_id"]: row for row in outstanding if row["retry_at"] <= now}
                state["tasks"] = [row for row in state["tasks"] if row["id"] in requirements]
                db.execute(
                    "UPDATE handoffs SET reservation_expires_at=? WHERE status='accepted' "
                    "AND task_id IN (SELECT t.id FROM tasks t JOIN mock_workflow_tasks m ON m.task_id=t.id "
                    "WHERE m.run_id=? AND t.status='pending' AND t.version=handoffs.task_version)",
                    (min(run["deadline"], now + 300), run["id"]),
                )
                assigned = dict(
                    db.execute(
                        "SELECT h.task_id,h.assigned_agent_id FROM handoffs h JOIN tasks t ON t.id=h.task_id "
                        "JOIN mock_workflow_tasks m ON m.task_id=t.id WHERE m.run_id=? AND h.status='accepted' "
                        "AND t.status='pending' AND t.version=h.task_version",
                        (run["id"],),
                    )
                )
                # The planner sees accepted transfer reservations and dependency
                # completion. Suppress future retry candidates, but retain them as dependencies.
                for task in state["tasks"]:
                    if task["status"] in {"completed", "failed", "cancelled"}:
                        task["owner_session_id"] = (
                            None  # Historical owner is outside this dispatch roster.
                        )
                    if task["id"] in assigned:
                        task["assigned_agent_id"] = assigned[task["id"]]
                        task["assignment_expires_at"] = min(run["deadline"], now + 300)
                    if task["status"] == "pending" and task["id"] not in pending:
                        task["status"] = "cancelled"
                db.execute(
                    "UPDATE sessions SET heartbeat_at=? WHERE id IN (SELECT session_id FROM mock_workflow_members WHERE run_id=?)",
                    (now, run["id"]),
                )
                for session in state["sessions"]:
                    session["heartbeat_at"] = now
                    session["online"] = session["expires_at"] > now
                selection = plan_dispatches(
                    state,
                    project_id=p["project_id"],
                    worker_agent_ids=tuple(driver.credentials),
                    now=now,
                    global_limit=max(1, config["budget"]["concurrency"]),
                    per_agent_limit=1,
                    limit=8,
                    required_capabilities=requirements,
                )
                candidates = sorted(
                    (pending[choice.task_id] for choice in selection.dispatches),
                    key=lambda row: row["state"] != "reserved",
                )
                for choice in selection.dispatches:
                    db.execute(
                        "UPDATE mock_workflow_attempts SET agent_id=? WHERE request_id=?",
                        (choice.agent_id, pending[choice.task_id]["request_id"]),
                    )
            if not candidates:
                if any(row["retry_at"] > now for row in outstanding):
                    self._finish_run(db, run, now, "waiting", "retry_scheduled")
                else:
                    self._stop(db, run, now, "no_eligible_tasks")
                return []
            reserved, blocked = self._reserve(db, run, candidates, config, now)
            if reserved:
                self._audit(db, p, "reserve", run["id"], reserved[0])
            if not reserved and blocked:
                self._stop(db, run, now, blocked)
            return reserved

    def _stop(self, db: sqlite3.Connection, run: sqlite3.Row, now: float, reason: str) -> None:
        db.execute(
            "UPDATE mock_workflow_attempts SET state='abandoned' WHERE run_id=? AND state IN ('scheduled','reserved')",
            (run["id"],),
        )
        self._finish_run(
            db, run, now, "cancelled" if reason == "owner_cancelled" else "stopped", reason
        )

    def _dispatch(
        self, p: dict[str, Any], driver: _Driver, config: dict[str, Any], request_id: str
    ) -> _Effect | None:
        with self._transaction(p) as (db, now):
            run = self._driver_run(db, p, driver, now)
            if run["cancelled"] or self._deadline(driver, now):
                return None
            self._members(db, run, config)
            attempt = db.execute(
                "SELECT * FROM mock_workflow_attempts WHERE run_id=? AND request_id=? AND state='reserved' AND generation=?",
                (run["id"], request_id, driver.generation),
            ).fetchone()
            if attempt is None:
                _error("workflow_boundary", "Workflow attempt reservation does not match.")
            effect = _Effect(
                request_id, attempt["task_id"], attempt["sequence"], attempt["agent_id"]
            )
            if effect.task_id is not None:
                assert effect.agent_id is not None
                target = db.execute(
                    "SELECT label FROM mock_workflow_tasks WHERE run_id=? AND task_id=?",
                    (run["id"], effect.task_id),
                ).fetchone()
                if target is None:
                    _error("workflow_boundary", "Workflow task binding is missing.")
                task = self._core._task(db, p | {"task_id": effect.task_id})
                claimed = self._core_call(
                    db,
                    driver,
                    effect.agent_id,
                    "claim_task",
                    now,
                    task_id=effect.task_id,
                    expected_version=task["version"],
                    lease_seconds=60,
                    request_id=request_id + ":claim",
                )
                active = self._core_call(
                    db,
                    driver,
                    effect.agent_id,
                    "update_task",
                    now,
                    task_id=effect.task_id,
                    expected_version=claimed["version"],
                    lease_token=claimed["lease_token"],
                    status="running",
                    result=_MARKER,
                    request_id=request_id + ":run",
                )
                effect = _Effect(
                    request_id,
                    effect.task_id,
                    effect.sequence,
                    effect.agent_id,
                    active["version"],
                    claimed["lease_token"],
                    target["label"],
                )
            db.execute(
                "UPDATE mock_workflow_attempts SET state='dispatch_intent' WHERE request_id=?",
                (request_id,),
            )
            db.execute(
                "UPDATE mock_workflows SET driver_until=?,last_wall=?,version=version+1 WHERE id=?",
                (now + _DRIVER_LEASE, now, run["id"]),
            )
            self._audit(db, p, "dispatch", run["id"], request_id)
            return effect

    def _before_effect(self, p: dict[str, Any], driver: _Driver, config: dict[str, Any]) -> bool:
        with self._transaction(p, write=False) as (db, now):
            run = self._driver_run(db, p, driver, now)
            self._members(db, run, config)
            return bool(run["cancelled"] or self._deadline(driver, now))

    def _terminal(
        self,
        p: dict[str, Any],
        driver: _Driver,
        config: dict[str, Any],
        effect: _Effect,
        outcome: str,
        *,
        tasks: tuple[MockWorkflowTask, ...] = (),
        mock_run_id: str | None = None,
    ) -> None:
        with self._transaction(p) as (db, now):
            run = self._driver_run(db, p, driver, now)
            self._members(db, run, config)
            attempt = db.execute(
                "SELECT state,task_id,agent_id,generation FROM mock_workflow_attempts WHERE run_id=? AND request_id=?",
                (run["id"], effect.request_id),
            ).fetchone()
            if attempt is None or tuple(attempt) != (
                "dispatch_intent",
                effect.task_id,
                effect.agent_id,
                driver.generation,
            ):
                _error(
                    "workflow_boundary", "Workflow terminal observation does not match dispatch."
                )
            disposition = (
                "cancelled" if run["cancelled"] or self._deadline(driver, now) else outcome
            )
            if effect.task_id is None:
                if disposition == "succeeded":
                    self._create_tasks(db, driver, tasks, now)
            else:
                self._settle_task(db, run, driver, config, effect, disposition, now)
            evidence = digest(
                canonical(
                    [
                        effect.request_id,
                        effect.task_id,
                        effect.sequence,
                        driver.generation,
                        mock_run_id,
                        outcome,
                    ]
                )
            )
            db.execute(
                "UPDATE mock_workflow_attempts SET state=?,evidence_sha256=? WHERE request_id=?",
                (outcome, evidence, effect.request_id),
            )
            db.execute(
                "UPDATE mock_workflows SET driver_until=?,last_wall=?,version=version+1 WHERE id=?",
                (now + _DRIVER_LEASE, now, run["id"]),
            )
            self._audit(db, p, "terminal", run["id"], effect.request_id)

    def _settle_task(
        self,
        db: sqlite3.Connection,
        run: sqlite3.Row,
        driver: _Driver,
        config: dict[str, Any],
        effect: _Effect,
        outcome: str,
        now: float,
    ) -> None:
        task_id, agent = effect.task_id, effect.agent_id
        assert task_id is not None and agent is not None
        assert effect.task_label is not None
        spec = self._specifications(config)[effect.task_label]
        payload = {
            "task_id": task_id,
            "expected_version": effect.task_version,
            "lease_token": effect.lease,
        }

        def transition(status: str) -> dict[str, Any]:
            return self._core_call(
                db,
                driver,
                agent,
                "update_task",
                now,
                **payload,
                status=status,
                result=_MARKER,
                request_id=effect.request_id + ":" + status,
            )

        if outcome == "cancelled":
            transition("cancelled")
        elif outcome == "failed":
            failed = transition("failed")
            if effect.sequence == 1:
                decision = plan_retry(
                    RetryPolicy(max_attempts=config["max_attempts_per_task"]),
                    attempts_used=1,
                    failure_kind="rate_limited"
                    if spec.first_retry_after_seconds is not None
                    else "transient_error",
                    outcome_confirmed=True,
                    now=now,
                    deadline=driver.deadline,
                    retry_after_seconds=spec.first_retry_after_seconds,
                )
                if decision.retry_at is not None:
                    db.execute(
                        "UPDATE tasks SET status='pending',version=version+1,owner_session_id=NULL,updated_at=? WHERE id=? AND version=? AND status='failed'",
                        (now, task_id, failed["version"]),
                    )
                    self._schedule(
                        db, run["id"], task_id, effect.sequence + 1, "task", decision.retry_at
                    )
        else:
            transfer = db.execute(
                "SELECT sender_agent_id,recipient_agent_id FROM handoffs WHERE project_id=? AND task_id=? AND status='accepted'",
                (run["project_id"], task_id),
            ).fetchone()
            if spec.handoff_on_success and transfer is None:
                if effect.sequence < config["max_attempts_per_task"]:
                    self._handoff(db, run, driver, config, effect, now, spec)
                else:
                    transition("failed")
                return
            reviewer = next(
                identity
                for identity in driver.credentials
                if identity != agent and (transfer is None or identity not in tuple(transfer))
            )
            submitted = transition("review")
            self._core_call(
                db,
                driver,
                reviewer,
                "review_task",
                now,
                task_id=task_id,
                expected_version=submitted["version"],
                accept=True,
                evidence=_MARKER,
                request_id=effect.request_id + ":review",
            )

    def _handoff(
        self,
        db: sqlite3.Connection,
        run: sqlite3.Row,
        driver: _Driver,
        config: dict[str, Any],
        effect: _Effect,
        now: float,
        spec: MockWorkflowTask,
    ) -> None:
        task_id, agent = effect.task_id, effect.agent_id
        assert task_id is not None and agent is not None
        recipient = next(
            identity
            for identity, worker in zip(driver.credentials, config["workers"], strict=True)
            if identity != agent and spec.capability in worker["capabilities"]
        )
        request = effect.request_id
        context = self._core_call(
            db,
            driver,
            agent,
            "publish_context",
            now,
            kind="progress",
            title=spec.label,
            content=_MARKER,
            request_id=request + ":context",
        )
        handoff = self._core_call(
            db,
            driver,
            agent,
            "submit_handoff",
            now,
            task_id=task_id,
            expected_version=effect.task_version,
            lease_token=effect.lease,
            target_agent_id=recipient,
            package={
                "summary": _MARKER,
                "context_refs": [
                    {"context_id": context["context_id"], "version": context["version"]}
                ],
            },
            request_id=request + ":handoff",
        )
        accepted = self._core_call(
            db,
            driver,
            recipient,
            "resolve_handoff",
            now,
            handoff_id=handoff["id"],
            expected_version=handoff["task_version"],
            accept=True,
            request_id=request + ":accept",
        )
        if accepted["status"] != "accepted" or accepted["assigned_agent_id"] != recipient:
            _error("workflow_boundary", "Workflow handoff did not preserve its recipient.")
        db.execute(
            "UPDATE handoffs SET reservation_expires_at=? WHERE id=?",
            (min(driver.deadline, now + 300), accepted["id"]),
        )
        self._schedule(db, run["id"], task_id, effect.sequence + 1, "task", now)

    def _drive(self, p: dict[str, Any], driver: _Driver, config: dict[str, Any]) -> dict[str, Any]:
        try:
            asyncio.run(self._run_effects(p, driver, config))
        except BaseException as error:
            try:
                self._release_driver(p, driver)
            except AgentSyncError as release_error:
                error.add_note(f"Workflow driver release deferred: {release_error.code}")
            raise
        return self.status(project_id=p["project_id"], admin_token=p["admin_token"])

    async def _run_effects(
        self, p: dict[str, Any], driver: _Driver, config: dict[str, Any]
    ) -> None:
        manager = MockRunManager(
            p["project_id"],
            tuple(
                MockWorker(agent, creds["session_id"])
                for agent, creds in driver.credentials.items()
            ),
            global_limit=max(1, config["budget"]["concurrency"]),
            max_runs=64,
        )
        definitions = self._specifications(config)
        active: list[tuple[_Effect, str, MockWorkflowTask]] = []
        try:
            while batch := self._next_batch(p, driver, config):
                for request_id in batch:
                    effect = self._dispatch(p, driver, config, request_id)
                    if effect is None:
                        break
                    if self._before_effect(p, driver, config):
                        self._terminal(p, driver, config, effect, "cancelled")
                        break
                    if effect.task_id is None:
                        try:
                            tasks = await _decompose(config["decomposition"])
                            _copy_workers(tuple(_worker(row) for row in config["workers"]), tasks)
                        except ValueError:
                            self._terminal(p, driver, config, effect, "failed")
                        else:
                            self._terminal(p, driver, config, effect, "succeeded", tasks=tasks)
                        continue
                    assert effect.agent_id is not None
                    assert effect.task_label is not None
                    spec = definitions[effect.task_label]
                    started = await manager.start_task(
                        effect.agent_id,
                        AdapterTask(
                            p["project_id"],
                            driver.credentials[effect.agent_id]["session_id"],
                            effect.task_id,
                            effect.request_id,
                            _MARKER,
                            30,
                        ),
                    )
                    active.append((effect, started.run.run_id, spec))
                while active:
                    effect, run_id, spec = active[0]
                    if self._before_effect(p, driver, config):
                        ended = await manager.cancel_task(run_id)
                        if ended.run.status != "cancelled":
                            _error("workflow_boundary", "Mock cancellation could not be confirmed.")
                    else:
                        fail = effect.sequence == 1 and (
                            spec.fail_first_attempt or spec.first_retry_after_seconds is not None
                        )
                        ended = await manager.finish_mock_run(run_id, output=_MARKER, failed=fail)
                    result = await manager.get_result(run_id)
                    if (
                        result.result.run != ended.run
                        or ended.run.task_id != effect.task_id
                        or ended.run.request_id != effect.request_id
                        or ended.agent_id != effect.agent_id
                        or ended.run.status not in {"succeeded", "failed", "cancelled"}
                    ):
                        _error(
                            "workflow_boundary",
                            "Mock terminal result did not match the admitted attempt.",
                        )
                    self._terminal(p, driver, config, effect, ended.run.status, mock_run_id=run_id)
                    active.pop(0)
        finally:
            # A lost driver may cancel only its own in-process Mock simulations.
            # Uncommitted terminal results remain unknown in the durable ledger.
            for _, run_id, _ in active:
                if (await manager.get_status(run_id)).run.status == "running":
                    await manager.cancel_task(run_id)

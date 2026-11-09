"""Private durable admission and completion for controlled relay waves."""

from __future__ import annotations

import json
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from agentsync.errors import AgentSyncError
from agentsync.workspaces.git import physical

_APPLICATION_ID = 0x41535751
_VERSION = 1
_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")
JournalState = Literal["admitted", "incomplete", "resolved"]


def _unavailable() -> AgentSyncError:
    return AgentSyncError("wave_journal_unavailable", "The private relay wave journal is unavailable.", 409)


def _reject(code: str, message: str) -> AgentSyncError:
    return AgentSyncError(code, message, 409)


class RelayWaveJournal:
    """Record one project fence until every admitted relay is observed.

    Result and fence release share a transaction. An admitted or incomplete
    row continues to block new waves across process restarts. The journal never
    treats a missing result as a failed or safely repeatable remote action.
    """

    def __init__(self, private_directory: Path) -> None:
        if not isinstance(private_directory, Path) or not private_directory.is_absolute():
            raise _unavailable()
        self._directory_identity = physical(private_directory)
        if not private_directory.is_dir():
            raise _unavailable()
        self._path = private_directory / "relay-waves.sqlite3"

    def _check_path(self) -> bool:
        if physical(self._path.parent) != self._directory_identity:
            raise _unavailable()
        sidecars = [self._path.with_name(self._path.name + suffix) for suffix in _SIDECAR_SUFFIXES]
        present = [self._check_file(path) for path in sidecars]
        exists = self._check_file(self._path)
        if not exists and any(present):
            raise _unavailable()
        return exists

    @staticmethod
    def _check_file(path: Path) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            raise _unavailable() from None
        if (
            not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400
        ):
            raise _unavailable()
        return True

    @staticmethod
    def _check_schema(db: sqlite3.Connection, *, initialize: bool) -> None:
        application_id = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if application_id == _APPLICATION_ID and version == _VERSION:
            return
        if (
            not initialize
            or application_id != 0
            or version != 0
            or db.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is not None
        ):
            raise _unavailable()
        db.execute(
            "CREATE TABLE relay_waves ("
            "project_key TEXT NOT NULL, request_key TEXT NOT NULL, "
            "state TEXT NOT NULL CHECK(state IN ('admitted','incomplete','resolved')), "
            "tasks_json TEXT NOT NULL, results_json TEXT, PRIMARY KEY(project_key,request_key), "
            "CHECK((state='admitted')=(results_json IS NULL)))"
        )
        db.execute(
            "CREATE UNIQUE INDEX relay_wave_project_fence ON relay_waves(project_key) "
            "WHERE state IN ('admitted','incomplete')"
        )
        db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
        db.execute(f"PRAGMA user_version={_VERSION}")

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        db = None
        try:
            self._check_path()
            db = sqlite3.connect(self._path, timeout=5, isolation_level=None)
            db.execute("PRAGMA synchronous=EXTRA")
            db.execute("BEGIN IMMEDIATE")
            self._check_schema(db, initialize=True)
            yield db
            db.commit()
        except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
            raise _unavailable() from None
        finally:
            if db is not None:
                with suppress(sqlite3.Error):
                    db.rollback()
                db.close()

    def admit(self, project_key: str, request_key: str, task_ids: tuple[str, ...]) -> None:
        with self._write() as db:
            if db.execute(
                "SELECT 1 FROM relay_waves WHERE project_key=? AND request_key=?",
                (project_key, request_key),
            ).fetchone() is not None:
                raise _reject("attempt_already_reserved", "This relay wave already has a receipt.")
            if db.execute(
                "SELECT 1 FROM relay_waves WHERE project_key=? AND state IN ('admitted','incomplete')",
                (project_key,),
            ).fetchone() is not None:
                raise _reject("wave_incomplete", "An earlier relay wave still holds the project fence.")
            db.execute(
                "INSERT INTO relay_waves VALUES (?,?,'admitted',?,NULL)",
                (project_key, request_key, json.dumps(task_ids)),
            )

    def record(
        self, project_key: str, request_key: str, *, incomplete: bool, results: list[dict[str, str]],
        reconciled: bool = False,
    ) -> None:
        with self._write() as db:
            row = db.execute(
                "SELECT tasks_json,state,results_json FROM relay_waves "
                "WHERE project_key=? AND request_key=?",
                (project_key, request_key),
            ).fetchone()
            if row is None or json.loads(row[0]) != [result["task_id"] for result in results]:
                raise _reject("wave_receipt_mismatch", "The relay result does not match the admitted wave.")
            state = "incomplete" if incomplete else "resolved"
            may_reconcile = reconciled and not incomplete and row[1] == "incomplete"
            if may_reconcile:
                previous = json.loads(row[2])
                if (
                    type(previous) is not list or len(previous) != len(results)
                    or any(
                        type(old) is not dict or set(old) not in (
                            {"task_id", "state"}, {"task_id", "state", "failure_code"},
                        )
                        or old["task_id"] != new["task_id"]
                        or old["state"] not in ("incomplete", new["state"])
                        or ("failure_code" in old and old["state"] != "incomplete")
                        for old, new in zip(previous, results, strict=True)
                    )
                ):
                    raise _reject("wave_receipt_mismatch", "Reconciliation cannot replace a terminal result.")
            if row[1] != "admitted" and not may_reconcile:
                if row[1] == state and json.loads(row[2]) == results:
                    return
                raise _reject("wave_receipt_mismatch", "The relay outcome is already recorded.")
            db.execute(
                "UPDATE relay_waves SET state=?,results_json=? WHERE project_key=? AND request_key=?",
                (state, json.dumps(results), project_key, request_key),
            )

    def get(self, project_key: str, request_key: str) -> tuple[JournalState, Any, Any] | None:
        saved = self._read(project_key, request_key)
        return None if saved is None else saved[1:]

    def pending(self, project_key: str) -> tuple[str, JournalState, Any, Any] | None:
        """Read the sole active project fence, if any, without creating a journal."""
        return self._read(project_key, None)

    @contextmanager
    def _query(self) -> Iterator[sqlite3.Connection]:
        # Permit SQLite to roll back a hot journal, but never create a database
        # or change application rows from an observation.
        db = sqlite3.connect(self._path.as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            db.execute("PRAGMA query_only=ON")
            self._check_schema(db, initialize=False)
            yield db
        finally:
            db.close()

    @staticmethod
    def _decode(row: tuple[Any, ...]) -> tuple[str, JournalState, Any, Any]:
        key, state, tasks, results = row
        if (
            state not in ("admitted", "incomplete", "resolved") or len(tasks) > 8192
            or (results is not None and len(results) > 8192)
        ):
            raise _unavailable()
        return key, state, json.loads(tasks), None if results is None else json.loads(results)

    def history(
        self, project_key: str, *, limit: int, before: str | None,
    ) -> tuple[list[tuple[str, JournalState, Any, Any]], str | None]:
        if not self._check_path():
            if before is not None:
                raise AgentSyncError("not_found", "The relay history cursor was not found.", 404)
            return [], None
        try:
            with self._query() as db:
                cursor = None
                if before is not None:
                    found = db.execute(
                        "SELECT rowid FROM relay_waves WHERE project_key=? AND request_key=?",
                        (project_key, before),
                    ).fetchone()
                    if found is None:
                        raise AgentSyncError("not_found", "The relay history cursor was not found.", 404)
                    cursor = found[0]
                rows = db.execute(
                    "SELECT request_key, state, tasks_json, results_json FROM relay_waves "
                    "WHERE project_key=? AND (? IS NULL OR rowid<?) ORDER BY rowid DESC LIMIT ?",
                    (project_key, cursor, cursor, limit + 1),
                ).fetchall()
            page = rows[:limit]
            return [self._decode(row) for row in page], page[-1][0] if len(rows) > limit else None
        except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
            raise _unavailable() from None

    def _read(
        self, project_key: str, request_key: str | None
    ) -> tuple[str, JournalState, Any, Any] | None:
        if not self._check_path():
            return None
        try:
            with self._query() as db:
                if request_key is None:
                    row = db.execute(
                        "SELECT request_key,state,tasks_json,results_json FROM relay_waves "
                        "WHERE project_key=? AND state IN ('admitted','incomplete')",
                        (project_key,),
                    ).fetchone()
                else:
                    row = db.execute(
                        "SELECT request_key,state,tasks_json,results_json FROM relay_waves "
                        "WHERE project_key=? AND request_key=?",
                        (project_key, request_key),
                    ).fetchone()
            if row is None:
                return None
            return self._decode(row)
        except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
            raise _unavailable() from None

"""Private durable admission and completion for controlled relay waves."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from agentsync.errors import AgentSyncError
from agentsync.workspaces.git import physical

_APPLICATION_ID = 0x41535751
_VERSION = 1


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
        if not self._path.exists() and not self._path.is_symlink():
            return False
        physical(self._path)
        if not self._path.is_file():
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
            db.execute("PRAGMA synchronous=FULL")
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
        self, project_key: str, request_key: str, *, incomplete: bool, results: list[dict[str, str]]
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
            if row[1] != "admitted":
                if row[1] == state and json.loads(row[2]) == results:
                    return
                raise _reject("wave_receipt_mismatch", "The relay outcome is already recorded.")
            db.execute(
                "UPDATE relay_waves SET state=?,results_json=? WHERE project_key=? AND request_key=?",
                (state, json.dumps(results), project_key, request_key),
            )

    def get(self, project_key: str, request_key: str) -> tuple[str, Any, Any] | None:
        if not self._check_path():
            return None
        db = None
        try:
            db = sqlite3.connect(self._path.as_uri() + "?mode=ro", uri=True, timeout=5)
            self._check_schema(db, initialize=False)
            row = db.execute(
                "SELECT state,tasks_json,results_json FROM relay_waves "
                "WHERE project_key=? AND request_key=?",
                (project_key, request_key),
            ).fetchone()
            if row is None:
                return None
            state, tasks, results = row
            if len(tasks) > 8192 or (results is not None and len(results) > 8192):
                raise _unavailable()
            return state, json.loads(tasks), None if results is None else json.loads(results)
        except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
            raise _unavailable() from None
        finally:
            if db is not None:
                db.close()

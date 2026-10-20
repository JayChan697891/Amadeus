"""Exercise process death against an isolated on-disk database, without graceful close."""

import json
import os
import subprocess
import sys
from pathlib import Path

import agentsync


def test_abrupt_process_exit_preserves_commits_and_rolls_back_transaction(tmp_path):
    # Both interpreters run in pytest's private project and use an absolute private DB.
    # os._exit deliberately bypasses Core/SQLite cleanup and finally handlers.
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(agentsync.__file__).resolve().parents[1])
    writer = r"""
import json
import os
from pathlib import Path
import sqlite3
import sys
from agentsync.core.service import Core

root = Path(sys.argv[1])
core = Core(root / "data")
project = core.execute("create_project", {"name": "recovery", "root_path": str(root)})
actor = core.execute("register_agent", {**project, "name": "writer"})
core.execute_owner("set_agent_roles", {**project, "agent_id": actor["agent_id"],
    "roles": ["worker"], "expected_version": 1, "request_id": "explicit-owner-grant"})
auth = {"project_id": project["project_id"], "session_id": actor["session_id"],
        "session_token": actor["session_token"]}
created = core.execute("create_task", {**auth, "title": "committed", "request_id": "create"})
# Transport the disposable session credential only in captured memory, never evidence files.
print(json.dumps(auth), flush=True)
db = sqlite3.connect(root / "data" / "agentsync.db")
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE tasks SET title = ? WHERE id = ?", ("uncommitted", created["id"]))
assert db.execute("SELECT title FROM tasks WHERE id = ?", (created["id"],)).fetchone()[0] == "uncommitted"
os._exit(73)
"""
    crashed = subprocess.run(
        [sys.executable, "-c", writer, str(tmp_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert crashed.returncode == 73, crashed.stderr
    reader = r"""
import json
from pathlib import Path
import sqlite3
import sys
from agentsync.core.service import Core

root = Path(sys.argv[1])
auth = json.loads(sys.stdin.read())
core = Core(root / "data")
tasks = core.execute("list_tasks", auth)["tasks"]
replayed = core.execute("create_task", {**auth, "title": "committed", "request_id": "create"})
with sqlite3.connect(root / "data" / "agentsync.db") as db:
    integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
print(json.dumps({"titles": [item["title"] for item in tasks],
                  "same_id": len(tasks) == 1 and replayed["id"] == tasks[0]["id"],
                  "count_after_replay": len(core.execute("list_tasks", auth)["tasks"]),
                  "integrity": integrity, "foreign_keys": foreign_keys}))
"""
    restarted = subprocess.run(
        [sys.executable, "-c", reader, str(tmp_path)],
        input=crashed.stdout,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert json.loads(restarted.stdout) == {
        "titles": ["committed"],
        "same_id": True,
        "count_after_replay": 1,
        "integrity": "ok",
        "foreign_keys": [],
    }

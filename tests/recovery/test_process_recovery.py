"""Exercise process death against an isolated on-disk database, without graceful close."""

import json
import os
import subprocess
import sys
import time
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


def test_crashed_running_owner_is_reclaimed_and_dependency_resumes_after_restart(tmp_path):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(agentsync.__file__).resolve().parents[1])
    producer = r"""
import json
import os
from pathlib import Path
import sys
from agentsync.core.service import Core

root = Path(sys.argv[1])
core = Core(root / "data")
project = core.execute("create_project", {"name": "lease-recovery", "root_path": str(root)})
actors = {}
for name, roles in (("crashed", ["worker"]), ("successor", ["worker"]),
                    ("reviewer", ["reviewer"])):
    actor = core.execute("register_agent", {**project, "name": name})
    core.execute_owner("set_agent_roles", {**project, "agent_id": actor["agent_id"],
        "roles": roles, "expected_version": 1, "request_id": "grant-" + name})
    actors[name] = {"project_id": project["project_id"], "session_id": actor["session_id"],
                    "session_token": actor["session_token"]}
auth = actors["crashed"]
task = core.execute("create_task", {**auth, "title": "root", "request_id": "root"})
dependent = core.execute("create_task", {**auth, "title": "dependent",
    "dependencies": [task["id"]], "request_id": "dependent"})
claim_request = {**auth, "task_id": task["id"], "expected_version": task["version"],
                 "lease_seconds": 1, "request_id": "crashed-claim"}
leased = core.execute("claim_task", claim_request)
running = core.execute("update_task", {**auth, "task_id": task["id"],
    "expected_version": leased["version"], "lease_token": leased["lease_token"],
    "status": "running", "request_id": "crashed-running"})
assert running["status"] == "running"
# Disposable credentials pass only through captured memory and the next process's stdin.
print(json.dumps({"actors": actors, "claim_request": claim_request,
    "lease_token": leased["lease_token"], "running": running, "dependent": dependent}),
    flush=True)
os._exit(73)
"""
    crashed = subprocess.run(
        [sys.executable, "-c", producer, str(tmp_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert crashed.returncode == 73, crashed.stderr
    handoff = json.loads(crashed.stdout)
    # Wait for the actual persisted lease deadline; do not patch clocks or update SQLite.
    expiry = handoff["running"]["lease_expires_at"]
    time.sleep(max(0, min(2, expiry - time.time() + 0.05)))
    assert time.time() > expiry
    recovery = r"""
import json
from pathlib import Path
import sys
import time
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError

handoff = json.loads(sys.stdin.read())
core = Core(Path(sys.argv[1]) / "data")
old, worker, reviewer = (handoff["actors"][name] for name in
                          ("crashed", "successor", "reviewer"))
running, dependent = handoff["running"], handoff["dependent"]
assert time.time() > running["lease_expires_at"]

def task(task_id):
    return next(item for item in core.execute("list_tasks", worker)["tasks"]
                if item["id"] == task_id)

def rejected(operation, payload, expected):
    try:
        core.execute(operation, payload)
    except AgentSyncError as exc:
        assert exc.code == expected, (operation, exc.code)
    else:
        raise AssertionError(operation + " unexpectedly succeeded")

assert task(running["id"]) == running
rejected("claim_task", handoff["claim_request"], "lease_expired")
rejected("claim_task", {**worker, "task_id": dependent["id"],
    "expected_version": dependent["version"], "request_id": "dependent-too-early"},
    "dependencies_incomplete")
assert core.execute("reclaim_expired", worker)["reclaimed_task_ids"] == [running["id"]]
pending = task(running["id"])
assert pending["status"] == "pending"
assert pending["version"] == running["version"] + 1
assert pending["owner_session_id"] is None and pending["lease_expires_at"] is None
assert core.execute("reclaim_expired", worker)["reclaimed_task_ids"] == []
assert task(running["id"]) == pending
rejected("update_task", {**old, "task_id": running["id"],
    "expected_version": pending["version"], "lease_token": handoff["lease_token"],
    "status": "running", "request_id": "stale-owner"}, "lease_denied")
rejected("claim_task", handoff["claim_request"], "lease_denied")
assert task(running["id"]) == pending
leased = core.execute("claim_task", {**worker, "task_id": pending["id"],
    "expected_version": pending["version"], "lease_seconds": 60,
    "request_id": "successor-claim"})
assert leased["status"] == "claimed" and leased["version"] == pending["version"] + 1
assert leased["owner_session_id"] == worker["session_id"]
assert leased["lease_token"] != handoff["lease_token"]
rejected("update_task", {**old, "task_id": leased["id"],
    "expected_version": leased["version"], "lease_token": handoff["lease_token"],
    "status": "running", "request_id": "stale-after-successor"}, "lease_denied")
rejected("claim_task", handoff["claim_request"], "lease_denied")
current = leased
for status in ("running", "review"):
    previous_version = current["version"]
    current = core.execute("update_task", {**worker, "task_id": current["id"],
        "expected_version": previous_version, "lease_token": leased["lease_token"],
        "status": status, "result": "recovered work", "request_id": "successor-" + status})
    assert current["status"] == status and current["version"] == previous_version + 1
assert current["lease_expires_at"] is None
review = {"task_id": current["id"], "expected_version": current["version"],
          "accept": True, "evidence": "Inspected recovered work.", "request_id": "accept"}
completed = core.execute("review_task", {**reviewer, **review})
assert completed["status"] == "completed"
assert completed["version"] == current["version"] + 1
assert completed["latest_review"]["reviewer_session_id"] == reviewer["session_id"]
assert reviewer["session_id"] != worker["session_id"]
assert completed["latest_review"]["accept"] is True
eligible = core.execute("claim_task", {**worker, "task_id": dependent["id"],
    "expected_version": dependent["version"], "lease_seconds": 60,
    "request_id": "eligible-dependent"})
assert eligible["status"] == "claimed" and eligible["dependencies"] == [completed["id"]]
assert eligible["version"] == dependent["version"] + 1
# Only public snapshots leave this process; successor lease credentials stay local.
print(json.dumps({"tasks": core.execute("list_tasks", worker)["tasks"]}))
"""
    recovered = subprocess.run(
        [sys.executable, "-c", recovery, str(tmp_path)],
        input=crashed.stdout,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert recovered.returncode == 0, recovered.stderr
    persisted = json.loads(recovered.stdout)
    reader = r"""
import json
from pathlib import Path
import sqlite3
import sys
from agentsync.core.service import Core

handoff = json.loads(sys.stdin.read())
core = Core(Path(sys.argv[1]) / "data")
tasks = core.execute("list_tasks", handoff["auth"])["tasks"]
assert tasks == handoff["expected"]["tasks"]
assert sorted(task["status"] for task in tasks) == ["claimed", "completed"]
with sqlite3.connect(core.db_path) as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 1
print(json.dumps({"persisted": True, "task_count": len(tasks), "review_count": 1}))
"""
    restarted = subprocess.run(
        [sys.executable, "-c", reader, str(tmp_path)],
        input=json.dumps({"auth": handoff["actors"]["successor"], "expected": persisted}),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    assert json.loads(restarted.stdout) == {
        "persisted": True,
        "task_count": 2,
        "review_count": 1,
    }

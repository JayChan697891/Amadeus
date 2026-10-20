"""Actual owner subprocesses race SQLite approval state; no Agent inference."""

import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from agentsync.core.service import Core

CHILD = """
import json, pathlib, sys, time
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
p = json.loads(sys.stdin.readline())
core = Core(p['data'])
print('ready', flush=True)
deadline = time.monotonic() + 15
while not pathlib.Path(p['gate']).exists():
    if time.monotonic() > deadline:
        raise RuntimeError('Fixture gate deadline exceeded')
    time.sleep(.01)
try:
    result = core.execute_owner('decide_approval', p['payload'])
    print(json.dumps({'status': result['status']}), flush=True)
except AgentSyncError as error:
    print(json.dumps({'code': error.code}), flush=True)
"""


def test_two_owner_processes_cannot_both_decide_same_approval(tmp_path):
    root = tmp_path / "isolated-project"
    root.mkdir()
    data = tmp_path / "state"
    core = Core(data)
    project = core.execute("create_project", {"name": "process race", "root_path": str(root)})
    agent = core.execute("register_agent", {**project, "name": "worker"})
    core.execute_owner(
        "set_agent_roles",
        {
            **project,
            "agent_id": agent["agent_id"],
            "roles": ["worker"],
            "expected_version": 1,
            "request_id": "grant",
        },
    )
    auth = {
        "project_id": project["project_id"],
        "session_id": agent["session_id"],
        "session_token": agent["session_token"],
    }
    task = core.execute("create_task", {**auth, "title": "metadata fixture", "request_id": "task"})
    receipt = {
        "candidate_id": "candidate",
        "candidate_sha": "c" * 40,
        "base_sha": "a" * 40,
        "left_sha": "b" * 40,
        "right_sha": "d" * 40,
        "changed_paths": ["file.txt"],
        "status": "awaiting_human_approval",
    }
    with sqlite3.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
            ("snapshot", project["project_id"], agent["session_id"], time.time(), "{}"),
        )
        for tree in ("left", "right"):
            db.execute(
                "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
                (
                    tree,
                    project["project_id"],
                    "snapshot",
                    task["id"],
                    agent["session_id"],
                    time.time(),
                    "{}",
                ),
            )
        db.execute(
            "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
            (
                "candidate",
                project["project_id"],
                "left",
                "right",
                agent["session_id"],
                time.time(),
                json.dumps(receipt),
            ),
        )
    pending = core.execute(
        "request_approval",
        {
            **auth,
            "action": "apply_merge_candidate",
            "subject_id": "candidate",
            "subject_sha": receipt["candidate_sha"],
            "reason": "metadata race only",
            "request_id": "request",
        },
    )
    gate = tmp_path / "start-gate"
    processes = []
    try:
        for accept in (True, False):
            process = subprocess.Popen(
                [sys.executable, "-c", CHILD],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env={**os.environ, "TMP": str(tmp_path), "TEMP": str(tmp_path)},
            )
            processes.append(process)
            config = {
                "data": str(data),
                "gate": str(gate),
                "payload": {
                    **project,
                    "approval_id": pending["id"],
                    "expected_version": pending["version"],
                    "accept": accept,
                    "request_id": "decision-" + str(accept),
                },
            }
            assert process.stdin is not None
            process.stdin.write(json.dumps(config) + "\n")
            process.stdin.flush()
        # Child gate has its own finite deadline; readiness never depends on inference.
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(process.stdout.readline) for process in processes]
            assert [future.result(timeout=20).strip() for future in futures] == ["ready", "ready"]
        gate.touch()
        outcomes = []
        for process in processes:
            output, errors = process.communicate(timeout=20)
            assert process.returncode == 0, errors
            for secret in (project["admin_token"], agent["session_token"]):
                assert secret not in output + errors
            outcomes.append(json.loads(output))
        assert sum(item.get("status") in {"approved", "denied"} for item in outcomes) == 1
        assert (
            sum(item.get("code") in {"version_conflict", "approval_state"} for item in outcomes)
            == 1
        )
        current = core.execute("get_approval", {**auth, "approval_id": pending["id"]})
        assert current["version"] == pending["version"] + 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)

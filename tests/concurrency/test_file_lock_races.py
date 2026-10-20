"""Independent Python processes contend for one SQLite-backed resource lock."""

import json
import subprocess
import sys

from conftest import owner_grant

from agentsync.core.service import Core

WORKER = r"""
import json
import sys
import time
from pathlib import Path
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError

payload = json.loads(sys.stdin.readline())
core = Core(payload.pop("data_dir"))
gate = Path(payload.pop("gate"))
print("READY", flush=True)
deadline = time.monotonic() + 15
while not gate.exists():
    if time.monotonic() > deadline:
        raise RuntimeError("Race start gate timed out")
    time.sleep(0.01)
try:
    result = core.execute("acquire_file_lock", payload)
    print(json.dumps({"ok": True, "id": result["id"]}), flush=True)
except AgentSyncError as exc:
    print(json.dumps({"ok": False, "code": exc.code}), flush=True)
"""


def test_two_independent_processes_have_exactly_one_lock_winner(tmp_path):
    root = tmp_path / "resources"
    root.mkdir()
    core = Core(tmp_path / "db")
    project = core.execute("create_project", {"name": "race", "root_path": str(root)})
    gate = tmp_path / "gate"
    processes = []
    auths = []
    try:
        for index in range(2):
            actor = core.execute("register_agent", {**project, "name": f"worker-{index}"})
            owner_grant(core, project, actor)
            auth = {key: actor[key] for key in ("session_id", "session_token")}
            auth["project_id"] = project["project_id"]
            auths.append(auth)
            process = subprocess.Popen(
                [sys.executable, "-c", WORKER],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
            process.stdin.write(
                json.dumps(
                    {
                        **auth,
                        "path": "shared.txt",
                        "request_id": f"acquire-{index}",
                        "data_dir": str(core.data_dir),
                        "gate": str(gate),
                    }
                )
                + "\n"
            )
            process.stdin.flush()
        for process in processes:
            assert process.stdout.readline().strip() == "READY"
        gate.touch()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=25)
            assert process.returncode == 0, stderr
            results.append(json.loads(stdout.strip()))
        assert sum(result["ok"] for result in results) == 1
        assert sum(not result["ok"] for result in results) == 1
        winner = next(result for result in results if result["ok"])
        listed = Core(core.data_dir).execute("list_file_locks", auths[0])["locks"]
        assert len(listed) == 1 and listed[0]["id"] == winner["id"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

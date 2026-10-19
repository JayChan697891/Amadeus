"""Real, inference-free Codex app-server collaboration probe.

Run with the project's Python environment. Two ephemeral native host threads use
one isolated absolute database. This does not exercise the desktop UI. No global
client configuration is changed. Reports never contain raw IDs or credentials.
"""

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from agentsync.core.service import Core

ROOT = Path(__file__).resolve().parents[2]
RESULT = "Native host A submitted the deterministic M2 collaboration fixture."
EVIDENCE = "Native host B read the exact submitted result and accepted version 4."
EXPECTED_STATES = [
    ("created", "pending", 1),
    ("claimed", "claimed", 2),
    ("running", "running", 3),
    ("submitted", "review", 4),
    ("accepted", "completed", 5),
    ("after_host_restart", "completed", 5),
    ("fresh_core", "completed", 5),
]


def validate_report(report):
    """Validate evidence contents, never interpret fabricated fixtures as live proof."""
    assert report["desktop_ui_tested"] is False
    assert report["inference_turns"] == 0
    assert report["host_threads"] == 2
    assert report["runtime_statuses"] == ["connected", "connected", "connected"]
    states = report["task_observations"]
    assert [(s["stage"], s["status"], s["version"]) for s in states] == EXPECTED_STATES
    assert report["duplicate_claim"] == {
        "ok": False,
        "code": "invalid_transition",
        "observed_version": 2,
    }
    expected_hash = hashlib.sha256(RESULT.encode()).hexdigest()
    for state in states[3:]:
        assert state["result_sha256"] == expected_hash
        assert state["owner"] == "A"
    for state in states[4:]:
        assert state["review"] == {
            "reviewer": "B",
            "accept": True,
            "evidence": EVIDENCE,
            "version": 5,
        }


class NativeHost:
    """Bounded public JSON-RPC host, with notifications kept out of the report."""

    def __init__(self, binary, data, log, *, use_registered_config=False):
        self.data = data
        self.use_registered_config = use_registered_config
        self.messages = queue.Queue()
        self.counter = 0
        self.errors = log.open("w", encoding="utf-8")
        argv = [str(binary), "app-server"]
        if not use_registered_config:
            if data is None:
                raise ValueError("Isolated host requires an explicit data directory.")
            config = "mcp_servers={agentsync={command=" + json.dumps(sys.executable)
            config += ",args=" + json.dumps(["-m", "agentsync", "--data-dir", str(data), "mcp"])
            config += "}}"
            argv.extend(["-c", config])
        self.proc = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                self.messages.put(json.loads(line))
            except ValueError:
                continue
        self.messages.put({"eof": True})

    def send(self, method, params=None, notification=False):
        self.counter += 1
        message = {"method": method, "params": params or {}}
        if not notification:
            message["id"] = self.counter
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notification:
            return None
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                reply = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if reply.get("eof"):
                raise RuntimeError("Native host closed its output before replying.")
            if reply.get("id") == self.counter:
                if "error" in reply:
                    # Raw host errors can contain local paths; leave them private.
                    raise RuntimeError(f"Native host rejected {method}.")
                return reply["result"]
        raise TimeoutError(f"Native host timed out: {method}")

    def initialize(self):
        init = self.send(
            "initialize",
            {
                "clientInfo": {"name": "agentsync-collaboration-acceptance", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send("initialized", notification=True)
        return init

    def start(self):
        params = {
            "cwd": str(ROOT),
            "ephemeral": True,
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }
        if not self.use_registered_config:
            params["config"] = {
                "mcp_servers": {
                    "agentsync": {
                        "command": sys.executable,
                        "args": ["-m", "agentsync", "--data-dir", str(self.data), "mcp"],
                    }
                }
            }
        thread = self.send("thread/start", params)
        tid = thread["thread"]["id"]
        status = self.send(
            "mcpServerStatus/list",
            {
                "threadId": tid,
                "serverName": "agentsync",
                "detail": "toolsAndAuthOnly",
            },
        )
        inventory = next(s for s in status["data"] if s["name"] == "agentsync")
        assert inventory["runtimeStatus"] == "connected"
        assert inventory["toolsError"] is None
        return tid, inventory["runtimeStatus"], sorted(inventory["tools"])

    def call(self, tid, operation, arguments, expect_ok=True):
        result = self.send(
            "mcpServer/tool/call",
            {
                "threadId": tid,
                "server": "agentsync",
                "tool": operation,
                "arguments": arguments,
            },
        )
        assert not result.get("isError", False), "MCP transport/tool failure"
        envelope = result["structuredContent"]
        assert envelope["ok"] is expect_ok, f"Unexpected operation outcome: {operation}"
        return envelope["data"] if expect_ok else envelope["error"]

    def close(self):
        if self.proc.stdin:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.errors.close()


def run(binary):
    (ROOT / "work").mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="codex-collaboration-", dir=ROOT / "work"))
    data = workspace / "data"
    observations = []
    sessions = {}

    def observe(stage, task):
        assert "lease_token" not in task
        item = {
            "stage": stage,
            "status": task["status"],
            "version": task["version"],
            "owner": next(
                (
                    name
                    for name, s in sessions.items()
                    if s["session_id"] == task["owner_session_id"]
                ),
                None,
            ),
            "result_sha256": hashlib.sha256(task["result"].encode()).hexdigest(),
            "review": None,
        }
        review = task["latest_review"]
        if review:
            assert review["reviewer_session_id"] == sessions["B"]["session_id"]
            assert review["reviewer_agent_id"] == sessions["B"]["agent_id"]
            item["review"] = {
                "reviewer": "B",
                "accept": review["accept"],
                "evidence": review["evidence"],
                "version": review["version"],
            }
        observations.append(item)

    host = NativeHost(binary, data, workspace / "host-stderr.log")
    try:
        init = host.initialize()
        ta, status_a, tools_a = host.start()
        tb, status_b, tools_b = host.start()
        assert ta != tb
        assert tools_a == tools_b
        project = host.call(
            ta,
            "create_project",
            {"name": "Native collaboration acceptance", "root_path": str(workspace)},
        )
        for name, tid in (("A", ta), ("B", tb)):
            sessions[name] = host.call(
                tid,
                "register_agent",
                {**project, "name": f"Native acceptance agent {name}", "capabilities": []},
            )
        assert sessions["A"]["agent_id"] != sessions["B"]["agent_id"]
        assert sessions["A"]["session_id"] != sessions["B"]["session_id"]
        auth = {
            name: {
                "project_id": project["project_id"],
                "session_id": session["session_id"],
                "session_token": session["session_token"],
            }
            for name, session in sessions.items()
        }
        task = host.call(
            ta,
            "create_task",
            {
                **auth["A"],
                "title": "Deterministic two-session M2 fixture",
                "request_id": "create-1",
                "dependencies": [],
            },
        )
        observe("created", task)
        claimed = host.call(
            ta,
            "claim_task",
            {
                **auth["A"],
                "task_id": task["id"],
                "expected_version": task["version"],
                "request_id": "claim-a-1",
            },
        )
        lease = claimed.pop("lease_token")
        observe("claimed", claimed)
        visible = host.call(tb, "list_tasks", auth["B"])["tasks"]
        assert len(visible) == 1 and visible[0] == claimed
        duplicate = host.call(
            tb,
            "claim_task",
            {
                **auth["B"],
                "task_id": task["id"],
                "expected_version": visible[0]["version"],
                "request_id": "claim-b-1",
            },
            False,
        )
        assert duplicate["code"] == "invalid_transition"
        unchanged = host.call(tb, "list_tasks", auth["B"])["tasks"]
        assert unchanged == visible
        current = claimed
        for stage, status, result in (("running", "running", ""), ("submitted", "review", RESULT)):
            current = host.call(
                ta,
                "update_task",
                {
                    **auth["A"],
                    "task_id": task["id"],
                    "lease_token": lease,
                    "expected_version": current["version"],
                    "status": status,
                    "result": result,
                    "request_id": stage + "-1",
                },
            )
            observe(stage, current)
        submitted = host.call(tb, "list_tasks", auth["B"])["tasks"][0]
        assert submitted == current and submitted["result"] == RESULT
        accepted = host.call(
            tb,
            "review_task",
            {
                **auth["B"],
                "task_id": task["id"],
                "expected_version": submitted["version"],
                "accept": True,
                "evidence": EVIDENCE,
                "request_id": "review-b-1",
            },
        )
        observe("accepted", accepted)
    finally:
        host.close()

    # A new native host and MCP subprocess must read the persisted exact task.
    restarted = NativeHost(binary, data, workspace / "restarted-stderr.log")
    try:
        restarted.initialize()
        tr, status_r, tools_r = restarted.start()
        assert tools_r == tools_a
        persisted = restarted.call(tr, "list_tasks", auth["B"])["tasks"]
        assert persisted == [accepted]
        observe("after_host_restart", persisted[0])
    finally:
        restarted.close()
    fresh = Core(data).execute("list_tasks", auth["B"])["tasks"]
    assert fresh == [accepted]
    observe("fresh_core", fresh[0])
    report = {
        "host": "installed Codex public app-server",
        "inference_turns": 0,
        "ephemeral": True,
        "host_threads": 2,
        "runtime_statuses": [status_a, status_b, status_r],
        "tools": tools_a,
        "client": init["userAgent"],
        "desktop_ui_tested": False,
        "global_configuration_modified": False,
        "limitations": "Native isolated backend only; no desktop UI or model development session. Review evidence is an Alpha assertion, not M5 verification.",
        "duplicate_claim": {"ok": False, "code": duplicate["code"], "observed_version": 2},
        "task_observations": observations,
    }
    validate_report(report)
    # Only safe summary fields are serialized. Raw tokens remain in memory only.
    output = ROOT / "docs/codex-collaboration-probe.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path)
    args = parser.parse_args()
    binary = args.codex_binary
    if binary is None:
        binary = Path(os.environ["APPDATA"]) / (
            "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/"
            "vendor/x86_64-pc-windows-msvc/bin/codex.exe"
        )
        if not binary.is_file():
            found = shutil.which("codex.exe")
            if found:
                binary = Path(found)
    if not binary.is_file():
        raise SystemExit("Codex native binary unavailable; pass --codex-binary.")
    run(binary)


if __name__ == "__main__":
    main()

"""One-off public Codex app-server MCP probe; never starts an inference turn."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
binary = (
    Path(os.environ["APPDATA"])
    / "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
)
data = root / "work/codex-mcp-data"
config = (
    "mcp_servers={agentsync={command="
    + json.dumps(sys.executable)
    + ",args="
    + json.dumps(["-m", "agentsync", "--data-dir", str(data), "mcp"])
    + "}}"
)
errors = (root / "work/codex-probe-stderr.log").open("w", encoding="utf-8")
proc = subprocess.Popen(
    [str(binary), "app-server", "-c", config],
    cwd=root,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=errors,
    text=True,
    encoding="utf-8",
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
messages = queue.Queue()


def read():
    for line in proc.stdout:
        try:
            messages.put(json.loads(line))
        except ValueError:
            pass


threading.Thread(target=read, daemon=True).start()
counter = 0


def send(method, params=None, notification=False):
    global counter
    counter += 1
    msg = {"method": method, "params": params or {}}
    if not notification:
        msg["id"] = counter
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notification:
        return None
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        reply = messages.get(timeout=max(0.01, deadline - time.monotonic()))
        if reply.get("id") == counter:
            if "error" in reply:
                raise RuntimeError(json.dumps(reply["error"]))
            return reply["result"]
    raise TimeoutError(method)


try:
    init = send(
        "initialize",
        {
            "clientInfo": {"name": "agentsync-acceptance", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True},
        },
    )
    send("initialized", notification=True)
    thread = send(
        "thread/start",
        {
            "cwd": str(root),
            "ephemeral": True,
            "approvalPolicy": "never",
            "sandbox": "read-only",
            "config": {
                "mcp_servers": {
                    "agentsync": {
                        "command": sys.executable,
                        "args": ["-m", "agentsync", "--data-dir", str(data), "mcp"],
                    }
                }
            },
        },
    )
    tid = thread["thread"]["id"]
    status = send(
        "mcpServerStatus/list",
        {"threadId": tid, "serverName": "agentsync", "detail": "toolsAndAuthOnly"},
    )

    def call(tool, arguments):
        result = send(
            "mcpServer/tool/call",
            {"threadId": tid, "server": "agentsync", "tool": tool, "arguments": arguments},
        )
        assert not result.get("isError", False), result
        envelope = result["structuredContent"]
        assert envelope["ok"], envelope
        return envelope["data"]

    project = call(
        "create_project", {"name": "Codex native MCP acceptance", "root_path": str(root)}
    )
    session = call("register_agent", {**project, "name": "Codex native MCP agent"})
    auth = {
        "project_id": project["project_id"],
        "session_id": session["session_id"],
        "session_token": session["session_token"],
    }
    task = call(
        "create_task", {**auth, "title": "Host integration evidence", "request_id": "host-task-1"}
    )
    visible = call("list_tasks", auth)
    assert task["id"] in [t["id"] for t in visible["tasks"]]
    # Credentials deliberately omitted from saved evidence.
    inventory = status["data"][0]
    report = {
        "host": "installed Codex public app-server",
        "inference_turns": 0,
        "ephemeral": True,
        "runtime_status": inventory["runtimeStatus"],
        "tools": sorted(inventory["tools"]),
        "tools_error": inventory["toolsError"],
        "verified_calls": ["create_project", "register_agent", "create_task", "list_tasks"],
        "roundtrip_verified": True,
        "client": init["userAgent"],
        "desktop_ui_tested": False,
    }
    (root / "docs/codex-host-probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
finally:
    proc.stdin.close()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)
    errors.close()

"""Real, inference-free Codex app-server collaboration probe.

Run with the installed a118 Python environment. Two ephemeral native host threads
share one disposable fixture on D:. App-server configuration and reports stay in
that fixture. The tool calls are deterministic; there are no inference requests.
"""

import argparse
import ctypes
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
import traceback
from ctypes import wintypes
from importlib import metadata
from pathlib import Path

import agentsync
from agentsync.core.service import Core
from agentsync.models import OPERATIONS

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path("D:/agentsync-debug")
VERSION = "0.3.0a118"
MCP_ENTRY = """
import os
import sys
from pathlib import Path
Path(sys.argv[1], str(os.getpid())).touch(exist_ok=False)
from agentsync.cli import main
raise SystemExit(main(sys.argv[2:]))
"""
METHODS = frozenset(
    {"initialize", "initialized", "thread/start", "mcpServerStatus/list", "mcpServer/tool/call"}
)
MCP_CONNECTION_STATES = (
    "notStarted",
    "starting",
    "connected",
    "authenticationRequired",
    "failed",
    "cancelled",
    "disabled",
)
MCP_AUTH_STATES = ("unsupported", "notLoggedIn", "bearerToken", "oAuth")
MCP_STATUS_TIMEOUT = 10
MCP_STATUS_INTERVAL = 0.25
CONTEXT = "Read the exact pinned context before accepting the deterministic task as text."
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


class NativeHostBlocked(RuntimeError):
    """A bounded diagnostic without raw app-server responses."""

    def __init__(self, method, reason, rpc_code=None):
        super().__init__(f"{method}: {reason}")
        self.method, self.reason, self.rpc_code = method, reason, rpc_code


class NativeHost:
    """Bounded public JSON-RPC host, with notifications kept out of the report."""

    def __init__(self, binary, data, log, *, use_registered_config=False):
        self.data = data
        self.use_registered_config = use_registered_config
        self.messages = queue.Queue()
        self.counter = 0
        self.unexpected_turn = False
        self.close_mode = "stdin_eof"
        argv = [str(binary), "app-server"]
        cwd, env = ROOT, None
        if not use_registered_config:
            if data is None:
                raise ValueError("Isolated host requires an explicit data directory.")
            cwd = data.parent
            home = cwd / (log.stem + "-home")
            home.mkdir()
            self.mcp_pids = cwd / (log.stem + "-mcp")
            self.mcp_pids.mkdir()
            env = {
                name: os.environ[name]
                for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT")
                if name in os.environ
            }
            env.update(
                {
                    name: str(home)
                    for name in (
                        "CODEX_HOME",
                        "HOME",
                        "USERPROFILE",
                        "APPDATA",
                        "LOCALAPPDATA",
                        "TEMP",
                        "TMP",
                    )
                }
            )
            env.update(
                GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0"
            )
            self.mcp_args = [
                "-I",
                "-B",
                "-c",
                MCP_ENTRY,
                str(self.mcp_pids),
                "--data-dir",
                str(data),
                "mcp",
            ]
            config = "mcp_servers={agentsync={command=" + json.dumps(sys.executable)
            config += ",args=" + json.dumps(self.mcp_args) + "}}"
            argv.extend(
                [
                    "-c",
                    config,
                    "-c",
                    'cli_auth_credentials_store="file"',
                    "-c",
                    'mcp_oauth_credentials_store="file"',
                    "-c",
                    "features.apps=false",
                ]
            )
        self.errors = log.open("w" if use_registered_config else "x", encoding="utf-8")
        try:
            self.proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self.errors,
                text=True,
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            self.errors.close()
            raise
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
                if isinstance(message, dict):
                    if str(message.get("method", "")).startswith("turn/"):
                        self.unexpected_turn = True
                    self.messages.put(message)
            except ValueError:
                continue
        self.messages.put({"eof": True})

    def send(self, method, params=None, notification=False, *, timeout=45):
        if method not in METHODS:
            raise ValueError("RPC method is outside the inference-free probe.")
        self.counter += 1
        message = {"method": method, "params": params or {}}
        if not notification:
            message["id"] = self.counter
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if notification:
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                reply = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if self.unexpected_turn:
                raise NativeHostBlocked(method, "unexpected_turn_notification")
            if reply.get("eof"):
                raise NativeHostBlocked(method, "host_output_closed")
            if "method" in reply and "id" in reply:
                raise NativeHostBlocked(method, "unexpected_server_request")
            if reply.get("id") == self.counter:
                if "error" in reply:
                    code = reply["error"].get("code")
                    reason = "method_not_found" if code == -32601 else "rpc_rejected"
                    raise NativeHostBlocked(method, reason, code if type(code) is int else None)
                return reply["result"]
        raise NativeHostBlocked(method, "rpc_timeout")

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

    def start(self, status_checks=None):
        params = {
            "cwd": str(ROOT if self.use_registered_config else self.data.parent),
            "ephemeral": True,
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }
        if not self.use_registered_config:
            params["config"] = {
                "mcp_servers": {
                    "agentsync": {
                        "command": sys.executable,
                        "args": self.mcp_args,
                    }
                }
            }
        thread = self.send("thread/start", params)
        tid = thread["thread"]["id"]
        request = {"threadId": tid, "detail": "toolsAndAuthOnly"}
        if self.use_registered_config:
            request["serverName"] = "agentsync"
        method = "mcpServerStatus/list"
        deadline = time.monotonic() + MCP_STATUS_TIMEOUT
        while (remaining := deadline - time.monotonic()) > 0:
            status = self.send(method, request, timeout=remaining)
            rows = status.get("data") if isinstance(status, dict) else None
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise NativeHostBlocked(method, "invalid_status_response")
            matching = [row for row in rows if row.get("name") == "agentsync"]
            if not matching:
                raise NativeHostBlocked(method, "local_mcp_missing")
            if len(matching) != 1 or (not self.use_registered_config and len(rows) != 1):
                raise NativeHostBlocked(method, "unexpected_mcp_servers")

            inventory = matching[0]
            runtime = inventory.get("runtimeStatus")
            auth = inventory.get("authStatus")
            tools_error = inventory.get("toolsError") is not None
            tools = inventory.get("tools")
            if status_checks is not None:
                status_checks.append(
                    {
                        "runtime_status": runtime
                        if runtime in MCP_CONNECTION_STATES
                        else ("unavailable" if runtime is None else "unknown"),
                        "auth_status": auth if auth in MCP_AUTH_STATES else "unknown",
                        "tools_error_present": tools_error,
                        "tool_count": len(tools) if isinstance(tools, dict) else None,
                    }
                )
            if tools_error:
                raise NativeHostBlocked(method, "tool_discovery_error")
            if runtime == "connected":
                if not isinstance(tools, dict):
                    raise NativeHostBlocked(method, "invalid_tool_catalog")
                return tid, runtime, sorted(tools)
            if runtime != "starting":
                reason = (
                    "mcp_not_connected"
                    if runtime in MCP_CONNECTION_STATES
                    else "mcp_status_unavailable"
                )
                raise NativeHostBlocked(method, reason)
            time.sleep(max(0, min(MCP_STATUS_INTERVAL, deadline - time.monotonic())))
        raise NativeHostBlocked(method, "mcp_startup_timeout")

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
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.close_mode = "terminated"
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.close_mode = "killed"
                self.proc.kill()
                self.proc.wait(timeout=5)
        finally:
            self.errors.close()
        if not self.use_registered_config:
            self.mcp_children_ended = wait_mcp_children(self.mcp_pids)


def wait_mcp_children(markers):
    """Observe exact fixture-marked children without signaling any process."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    children = list(markers.iterdir())
    deadline = time.monotonic() + 10
    for marker in children:
        handle = kernel.OpenProcess(0x00100000, False, int(marker.name))  # SYNCHRONIZE
        if not handle:
            if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: PID already absent
                continue
            raise NativeHostBlocked("host_shutdown", "mcp_child_status_unavailable")
        try:
            budget = max(0, round((deadline - time.monotonic()) * 1000))
            if kernel.WaitForSingleObject(handle, budget) != 0:  # WAIT_OBJECT_0
                raise NativeHostBlocked("host_shutdown", "mcp_child_exit_unconfirmed")
        finally:
            kernel.CloseHandle(handle)
    return len(children)


def run_collaboration(binary, workspace, report):
    data = workspace / "data"
    observations = report["task_observations"] = []
    stages = report["completed_stages"] = []
    status_checks = report["mcp_status_checks"] = {}
    sessions = {}

    def observe(stage, task):
        assert "lease_token" not in task
        assert task["task_verification"] == "unverified" and task["verification"] is None
        item = {
            "task_verification": task["task_verification"],
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

    host = NativeHost(binary, data, workspace / "host-stderr.private.log")
    try:
        init = host.initialize()
        ta, status_a, tools_a = host.start(status_checks.setdefault("thread_a", []))
        stages.append("thread_a_connected")
        tb, status_b, tools_b = host.start(status_checks.setdefault("thread_b", []))
        stages.append("thread_b_connected")
        assert ta != tb
        assert tools_a == tools_b == sorted(OPERATIONS.keys() - {"inspect_owned_worktree"})
        stages.append("public_tool_catalog_verified")
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
        core = Core(data)
        members = core.execute_owner("list_members", {**project, "limit": 2, "offset": 0})[
            "members"
        ]
        assert len(members) == 2 and all(member["roles"] == ["viewer"] for member in members)
        roles = {"A": ["worker"], "B": ["worker", "reviewer"]}
        for name, grant in roles.items():
            member = next(row for row in members if row["agent_id"] == sessions[name]["agent_id"])
            updated = core.execute_owner(
                "set_agent_roles",
                {
                    **project,
                    "agent_id": member["agent_id"],
                    "roles": grant,
                    "expected_version": member["version"],
                    "request_id": "native-probe-role-" + name,
                },
            )
            assert set(updated["roles"]) == set(grant)
        report["owner_granted_roles"] = roles
        stages.append("distinct_identities_authorized")
        context = host.call(
            ta,
            "publish_context",
            {
                **auth["A"],
                "kind": "requirement",
                "title": "Deterministic review input",
                "content": CONTEXT,
                "request_id": "native-probe-context",
            },
        )
        assert context["author_agent_id"] == sessions["A"]["agent_id"]
        assert context["author_session_id"] == sessions["A"]["session_id"]
        assert context["version"] == 1 and context["content"] == CONTEXT
        context_pin = {**auth["B"], "context_id": context["id"], "version": context["version"]}
        assert host.call(tb, "get_context", context_pin) == context
        report["context"] = {
            "publisher": "A",
            "reader": "B",
            "version": context["version"],
            "content_sha256": hashlib.sha256(context["content"].encode()).hexdigest(),
            "read_after_host_restart": False,
            "read_from_fresh_core": False,
        }
        stages.append("context_published_and_read")

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
        report["duplicate_claim"] = {"ok": False, "code": duplicate["code"], "observed_version": 2}
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
        report["review_verification"] = "unverified"
        stages.append("distinct_text_review_recorded")
    finally:
        host.close()
    assert host.close_mode == "stdin_eof" and host.proc.returncode == 0 and not host.unexpected_turn
    assert host.mcp_children_ended > 0
    report["native_hosts"] = [
        {
            "pid": host.proc.pid,
            "exit_code": host.proc.returncode,
            "close_mode": host.close_mode,
            "mcp_children_ended": host.mcp_children_ended,
        }
    ]
    stages.append("initial_host_and_mcp_children_exited")

    # A new native host and MCP subprocess read the same task and context.
    restarted = NativeHost(binary, data, workspace / "restarted-stderr.private.log")
    try:
        restarted.initialize()
        tr, status_r, tools_r = restarted.start(status_checks.setdefault("restarted_thread", []))
        stages.append("restarted_thread_connected")
        assert tools_r == tools_a
        persisted = restarted.call(tr, "list_tasks", auth["B"])["tasks"]
        assert persisted == [accepted]
        assert restarted.call(tr, "get_context", context_pin) == context
        report["context"]["read_after_host_restart"] = True
        observe("after_host_restart", persisted[0])
        stages.append("task_and_context_reopened")
    finally:
        restarted.close()
    assert restarted.close_mode == "stdin_eof" and restarted.proc.returncode == 0
    assert not restarted.unexpected_turn and restarted.mcp_children_ended > 0
    report["native_hosts"].append(
        {
            "pid": restarted.proc.pid,
            "exit_code": restarted.proc.returncode,
            "close_mode": restarted.close_mode,
            "mcp_children_ended": restarted.mcp_children_ended,
        }
    )
    stages.append("restarted_host_and_mcp_children_exited")
    fresh_core = Core(data)
    fresh = fresh_core.execute("list_tasks", auth["B"])["tasks"]
    assert fresh == [accepted]
    assert fresh_core.execute("get_context", context_pin) == context
    report["context"]["read_from_fresh_core"] = True
    observe("fresh_core", fresh[0])
    stages.append("task_and_context_read_from_fresh_core")
    report.update(
        host="installed Codex public app-server",
        ephemeral=True,
        host_threads=2,
        runtime_statuses=[status_a, status_b, status_r],
        tools=tools_a,
        client=init["userAgent"],
        limitations="Isolated native backend, deterministic tool calls and text review.",
    )
    validate_report(report)


def run(binary, scratch_parent=SCRATCH):
    scratch_parent = scratch_parent.resolve(strict=True)
    if not scratch_parent.is_relative_to(SCRATCH.resolve(strict=True)):
        raise ValueError("Use a fixture under D:/agentsync-debug.")
    if (
        os.name != "nt"
        or not __debug__
        or metadata.version("agentsync-local") != VERSION
        or agentsync.__version__ != VERSION
        or not Path(agentsync.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    ):
        raise ValueError("Use the installed Amadeus a118 Python environment.")
    workspace = Path(tempfile.mkdtemp(prefix="codex-collaboration-", dir=scratch_parent))
    with binary.open("rb") as stream:
        binary_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {
        "status": "blocked",
        "amadeus_version": VERSION,
        "inference_turns": 0,
        "desktop_ui_tested": False,
        "global_configuration_modified": False,
        "codex_binary_sha256": binary_sha,
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    print(f"Probe evidence directory {workspace}", file=sys.stderr, flush=True)
    try:
        run_collaboration(binary, workspace, result)
        result["status"] = "passed_scoped"
    except NativeHostBlocked as exc:
        result.update(blocked_method=exc.method, reason=exc.reason, rpc_code=exc.rpc_code)
    except (Exception, KeyboardInterrupt) as exc:
        result["error_type"] = type(exc).__name__
        with (workspace / "failure.private.log").open("x", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
    with (workspace / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path)
    parser.add_argument("--scratch-parent", type=Path, default=SCRATCH)
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
    binary = binary.resolve(strict=True)
    if binary.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        parser.error("Use the native Codex executable.")
    return int(run(binary, args.scratch_parent)["status"] != "passed_scoped")


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only AgentSync probe through the actual registered Codex configuration.

No -c arguments or per-thread MCP overrides, no inference turns, no project,
agent, or task creation. MCP startup may initialize an empty shared database.
Native backend registration evidence does not establish desktop UI acceptance.
"""

import argparse
import json
import shutil
from pathlib import Path

from probe_codex_collaboration import ROOT, NativeHost

EXPECTED_TOOLS = sorted(
    [
        "create_project",
        "register_agent",
        "heartbeat",
        "create_task",
        "list_tasks",
        "get_project_state",
        "claim_task",
        "renew_lease",
        "update_task",
        "review_task",
        "reclaim_expired",
    ]
)


def run(binary):
    (ROOT / "work").mkdir(exist_ok=True)
    host = NativeHost(
        binary, None, ROOT / "work/registered-codex-stderr.log", use_registered_config=True
    )
    try:
        init = host.initialize()
        tid, status, tools = host.start()
        assert tools == EXPECTED_TOOLS
        result = host.send(
            "mcpServer/tool/call",
            {
                "threadId": tid,
                "server": "agentsync",
                "tool": "get_project_state",
                "arguments": {
                    "project_id": "registration-probe-no-project",
                    "session_id": "registration-probe-no-session",
                    "session_token": "registration-probe-invalid-credential",
                },
            },
        )
        assert not result.get("isError", False)
        expected = {
            "ok": False,
            "error": {
                "code": "unauthorized",
                "message": "Invalid session credentials.",
            },
        }
        envelope = result["structuredContent"]
        assert envelope == expected
        report = {
            "host": "installed Codex public app-server",
            "configuration_source": "actual shared registered configuration",
            "command_line_configuration_override": False,
            "thread_configuration_override": False,
            "runtime_status": status,
            "tools": tools,
            "verified_operation": "get_project_state",
            "response": envelope,
            "client": init["userAgent"],
            "inference_turns": 0,
            "ephemeral": True,
            "project_agent_task_writes": 0,
            "global_configuration_modified": False,
            "desktop_ui_tested": False,
            "limitations": "Native backend configuration loading only. MCP startup may initialize the shared database. No desktop UI or model development session was exercised.",
        }
        output = ROOT / "docs/codex-registration-probe.json"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report))
        return report
    finally:
        host.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-binary", type=Path)
    args = parser.parse_args()
    binary = args.codex_binary or shutil.which("codex.exe") or shutil.which("codex")
    if not binary or not Path(binary).is_file():
        raise SystemExit("Native Codex executable unavailable; pass --codex-binary.")
    if Path(binary).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise SystemExit("Use the native Codex executable, not a shell wrapper.")
    run(binary)


if __name__ == "__main__":
    main()

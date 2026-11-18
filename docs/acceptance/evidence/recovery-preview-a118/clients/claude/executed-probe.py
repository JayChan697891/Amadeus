"""Isolated official Claude MCP health check; no model prompts or credentials."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

import agentsync

SCRATCH = Path("D:/agentsync-debug")


def run(binary, scratch):
    scratch = scratch.resolve(strict=True)
    if not scratch.is_relative_to(SCRATCH.resolve(strict=True)):
        raise ValueError("Use a fixture under D:/agentsync-debug.")
    if (
        os.name != "nt"
        or not __debug__
        or metadata.version("agentsync-local") != "0.3.0a118"
        or agentsync.__version__ != "0.3.0a118"
        or not Path(agentsync.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    ):
        raise ValueError("Use the installed Amadeus a118 Python environment.")
    workspace = Path(tempfile.mkdtemp(prefix="claude-mcp-", dir=scratch))
    home = workspace / "home"
    home.mkdir()
    env = {
        k: os.environ[k]
        for k in ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "PATHEXT")
        if k in os.environ
    }
    env.update(
        {
            k: str(home)
            for k in (
                "CLAUDE_CONFIG_DIR",
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
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        DISABLE_AUTOUPDATER="1",
        DISABLE_TELEMETRY="1",
        DISABLE_ERROR_REPORTING="1",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
    )
    with binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {
        "status": "blocked",
        "host": "installed Claude Code CLI",
        "amadeus_version": "0.3.0a118",
        "client_sha256": digest,
        "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_prompts": 0,
        "isolated_config": True,
        "credentials_provided": False,
        "shared_config_modified": False,
        "tool_calls_tested": False,
        "desktop_ui_tested": False,
        "health_check_connected": False,
        "checks": [],
    }
    print(f"Probe evidence directory {workspace}", file=sys.stderr, flush=True)

    def invoke(name, args):
        report["phase"] = name
        with (
            (workspace / f"{name}-stdout.private.log").open("xb") as out,
            (workspace / f"{name}-stderr.private.log").open("xb") as err,
        ):
            done = subprocess.run(
                [str(binary), *args],
                env=env,
                cwd=workspace,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        report["checks"].append({"name": name, "exit_code": done.returncode})
        if done.returncode:
            raise RuntimeError("Command failed; retained private logs identify the cause.")
        return (workspace / f"{name}-stdout.private.log").read_text(encoding="utf-8")

    try:
        report["client_version"] = invoke("version", ["--version"]).strip()
        help_text = invoke("mcp_help", ["mcp", "--help"])
        if "add-json" not in help_text or "list" not in help_text:
            raise RuntimeError("Required public MCP commands unavailable.")
        server = {
            "command": sys.executable,
            "args": ["-I", "-B", "-m", "agentsync", "--data-dir", str(workspace / "data"), "mcp"],
        }
        invoke("add", ["mcp", "add-json", "--scope", "user", "agentsync", json.dumps(server)])
        listed = invoke("list", ["mcp", "list"])
        lines = re.sub(r"\x1b\[[0-9;]*m", "", listed).splitlines()
        own = [line for line in lines if line.startswith("agentsync:")]
        report["health_check_connected"] = len(own) == 1 and bool(
            re.search(r"\bConnected\b", own[0])
        )
        if report["health_check_connected"]:
            report["status"] = "passed_scoped"
    except (Exception, KeyboardInterrupt) as exc:
        report["error_type"] = type(exc).__name__
    with (workspace / "result.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-binary", required=True, type=Path)
    parser.add_argument("--scratch-parent", type=Path, default=SCRATCH)
    args = parser.parse_args()
    binary = args.claude_binary.resolve(strict=True)
    if binary.suffix.lower() != ".exe":
        parser.error("Use the installed native Claude Code executable.")
    return int(run(binary, args.scratch_parent)["status"] != "passed_scoped")


if __name__ == "__main__":
    raise SystemExit(main())

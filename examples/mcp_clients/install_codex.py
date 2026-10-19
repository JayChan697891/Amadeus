"""Register AgentSync with the public Codex MCP CLI, without editing TOML.

Run using a Python environment with agentsync-local installed. --dry-run reads
configuration and validates Python but never calls `mcp add`. No database or data
directory is created here; the MCP server creates it on first connection.
Reference: https://developers.openai.com/codex/mcp/
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agentsync.config import resolve_data_dir
from agentsync.errors import AgentSyncError


class InstallError(Exception):
    """Actionable safe message; never carries raw configuration or child output."""


def run_process(argv):
    try:
        return subprocess.run(
            [str(arg) for arg in argv], capture_output=True, text=True,
            encoding="utf-8", timeout=30, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError("Could not run a required executable; check its path and retry.") from exc


def resolve_codex(value=None):
    # Windows npm .cmd/.ps1 shims require a shell. Prefer the public installed
    # native CLI on PATH and require an explicit native executable otherwise.
    executable = value or shutil.which("codex.exe" if os.name == "nt" else "codex")
    if not executable:
        raise InstallError("Codex CLI not found. Pass --codex with its native executable path.")
    path = Path(executable)
    if not path.is_file():
        found = shutil.which(str(executable))
        if found:
            path = Path(found)
    if not path.is_file() or path.suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise InstallError("Pass --codex pointing to the native Codex executable, not a shell shim.")
    if os.name == "nt" and path.suffix.lower() != ".exe":
        raise InstallError("Windows --codex must point to a native .exe executable.")
    return path.resolve()


def read_entry(codex):
    result = run_process([codex, "mcp", "get", "agentsync", "--json"])
    if result.returncode:
        # Only this observed public CLI not-found response permits installation.
        # Parse/config/auth failures must never be mistaken for an absent entry.
        if (result.returncode == 1 and not result.stdout.strip()
                and result.stderr.strip() == "Error: No MCP server named 'agentsync' found."):
            return None
        raise InstallError("Cannot safely read Codex MCP settings. Run `codex mcp get agentsync --json` privately to diagnose; no changes made.")
    try:
        entry = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise InstallError("Codex returned malformed MCP JSON; no changes made.") from exc
    if (not isinstance(entry, dict) or entry.get("name") != "agentsync"
            or not isinstance(entry.get("transport"), dict)
            or type(entry.get("enabled")) is not bool):
        raise InstallError("Codex returned an unrecognized MCP configuration; no changes made.")
    return entry


def matches(entry, python, args):
    transport = entry["transport"]
    command = transport.get("command")
    if not isinstance(command, str):
        return False
    # Exact argument comparison intentionally treats a different data directory
    # as a conflict, even when other launch settings happen to match.
    return (
        entry["enabled"] is True
        and transport.get("type") == "stdio"
        and os.path.normcase(command) == os.path.normcase(str(python))
        and transport.get("args") == args
        and not transport.get("env")
        and not transport.get("env_vars")
        and not transport.get("cwd")
        and entry.get("enabled_tools") is None
        and not entry.get("disabled_tools")
    )


def install(codex=None, python=None, data_dir=None, dry_run=False):
    codex = resolve_codex(codex)
    python = Path(python or sys.executable).resolve()
    if not python.is_file():
        raise InstallError("Python executable does not exist; pass --python with an installed environment.")
    if (python.suffix.lower() in {".cmd", ".bat", ".ps1"}
            or os.name == "nt" and python.suffix.lower() != ".exe"):
        raise InstallError("Pass --python with a native Python executable, not a shell shim.")
    # Isolated Python ignores cwd/PYTHONPATH, so a source checkout alone cannot
    # falsely satisfy the installed-environment prerequisite.
    checked = run_process([python, "-I", "-c",
        "from importlib.metadata import version; import agentsync.integrations.mcp; version('agentsync-local')"])
    if checked.returncode:
        raise InstallError("AgentSync is not installed in the selected Python environment. Install its wheel there, then retry.")
    try:
        data = resolve_data_dir(data_dir, create=False)
    except (AgentSyncError, OSError, ValueError) as exc:
        raise InstallError("Data directory must be an absolute writable local directory.") from exc
    args = ["-m", "agentsync", "--data-dir", str(data), "mcp"]
    existing = read_entry(codex)
    if existing is not None:
        if matches(existing, python, args):
            return {"status": "already_configured", "changed": False}
        raise InstallError("An existing agentsync MCP entry differs. Review it privately with `codex mcp get agentsync --json`; preserve or explicitly remove it yourself before retrying. Nothing was overwritten.")
    if dry_run:
        return {"status": "dry_run", "changed": False,
                "planned_argv": [str(codex), "mcp", "add", "agentsync", "--", str(python), *args]}
    # Detect settings changes during prerequisite checks. The public CLI has no
    # compare-and-swap; avoid concurrent configuration writers during install.
    if read_entry(codex) is not None:
        raise InstallError("The agentsync entry appeared during installation; no write attempted. Retry to inspect it safely.")
    added = run_process([codex, "mcp", "add", "agentsync", "--", python, *args])
    if added.returncode:
        raise InstallError("Codex MCP registration failed. Inspect `codex mcp get agentsync --json` privately before retrying.")
    installed = read_entry(codex)
    if installed is None or not matches(installed, python, args):
        raise InstallError("Codex registration could not be verified. Inspect the agentsync entry privately; no automatic rollback was attempted.")
    return {"status": "installed", "changed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", help="Native Codex executable path")
    parser.add_argument("--python", help="Python with agentsync-local installed (default: current Python)")
    parser.add_argument("--data-dir", help="Absolute shared data directory (default: AgentSync user data)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        report = install(codex=args.codex, python=args.python,
                         data_dir=args.data_dir, dry_run=args.dry_run)
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

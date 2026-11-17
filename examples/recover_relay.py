"""Inspect an existing relay or reconcile one explicitly selected saved wave."""

import argparse
import getpass
import json
import re
import subprocess
import sys
import warnings
from pathlib import Path


def absolute_path(value):
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path.")
    return path


def wave_id(value):
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise argparse.ArgumentTypeError("Use the exact 64-character wave ID from status.")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data-dir", "scratch-root", "receipts"):
        parser.add_argument(f"--{name}", type=absolute_path, required=True)
    parser.add_argument("--project-id", required=True)
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("status", help="Read the pending wave")
    operations.add_parser("history", help="Read the latest wave history page")
    operations.add_parser("task", help="Read attempt observations for one task").add_argument(
        "task_id"
    )
    operations.add_parser("reconcile", help="Reconcile one exact saved wave").add_argument(
        "wave_id", type=wave_id
    )
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error("Use a terminal that can hide credential input.")

    credentials = {"project_id": args.project_id}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            credentials["admin_token"] = getpass.getpass("Project owner token: ")
            if args.operation == "reconcile":
                credentials["session_id"] = getpass.getpass("Project session ID: ")
                credentials["session_token"] = getpass.getpass("Project session token: ")
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError):
        parser.error("Secure credential input did not complete.")

    command = [sys.executable, "-I", "-B", "-m", "agentsync", "--data-dir", str(args.data_dir)]
    if args.operation == "reconcile":
        command.extend(("relay-reconcile", args.wave_id))
    else:
        command.append("relay-status")
        if args.operation == "history":
            command.append("--history")
        elif args.operation == "task":
            command.extend(("--task-id", args.task_id))
    command.extend(("--scratch-root", str(args.scratch_root), "--receipts", str(args.receipts)))
    try:
        child = subprocess.run(
            command, input=json.dumps(credentials).encode("utf-8"), check=False, timeout=60
        )
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        print(
            "Command outcome unknown. Check status before taking further action.", file=sys.stderr
        )
        return 1
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())

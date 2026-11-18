"""Create one Linux terminal project and privately deliver its owner credentials.

Run with the installed Amadeus Python and a new absolute root directory. Retain
private-owner.json locally for later owner prompts. On failure, preserve the
partial root. A credential write or fsync failure may leave an incomplete file.
The initializer never reuses a root, removes state, or registers a replacement.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient


def initialize(root):
    if sys.platform != "linux":
        raise ValueError("linux_required")
    if not root.is_absolute():
        raise ValueError("absolute_root_required")
    previous_mask = os.umask(0o077)
    try:
        root.mkdir(mode=0o700)
        root = root.resolve(strict=True)
        repo, empty = root / "repo", root / "git-empty"
        repo.mkdir(mode=0o700)
        empty.mkdir(mode=0o700)
        executable = shutil.which("git", path=os.defpath)
        if executable is None:
            raise FileNotFoundError("git_required")
        environment = {
            "PATH": os.defpath,
            "HOME": str(root),
            "XDG_CONFIG_HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }

        def git(*arguments):
            return subprocess.run(
                [
                    executable,
                    "-c",
                    f"core.hooksPath={empty}",
                    "-c",
                    "commit.gpgSign=false",
                    *arguments,
                ],
                cwd=repo,
                env=environment,
                capture_output=True,
                check=True,
                timeout=30,
            ).stdout

        git("init", "--initial-branch=terminal-main", f"--template={empty}")
        git("config", "--local", "user.name", "Amadeus terminal owner")
        git("config", "--local", "user.email", "terminal-owner@example.invalid")
        with (repo / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(
                "# Amadeus terminal project\n\nDedicated source for owner-approved tasks.\n"
            )
        git("add", "--", "README.md")
        git("commit", "--no-gpg-sign", "-m", "Initialize Amadeus terminal project")
        assert not git("status", "--porcelain", "--untracked-files=all")

        credentials = root / "private-owner.json"
        descriptor = os.open(
            credentials,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            response = AgentSyncClient(root / "core").call(
                "create_project", name="Owner terminal project", root_path=str(repo)
            )
            if not response["ok"]:
                raise AgentSyncError(response["error"]["code"], "Project creation failed.")
            owner = response["data"]
            assert set(owner) == {"project_id", "admin_token"}
            json.dump(owner, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {
            "project_id": owner["project_id"],
            "root": str(root),
            "private_owner_file": str(credentials),
        }
    finally:
        os.umask(previous_mask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    try:
        result = initialize(args.root)
    except (Exception, KeyboardInterrupt) as error:
        print(
            json.dumps(
                {
                    "error_code": error.code
                    if isinstance(error, AgentSyncError)
                    else type(error).__name__,
                    "partial_state_retained": args.root.exists(),
                    "automatic_retry": False,
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded local Git operations. Never apply changes to the source checkout."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, NoReturn

from agentsync.errors import AgentSyncError

MAX_OUTPUT = 4 * 1024 * 1024
MAX_REPOSITORY = 256 * 1024 * 1024
HEX = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
IDENTITY = re.compile(r"(?:[0-9a-f]{64}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\Z")


def fail(code: str, message: str) -> NoReturn:
    raise AgentSyncError(code, message, 409)


def physical(path: Path) -> list[str]:
    """Reject links in every existing ancestor, including Windows junctions."""
    for ancestor in (*reversed(path.parents), path):
        try:
            info = ancestor.lstat()
        except OSError:
            fail("workspace_boundary", "Workspace path cannot be inspected.")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            fail("workspace_boundary", "Workspace links and reparse points are forbidden.")
    return [str(info.st_dev), str(info.st_ino)]


def valid_sha(value: str) -> str:
    if not HEX.fullmatch(value):
        fail("invalid_revision", "Expected a complete hexadecimal commit ID.")
    return value


def config_digest(repo: Path) -> str:
    config = repo / "config"
    physical(config)
    if config.stat().st_size > MAX_OUTPUT:
        fail("repository_too_large", "Git configuration exceeds supported size.")
    return hashlib.sha256(config.read_bytes()).hexdigest()


class GitWorkspaceStore:
    def __init__(self, data_dir: Path | str):
        self.root = Path(data_dir).resolve() / "managed-git"
        self.root.mkdir(parents=True, exist_ok=True)
        self.root_identity = physical(self.root)
        binary = shutil.which("git")
        if binary is None:
            fail("unsupported", "Git is not installed.")
        self.binary = str(Path(binary).resolve())
        for name in (
            "receipts",
            "intents",
            "repositories",
            "worktrees",
            "comparisons",
            "home",
            "hooks",
        ):
            (self.root / name).mkdir(exist_ok=True)
            physical(self.root / name)

    def _env(self) -> dict[str, str]:
        env = {
            key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
        }
        env.update(
            HOME=str(self.root / "home"),
            XDG_CONFIG_HOME=str(self.root / "home"),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_OPTIONAL_LOCKS="0",
            GIT_ALLOW_PROTOCOL="file",
            LC_ALL="C",
        )
        return env

    def _git(self, cwd: Path, *args: str, accepted: tuple[int, ...] = (0,)) -> tuple[int, bytes]:
        if physical(self.root) != self.root_identity:
            fail("workspace_boundary", "Managed root identity changed.")
        argv = [self.binary, "--no-pager"]
        for setting in (
            f"core.hooksPath={self.root / 'hooks'}",
            "core.fsmonitor=false",
            "core.untrackedCache=false",
            "core.quotePath=false",
            "core.sshCommand=false",
            "credential.helper=",
            "diff.external=",
            "submodule.recurse=false",
            "protocol.ext.allow=never",
            "protocol.file.allow=always",
            "gc.auto=0",
            "maintenance.auto=false",
            "core.logAllRefUpdates=false",
            f"init.templateDir={self.root / 'hooks'}",
            "commit.gpgSign=false",
            "tag.gpgSign=false",
            "user.name=AgentSync",
            "user.email=agentsync@localhost",
        ):
            argv += ["-c", setting]
        # File-backed output prevents a malicious repository from exhausting RAM.
        with tempfile.TemporaryFile(dir=self.root) as output:
            try:
                process = subprocess.Popen(
                    [*argv, "-C", str(cwd), *args],
                    env=self._env(),
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 30
                while process.poll() is None:
                    if (
                        time.monotonic() > deadline
                        or os.fstat(output.fileno()).st_size > MAX_OUTPUT
                    ):
                        process.kill()
                        process.wait()
                        fail("git_failed", "Git operation exceeded its time or output limit.")
                    time.sleep(0.01)
                returncode = process.wait()
            except (OSError, subprocess.TimeoutExpired):
                fail("git_failed", "Git operation failed or exceeded its time limit.")
            if output.tell() > MAX_OUTPUT:
                fail("repository_too_large", "Git output exceeds the supported limit.")
            output.seek(0)
            data = output.read(MAX_OUTPUT + 1)
        if returncode not in accepted:
            fail("git_failed", "Git operation failed; unsupported or invalid repository.")
        return returncode, data

    def _path(self, group: str, identity: str) -> Path:
        if not IDENTITY.fullmatch(identity):
            fail("invalid_workspace", "Workspace identity is invalid.")
        path = self.root / group / identity
        physical(path.parent)
        return path

    def _save(self, path: Path, value: dict[str, Any]) -> None:
        if path.exists():
            physical(path)
        temporary = path.with_suffix(".new")
        if temporary.exists():
            physical(temporary)
        temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _receipt(self, identity: str) -> dict[str, Any] | None:
        path = self._path("receipts", identity)
        if not path.exists():
            return None
        physical(path)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fail("workspace_incomplete", "Workspace receipt requires recovery.")

    def _intent(self, identity: str, value: dict[str, Any]) -> None:
        path = self._path("intents", identity)
        if path.exists():
            physical(path)
            if json.loads(path.read_text(encoding="utf-8")) != value:
                fail("workspace_incomplete", "An incompatible workspace intent exists.")
        else:
            self._save(path, value)

    def _names(self, data: bytes) -> list[str]:
        names = []
        for raw in data.split(b"\0"):
            if not raw:
                continue
            try:
                name = raw.decode("utf-8", errors="strict")
            except UnicodeError:
                fail("unsupported", "Non-UTF-8 Git filenames are unsupported.")
            parts = name.split("/")
            if any(
                not part
                or part in {".", ".."}
                or part.casefold() == ".git"
                or part.endswith((".", " "))
                or any(ord(c) < 32 or c in "\\:" for c in part)
                or re.match(r"(?i)^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", part)
                for part in parts
            ):
                fail("workspace_boundary", "Git tree contains unsafe filenames.")
            names.append(name)
        return names

    def _tree(self, repo: Path, sha: str) -> None:
        _, data = self._git(repo, "ls-tree", "-r", "-l", "-z", valid_sha(sha))
        total = 0
        folded = set()
        for entry in data.split(b"\0"):
            if not entry:
                continue
            metadata, name = entry.split(b"\t", 1)
            mode, kind, _oid, size = metadata.split()
            if mode not in {b"100644", b"100755"} or kind != b"blob":
                fail("unsupported", "Submodules and symbolic-link tree entries are unsupported.")
            decoded = self._names(name + b"\0")[0]
            if decoded.casefold() in folded:
                fail("unsupported", "Case-aliasing Git paths are unsupported.")
            folded.add(decoded.casefold())
            total += int(size)
            if total > MAX_REPOSITORY:
                fail("repository_too_large", "Committed tree exceeds supported size.")

    def _head(self, repo: Path) -> str:
        _, data = self._git(repo, "rev-parse", "--verify", "HEAD^{commit}")
        return valid_sha(data.decode("ascii").strip())

    def _source_config(self, source: Path) -> None:
        # This command reads config syntax only and does not run status, filters,
        # hooks or a pack subprocess. Includes are deliberately not expanded.
        _, output = self._git(source, "config", "--local", "--no-includes", "--null", "--list")
        for item in output.split(b"\0"):
            if not item:
                continue
            key = item.split(b"\n", 1)[0].decode("utf-8", errors="strict").casefold()
            if key.startswith(
                ("include.", "includeif.", "filter.", "uploadpack.", "diff.", "merge.")
            ) or key in {
                "core.alternaterefscommand",
                "core.gitproxy",
                "core.sshcommand",
                "extensions.worktreeconfig",
            }:
                fail(
                    "unsupported",
                    "Executable filters, includes and external Git drivers are unsupported.",
                )

    def _status(self, repo: Path) -> list[str]:
        _, data = self._git(
            repo,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=all",
        )
        entries = data.split(b"\0")
        result = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            code = entry[:2].decode("ascii")
            name = self._names(entry[3:] + b"\0")[0]
            result.append(code + " " + name)
            if "R" in code or "C" in code:
                if index >= len(entries) or not entries[index]:
                    fail("git_failed", "Invalid Git status output.")
                result.append("from " + self._names(entries[index] + b"\0")[0])
                index += 1
        return result

    def capture_repository(self, root: Path | str, identity: str) -> dict[str, Any]:
        source = Path(root)
        source_identity = physical(source)
        source = source.resolve()
        if self.root.is_relative_to(source) or source.is_relative_to(self.root):
            fail("workspace_boundary", "Source and managed repository storage must be disjoint.")
        gitdir = source / ".git"
        physical(gitdir)
        if not gitdir.is_dir() or any(
            (gitdir / part).exists()
            for part in (
                "commondir",
                "config.worktree",
                "objects/info/alternates",
                "objects/info/http-alternates",
            )
        ):
            fail("unsupported", "External Git directories and alternate objects are unsupported.")
        size = 0
        entries = 0
        for directory, dirs, files in os.walk(gitdir, followlinks=False):
            for name in [*dirs, *files]:
                entry = Path(directory) / name
                physical(entry)
                entries += 1
                size += entry.stat().st_size
                if entries > 100000 or size > MAX_REPOSITORY:
                    fail("repository_too_large", "Repository metadata exceeds supported size.")
        self._source_config(source)
        _, top = self._git(source, "rev-parse", "--show-toplevel")
        if Path(top.decode("utf-8").strip()).resolve() != source:
            fail("workspace_boundary", "Project must be the repository root.")
        head, status = self._head(source), self._status(source)
        old = self._receipt(identity)
        if old:
            if old.get("operation") != "capture" or old.get("source_root") != str(source):
                fail("idempotency_conflict", "Capture identity is bound to different inputs.")
            self._intent(
                identity,
                {"operation": "capture", "source": str(source), "base_sha": old["base_sha"]},
            )
            self.verify_snapshot(old)
            return old
        self._tree(source, head)
        self._intent(identity, {"operation": "capture", "source": str(source), "base_sha": head})
        target = self._path("repositories", identity)
        bundle = self._path("intents", identity).with_suffix(".bundle")
        if target.exists():
            physical(target)
            if self._head(target) != head:
                fail("workspace_incomplete", "Interrupted capture requires recovery.")
        else:
            if bundle.exists():
                physical(bundle)
                fail("workspace_incomplete", "Interrupted bundle requires recovery.")
            self._git(source, "bundle", "create", str(bundle), "HEAD")
            if bundle.stat().st_size > MAX_REPOSITORY:
                fail("repository_too_large", "Repository bundle exceeds supported size.")
            self._git(self.root, "clone", "--bare", "--no-local", str(bundle), str(target))
            self._git(target, "config", "--unset-all", "remote.origin.url", accepted=(0, 5))
        if (
            physical(source) != source_identity
            or self._head(source) != head
            or self._status(source) != status
        ):
            fail("stale_snapshot", "Source repository changed during capture.")
        if self._head(target) != head:
            fail("stale_snapshot", "Captured commit differs from expected HEAD.")
        receipt = {
            "operation": "capture",
            "id": identity,
            "base_sha": head,
            "source_root": str(source),
            "source_dirty": bool(status),
            "source_status": status,
            "committed_only": True,
            "repository_path": str(target),
            "root_identity": physical(target),
            "config_sha256": config_digest(target),
        }
        self._save(self._path("receipts", identity), receipt)
        return receipt

    def verify_snapshot(self, snapshot: dict[str, Any]) -> None:
        repo = self._path("repositories", snapshot["id"])
        if str(repo) != snapshot["repository_path"] or physical(repo) != snapshot["root_identity"]:
            fail("workspace_boundary", "Managed repository identity changed.")
        if (repo / "objects" / "info" / "alternates").exists():
            fail("workspace_boundary", "Managed alternate objects are forbidden.")
        if config_digest(repo) != snapshot["config_sha256"]:
            fail("workspace_boundary", "Managed Git configuration changed.")
        self._git(repo, "cat-file", "-e", valid_sha(snapshot["base_sha"]) + "^{commit}")

    def create_worktree(
        self, snapshot: dict[str, Any], identity: str, *, task_id: str | None = None
    ) -> dict[str, Any]:
        self._intent(
            identity, {"operation": "create", "snapshot_id": snapshot["id"], "task_id": task_id}
        )
        self.verify_snapshot(snapshot)
        old = self._receipt(identity)
        if old:
            if (
                old.get("operation") != "create"
                or old.get("snapshot_id") != snapshot["id"]
                or old.get("task_id") != task_id
            ):
                fail("idempotency_conflict", "Worktree identity is bound to different inputs.")
            self.inspect_worktree(old)
            return old
        repo = Path(snapshot["repository_path"])
        path = self._path("worktrees", identity)
        if not path.exists():
            self._git(
                repo, "worktree", "add", "--detach", str(path), valid_sha(snapshot["base_sha"])
            )
        physical(path)
        if self._head(path) != snapshot["base_sha"] or self._status(path):
            fail(
                "workspace_incomplete",
                "Interrupted workspace contains changes; retained for recovery.",
            )
        receipt = {
            "operation": "create",
            "task_id": task_id,
            "id": identity,
            "snapshot_id": snapshot["id"],
            "base_sha": snapshot["base_sha"],
            "head_sha": snapshot["base_sha"],
            "path": str(path),
            "status": "ready",
            "version": 1,
            "repository_path": str(repo),
            "root_identity": physical(path),
            "repository_identity": snapshot["root_identity"],
            "config_sha256": snapshot["config_sha256"],
        }
        self._save(self._path("receipts", identity), receipt)
        return receipt

    def inspect_worktree(self, receipt: dict[str, Any]) -> dict[str, Any]:
        path = self._path("worktrees", receipt["id"])
        repo = self._path("repositories", receipt["snapshot_id"])
        if str(path) != receipt["path"] or physical(path) != receipt["root_identity"]:
            fail("workspace_boundary", "Managed worktree identity changed.")
        if (
            str(repo) != receipt["repository_path"]
            or physical(repo) != receipt["repository_identity"]
        ):
            fail("workspace_boundary", "Managed repository identity changed.")
        if config_digest(repo) != receipt["config_sha256"]:
            fail("workspace_boundary", "Managed Git configuration changed.")
        _, common = self._git(path, "rev-parse", "--git-common-dir")
        common_path = Path(common.decode("utf-8").strip())
        if (path / common_path).resolve() != repo.resolve():
            fail("workspace_boundary", "Worktree Git directory changed.")
        head = self._head(path)
        self._tree(path, head)
        status = self._status(path)
        return {**receipt, "head_sha": head, "dirty": bool(status), "status_entries": status}

    def _merge(
        self, left: dict[str, Any], right: dict[str, Any], lh: str, rh: str, identity: str
    ) -> dict[str, Any]:
        for receipt, expected in ((left, lh), (right, rh)):
            valid_sha(expected)
            state = self.inspect_worktree(receipt)
            if state["head_sha"] != expected:
                fail("stale_snapshot", "Worktree HEAD changed.")
            if state["dirty"]:
                fail("dirty_worktree", "Commit worktree changes before comparing.")
        if left["snapshot_id"] != right["snapshot_id"] or left["base_sha"] != right["base_sha"]:
            fail("invalid_workspace", "Worktrees must share the same snapshot.")
        repo = Path(left["repository_path"])
        base = valid_sha(left["base_sha"])
        for head in (lh, rh):
            code, _ = self._git(repo, "merge-base", "--is-ancestor", base, head, accepted=(0, 1))
            if code:
                fail("stale_snapshot", "Worktree history no longer descends from its snapshot.")
        changed = []
        for head in (lh, rh):
            _, output = self._git(
                repo,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                base,
                head,
                "--",
            )
            changed.append(set(self._names(output)))
        path = self._path("comparisons", identity)
        self._intent(identity, self._merge_binding(left, right, lh, rh))
        if path.exists():
            fail(
                "workspace_incomplete",
                "Existing comparison is retained for recovery; use a new operation ID.",
            )
        self._git(repo, "worktree", "add", "--detach", str(path), lh)
        code, _ = self._git(path, "merge", "--no-commit", "--no-ff", rh, accepted=(0, 1))
        _, conflicts = self._git(path, "diff", "--name-only", "--diff-filter=U", "-z", "--")
        conflict_paths = self._names(conflicts)
        if code and not conflict_paths:
            fail("git_failed", "Git merge failed without a supported conflict report.")
        # Revalidate both original actors after the potentially slow merge.
        for receipt, expected in ((left, lh), (right, rh)):
            state = self.inspect_worktree(receipt)
            if state["head_sha"] != expected or state["dirty"]:
                fail("stale_snapshot", "Worktree changed during comparison.")
        return {
            "base_sha": base,
            "left_sha": lh,
            "right_sha": rh,
            "overlapping_paths": sorted(changed[0] & changed[1]),
            "mergeable": code == 0,
            "conflict_paths": conflict_paths,
            "merge_exit_code": code,
            "_merge_path": str(path),
        }

    @staticmethod
    def _merge_binding(
        left: dict[str, Any], right: dict[str, Any], lh: str, rh: str
    ) -> dict[str, Any]:
        return {
            "operation": "merge",
            "snapshot_id": left["snapshot_id"],
            "right_snapshot_id": right["snapshot_id"],
            "base_sha": left["base_sha"],
            "right_base_sha": right["base_sha"],
            "left_id": left["id"],
            "right_id": right["id"],
            "left": valid_sha(lh),
            "right": valid_sha(rh),
        }

    def compare_worktrees(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
        expected_left_head: str,
        expected_right_head: str,
        identity: str,
    ) -> dict[str, Any]:
        result = self._merge(left, right, expected_left_head, expected_right_head, identity)
        return {key: value for key, value in result.items() if not key.startswith("_")}

    def prepare_merge_candidate(
        self,
        left: dict[str, Any],
        right: dict[str, Any],
        expected_left_head: str,
        expected_right_head: str,
        identity: str,
    ) -> dict[str, Any]:
        binding = self._merge_binding(left, right, expected_left_head, expected_right_head)
        self._intent(identity, binding)
        old = self._receipt(identity)
        if old:
            if old.get("operation") != "candidate" or old.get("input_binding") != binding:
                fail("idempotency_conflict", "Candidate identity is bound to different inputs.")
            for receipt, expected in ((left, expected_left_head), (right, expected_right_head)):
                state = self.inspect_worktree(receipt)
                if state["head_sha"] != valid_sha(expected) or state["dirty"]:
                    fail("stale_snapshot", "Worktree changed since candidate preparation.")
            self._git(
                Path(left["repository_path"]),
                "cat-file",
                "-e",
                valid_sha(old["candidate_sha"]) + "^{commit}",
            )
            candidate_path = self._path("comparisons", identity)
            if (
                str(candidate_path) != old["candidate_path"]
                or physical(candidate_path) != old["candidate_identity"]
                or self._head(candidate_path) != old["candidate_sha"]
                or self._status(candidate_path)
            ):
                fail("stale_snapshot", "Prepared candidate changed or its path was replaced.")
            return old
        stage_path = self._path("intents", identity).with_suffix(".merge-ready")
        if stage_path.exists():
            physical(stage_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            if stage.get("input_binding") != binding:
                fail("workspace_incomplete", "Candidate recovery is bound to different inputs.")
            result = stage["result"]
            if (
                result["left_sha"] != expected_left_head
                or result["right_sha"] != expected_right_head
            ):
                fail("workspace_incomplete", "Candidate recovery inputs do not match the intent.")
            for receipt, expected in ((left, expected_left_head), (right, expected_right_head)):
                state = self.inspect_worktree(receipt)
                if state["head_sha"] != valid_sha(expected) or state["dirty"]:
                    fail("stale_snapshot", "Worktree changed before candidate recovery.")
            path = self._path("comparisons", identity)
            if physical(path) != stage["path_identity"]:
                fail("workspace_boundary", "Candidate recovery path identity changed.")
        else:
            result = self._merge(left, right, expected_left_head, expected_right_head, identity)
            if not result["mergeable"]:
                fail("merge_conflict", "Merge conflicts require independent resolution.")
            path = Path(result.pop("_merge_path"))
            _, tree = self._git(path, "write-tree")
            stage = {
                "input_binding": binding,
                "result": result,
                "tree": valid_sha(tree.decode("ascii").strip()),
                "path_identity": physical(path),
            }
            self._save(stage_path, stage)
        _, index_tree = self._git(path, "write-tree")
        if index_tree.decode("ascii").strip() != stage["tree"]:
            fail("workspace_incomplete", "Prepared merge index changed; retained for recovery.")
        code, _ = self._git(
            path, "diff", "--quiet", "--no-ext-diff", "--no-textconv", "--", accepted=(0, 1)
        )
        _, untracked = self._git(path, "ls-files", "--others", "--exclude-standard", "-z")
        if code or untracked:
            fail("workspace_incomplete", "Prepared merge files changed; retained for recovery.")
        current = self._head(path)
        if current == expected_left_head:
            self._git(
                path,
                "commit",
                "--allow-empty",
                "-m",
                "AgentSync merge candidate; awaiting human approval",
            )
        else:
            # A crash after commit but before receipt must not create a second commit.
            _, tree = self._git(path, "rev-parse", "HEAD^{tree}")
            _, parents = self._git(path, "show", "-s", "--format=%P", "HEAD")
            parent_ids = parents.decode("ascii").strip().split()
            if tree.decode("ascii").strip() != stage["tree"] or parent_ids not in (
                [expected_left_head],
                [expected_left_head, expected_right_head],
            ):
                fail("workspace_incomplete", "Candidate recovery commit does not match its intent.")
        sha = self._head(path)
        self._tree(path, sha)
        _, names = self._git(
            path,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--name-only",
            "-z",
            result["base_sha"],
            sha,
            "--",
        )
        candidate = {
            "operation": "candidate",
            "input_binding": binding,
            **result,
            "candidate_id": identity,
            "candidate_sha": sha,
            "changed_paths": self._names(names),
            "status": "awaiting_human_approval",
            "candidate_path": str(path),
            "candidate_identity": physical(path),
        }
        self._save(self._path("receipts", identity), candidate)
        return candidate


GitWorkspaceManager = GitWorkspaceStore

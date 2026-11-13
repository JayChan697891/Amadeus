"""Bounded Git operations for an approved create-only external worktree."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from agentsync.verification.candidate import CandidateInput, _linked_directory
from agentsync.workspaces.git import (
    MAX_OUTPUT,
    MAX_REPOSITORY,
    GitWorkspaceStore,
    _walk_error,
    fail,
    physical,
    valid_sha,
)

_CONFIG = frozenset(
    {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.symlinks",
        "core.ignorecase",
        "core.autocrlf",
        "core.eol",
        "core.safecrlf",
        "core.precomposeunicode",
        "core.protecthfs",
        "core.protectntfs",
        "core.hookspath",
        "core.longpaths",
        "core.quotepath",
        "core.abbrev",
        "core.sharedrepository",
        "core.fsmonitor",
        "core.untrackedcache",
        "core.commitgraph",
        "core.checkstat",
        "core.trustctime",
        "extensions.objectformat",
        "init.defaultbranch",
        "user.name",
        "user.email",
        "user.signingkey",
        "commit.gpgsign",
        "tag.gpgsign",
        "gc.auto",
        "maintenance.auto",
    }
)
_REMOTE_CONFIG = re.compile(
    r"(?:remote\..+\.(?:url|pushurl|fetch|push)|branch\..+\.(?:remote|merge|rebase))\Z"
)
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
_ATTRIBUTES = {b"filter", b"working-tree-encoding", b"ident", b"crlf", b"text", b"eol"}
_DEVICE = re.compile(r"(?i)^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)")


def _state(message: str) -> NoReturn:
    fail("integration_boundary", message)


def _normal_path(path: Path) -> tuple[str, ...]:
    return tuple(unicodedata.normalize("NFC", part).casefold() for part in path.parts)


def _overlaps(left: Path, right: Path) -> bool:
    a, b = _normal_path(left), _normal_path(right)
    return a[: len(b)] == b or b[: len(a)] == a


def _exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def integration_path(value: str) -> Path:
    path = Path(value)
    if (
        not path.is_absolute()
        or not path.name
        or ".." in path.parts
        or value.startswith(("\\\\", "//"))
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(
            part.casefold() == ".git"
            or part.endswith((".", " "))
            or _DEVICE.match(part)
            or any(char in ':<>"|?*' for char in part)
            for part in path.parts[1:]
        )
    ):
        _state("Integration requires an absolute local path without aliases.")
    parent = path.parent
    physical(parent)
    return parent.resolve(strict=True) / path.name


def _read_regular(path: Path, bound: int) -> bytes:
    identity = physical(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 <= info.st_size <= bound:
        _state("Integration requires bounded, ordinary files with no hard links.")
    with path.open("rb") as file:
        data = file.read(bound + 1)
    after = path.lstat()
    if (
        len(data) != info.st_size
        or physical(path) != identity
        or info.st_mtime_ns != after.st_mtime_ns
        or info.st_ctime_ns != after.st_ctime_ns
    ):
        _state("An integration file changed while it was read.")
    return data


def bundle_pin(path: Path) -> str:
    identity = physical(path)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= MAX_REPOSITORY
    ):
        _state("The private candidate bundle exceeds its limits or changed identity.")
    with path.open("rb") as file:
        hashed = hashlib.file_digest(file, "sha256").hexdigest()
    after = path.lstat()
    if (
        physical(path) != identity
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
    ):
        _state("The private candidate bundle changed during inspection.")
    return hashed


@dataclass(frozen=True, slots=True)
class _Blob:
    path: str
    sha: str
    size: int
    executable: bool


class IntegrationGit:
    def __init__(self, store: GitWorkspaceStore) -> None:
        self.store = store

    def _git(self, cwd: Path, *args: str, **options: Any) -> tuple[int, bytes]:
        hooks = self.store.root / "hooks"
        physical(hooks)
        if not hooks.is_dir() or any(hooks.iterdir()):
            _state("Integration requires an empty managed hooks directory.")
        return self.store._git(cwd, *args, fixed_attributes=True, local_only=True, **options)

    def check_managed_environment(self) -> None:
        for name in ("hooks", "home"):
            path = self.store.root / name
            physical(path)
            if not path.is_dir() or any(path.iterdir()):
                _state("Integration requires empty managed hooks and home directories.")

    def _repo(self, target: Path) -> dict[str, Any]:
        root_identity = physical(target)
        if not target.is_dir() or _overlaps(target, self.store.root.parent):
            _state("The target and Core storage must be separate directories.")
        gitdir = self.store._ordinary_gitdir(target)
        git_identity = physical(gitdir)
        if "0" in (root_identity[1], git_identity[1]):
            _state("The target does not expose stable physical identities.")
        config_before = hashlib.sha256(_read_regular(gitdir / "config", MAX_OUTPUT)).hexdigest()
        _read_regular(gitdir / "HEAD", 4096)
        for name in (
            "info/attributes",
            "info/grafts",
            "shallow",
            "refs/replace",
            "index.lock",
            "index.sparse",
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
            "sequencer",
            "BISECT_START",
        ):
            if _exists(gitdir / name):
                _state(
                    "External attributes, replacement objects and in-progress Git operations are unsupported."
                )
        packs = gitdir / "objects" / "pack"
        if packs.is_dir() and any(path.suffix == ".promisor" for path in packs.iterdir()):
            _state("Promised objects and partial clones are unsupported.")
        config = self.store._source_config(target, config_file=gitdir / "config")
        if any(key not in _CONFIG and not _REMOTE_CONFIG.fullmatch(key) for key in config):
            _state("The target repository has unsupported local Git configuration.")
        if (
            config.get("core.bare", b"false") != b"false"
            or config.get("core.repositoryformatversion", b"0") not in (b"0", b"1")
            or config.get("extensions.objectformat", b"sha1") not in (b"sha1", b"sha256")
            or hashlib.sha256(_read_regular(gitdir / "config", MAX_OUTPUT)).hexdigest()
            != config_before
        ):
            _state("The target repository format or configuration changed.")
        _, top = self._git(target, "rev-parse", "--show-toplevel")
        if Path(top.decode("utf-8").removesuffix("\n")).resolve(strict=True) != target:
            _state("The target must be the original root of an ordinary Git repository.")
        return {
            "target_root": str(target),
            "target_root_identity": root_identity,
            "target_git_identity": git_identity,
            "target_config_sha256": config_before,
        }

    def _tree(self, repo: Path, commit: str) -> tuple[_Blob, ...]:
        _, data = self._git(repo, "ls-tree", "-r", "-l", "-z", valid_sha(commit))
        result = []
        seen: dict[str, str] = {}
        files = set()
        total = 0
        for entry in data.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, oid, size = metadata.split()
            if mode not in (b"100644", b"100755") or kind != b"blob":
                _state("Integration accepts regular files only, without symlinks or submodules.")
            path = self.store._names(raw_path + b"\0")[0]
            parts = path.split("/")
            if (
                len(parts) > 64
                or len(raw_path) > 4096
                or any(ord(char) == 127 or char in '<>"|?*' for char in path)
            ):
                _state("The Git tree has unsupported file paths.")
            for i in range(1, len(parts) + 1):
                name = "/".join(parts[:i])
                key = unicodedata.normalize("NFC", name).casefold()
                if seen.setdefault(key, name) != name or name in files:
                    _state("The Git tree has case or Unicode path aliases.")
            files.add(path)
            length = int(size)
            total += length
            if not 0 <= length <= MAX_REPOSITORY or total > MAX_REPOSITORY or len(files) > 100000:
                _state("The Git tree exceeds supported limits.")
            result.append(_Blob(path, valid_sha(oid.decode("ascii")), length, mode == b"100755"))
        return tuple(result)

    def _index(self, repo: Path, blobs: tuple[_Blob, ...]) -> None:
        _, raw = self._git(repo, "ls-files", "--stage", "-v", "-z")
        expected = sorted(
            f"H {100755 if item.executable else 100644} {item.sha} 0\t{item.path}".encode()
            for item in blobs
        )
        if sorted(raw.split(b"\0")[:-1]) != expected:
            _state("The index differs from HEAD or contains hidden entries.")

    def _attributes(self, repo: Path, blobs: tuple[_Blob, ...]) -> None:
        if not blobs:
            return
        names = b"\0".join(item.path.encode("utf-8") for item in blobs) + b"\0"
        _, raw = self._git(repo, "check-attr", "--cached", "-z", "--stdin", "--all", stdin=names)
        entries = raw.split(b"\0")[:-1]
        if len(entries) % 3:
            _state("Git returned invalid attribute information.")
        for _, key, value in zip(entries[::3], entries[1::3], entries[2::3], strict=True):
            if key not in _ATTRIBUTES or value == b"unset":
                continue
            if key in (b"filter", b"working-tree-encoding", b"ident"):
                _state("Filters, working-tree encoding and identifier expansion are unsupported.")
            if key == b"text" and value not in (b"set", b"auto"):
                _state("The Git text attribute is unsupported.")
            if key == b"eol" and value not in (b"lf", b"crlf"):
                _state("The Git line-ending attribute is unsupported.")
            if key == b"crlf" and value not in (b"set", b"input"):
                _state("The Git CRLF attribute is unsupported.")

    def _files(self, repo: Path, blobs: tuple[_Blob, ...], *, original: bool = False) -> str:
        expected = {item.path: item for item in blobs}
        seen = set()
        fingerprint = hashlib.sha256()
        entries = total = 0
        for root, dirs, names in os.walk(repo, followlinks=False, onerror=_walk_error):
            dirs.sort()
            names.sort()
            if Path(root) == repo and ".git" in dirs:
                dirs.remove(".git")
            if Path(root) == repo and ".git" in names:
                names.remove(".git")
            for name in dirs + names:
                path = Path(root) / name
                physical(path)
                relative = path.relative_to(repo).as_posix()
                entries += 1
                if entries > 100000:
                    _state("The checkout exceeds supported limits.")
                if name in dirs:
                    if not stat.S_ISDIR(path.lstat().st_mode):
                        _state("The checkout contains a non-directory path component.")
                    fingerprint.update(relative.encode("utf-8") + b"/\0")
                    continue
                item = expected.get(relative)
                if item is None:
                    _state("The checkout contains untracked or ignored files.")
                bound = min(2 * item.size, MAX_REPOSITORY - total)
                raw = _read_regular(path, bound)
                total += len(raw)
                if not self._match_blob(item, raw):
                    # Check exact possible normalization first. Git confirms that
                    # the pinned clean filter semantics actually permit the bytes.
                    if not original or not self._match_blob(item, raw.replace(b"\r\n", b"\n")):
                        _state("The checkout bytes differ from the expected Git blob.")
                    _, normalized = self._git(repo, "hash-object", "--", relative)
                    if normalized.decode("ascii").strip() != item.sha:
                        _state(
                            "The original checkout differs from its committed line-ending policy."
                        )
                if os.name != "nt" and bool(path.stat().st_mode & stat.S_IXUSR) != item.executable:
                    _state("Checkout executable bits differ from the expected Git tree.")
                fingerprint.update(relative.encode("utf-8") + b"\0" + hashlib.sha256(raw).digest())
                seen.add(relative)
        if seen != expected.keys():
            _state("The checkout is missing tracked files.")
        return fingerprint.hexdigest()

    @staticmethod
    def _match_blob(item: _Blob, data: bytes) -> bool:
        if len(data) != item.size:
            return False
        header = f"blob {item.size}\0".encode("ascii")
        algorithm = "sha1" if len(item.sha) == 40 else "sha256"
        hashed = hashlib.new(algorithm, header)
        hashed.update(data)
        return hashed.hexdigest() == item.sha

    def target(self, target: Path, base: str) -> dict[str, Any]:
        pin = self._repo(target)
        _, branch = self._git(target, "symbolic-ref", "--quiet", "HEAD")
        head = branch.decode("utf-8").removesuffix("\n")
        if not head.startswith("refs/heads/") or "\n" in head:
            _state("An attached local target branch is required.")
        _, actual = self._git(target, "rev-parse", "--verify", "HEAD^{commit}")
        if actual.decode("ascii").strip() != base:
            _state("The target HEAD differs from the verified candidate base.")
        blobs = self._tree(target, base)
        self._index(target, blobs)
        self._attributes(target, blobs)
        files = self._files(target, blobs, original=True)
        _, status = self._git(
            target,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        if status:
            _state("The target checkout must be clean.")
        index = _read_regular(target / ".git" / "index", MAX_REPOSITORY)
        if (
            physical(target) != pin["target_root_identity"]
            or physical(target / ".git") != pin["target_git_identity"]
        ):
            _state("The target repository changed during inspection.")
        return pin | {
            "target_head_ref": head,
            "target_index_sha256": hashlib.sha256(index).hexdigest(),
            "target_checkout_sha256": files,
            "base_sha": base,
        }

    def destination(self, target: Path, worktree: Path, branch: str) -> dict[str, Any]:
        if (
            not _BRANCH.fullmatch(branch)
            or branch.casefold().endswith((".", ".lock"))
            or ".." in branch
            or _DEVICE.match(branch)
        ):
            _state("Use a simple local destination branch name.")
        self._git(target, "check-ref-format", "refs/heads/" + branch)
        if _overlaps(worktree, target) or _overlaps(worktree, self.store.root.parent):
            _state("The new worktree must be separate from the target and Core storage.")
        for parent in (worktree.parent, *worktree.parent.parents):
            if _exists(parent / ".git"):
                _state("The new worktree must be outside existing checkouts.")
        if any(_normal_path(path) == _normal_path(worktree) for path in worktree.parent.iterdir()):
            _state("The destination worktree path already exists.")
        _, refs = self._git(target, "for-each-ref", "--format=%(refname)", "refs/heads/")
        ref = "refs/heads/" + branch
        for old in refs.decode("utf-8").splitlines():
            left, right = old.casefold(), ref.casefold()
            if left == right or left.startswith(right + "/") or right.startswith(left + "/"):
                _state("The destination branch already exists or conflicts with another ref.")
        if _exists(target / ".git" / ref):
            _state("The destination branch already exists.")
        parent_identity = physical(worktree.parent)
        if parent_identity[1] == "0":
            _state("The worktree parent does not expose a stable physical identity.")
        return {
            "destination_ref": ref,
            "worktree_path": str(worktree),
            "worktree_parent_identity": parent_identity,
        }

    def destination_state(self, target: Path, plan: dict[str, Any]) -> str:
        ref = plan["destination_ref"]
        _, raw = self._git(
            target, "for-each-ref", "--format=%(refname)%00%(objectname)%00%(symref)", "--", ref
        )
        expected = (ref + "\0" + plan["candidate_sha"] + "\0").encode("ascii")
        if raw.splitlines() == [expected]:
            return "exact"
        return "mismatch" if raw or _exists(target / ".git" / ref) else "absent"

    def candidate(self, repo: Path, exported: CandidateInput) -> tuple[_Blob, ...]:
        candidate, base = exported.snapshot.commit_sha, exported.binding.base_sha
        code, _ = self._git(
            repo,
            "merge-base",
            "--is-ancestor",
            valid_sha(base),
            valid_sha(candidate),
            accepted=(0, 1),
        )
        if code or candidate == base:
            _state("The verified candidate must descend from the target base.")
        blobs = self._tree(repo, candidate)
        if sorted((item.path, item.sha, item.size) for item in blobs) != sorted(
            exported.snapshot.manifest
        ):
            _state("The candidate tree differs from the verified manifest.")
        self._index(repo, blobs)
        self._attributes(repo, blobs)
        return blobs

    def stage_bundle(
        self, comparison: Path, target: Path, bundle: Path, plan: dict[str, Any]
    ) -> str:
        candidate = valid_sha(plan["candidate_sha"])
        base = valid_sha(plan["base_sha"])
        self._git(
            comparison, "bundle", "create", str(bundle), "HEAD", "^" + base, bounded_file=bundle
        )
        pin = bundle_pin(bundle)
        _, listed = self._git(comparison, "bundle", "list-heads", str(bundle))
        if listed.splitlines() != [f"{candidate} HEAD".encode("ascii")]:
            _state("The private candidate bundle does not bind the approved commit.")
        self._git(target, "bundle", "verify", str(bundle))
        if bundle_pin(bundle) != pin:
            _state("The private candidate bundle changed during inspection.")
        return pin

    def import_objects(self, target: Path, bundle: Path, pin: str, plan: dict[str, Any]) -> None:
        if bundle_pin(bundle) != pin:
            _state("The private candidate bundle changed before import.")
        self._git(target, "bundle", "unbundle", str(bundle))
        if bundle_pin(bundle) != pin:
            _state("The private candidate bundle changed during import.")
        sha = valid_sha(plan["candidate_sha"])
        _, tree = self._git(target, "rev-parse", "--verify", sha + "^{tree}")
        if tree.decode("ascii").strip() != plan["tree_sha"]:
            _state("The imported candidate does not have the approved tree.")

    def create_branch(self, target: Path, plan: dict[str, Any]) -> None:
        sha = valid_sha(plan["candidate_sha"])
        self._git(target, "update-ref", "--no-deref", plan["destination_ref"], sha, "0" * len(sha))

    def write_worktree(
        self, target: Path, worktree: Path, plan: dict[str, Any], blobs: tuple[_Blob, ...]
    ) -> None:
        ref = plan["destination_ref"]
        candidate = valid_sha(plan["candidate_sha"])
        # --no-checkout creates a fresh linked index without applying attributes.
        worktree.mkdir()
        created = physical(worktree)
        self._git(
            target,
            "worktree",
            "add",
            "--no-checkout",
            str(worktree),
            ref.removeprefix("refs/heads/"),
        )
        if physical(worktree) != created:
            _state("The created worktree changed identity.")
        _linked_directory(self.store, worktree, target / ".git")
        self._git(worktree, "read-tree", candidate)
        for item in blobs:
            path = worktree / item.path
            path.parent.mkdir(parents=True, exist_ok=True)
            physical(path.parent)
            _, data = self._git(target, "cat-file", "blob", item.sha)
            if not self._match_blob(item, data):
                _state("The imported candidate blob differs from the verified input.")
            with path.open("xb") as output:
                output.write(data)
                output.flush()
                if item.executable and os.name != "nt":
                    path.chmod(0o755)
                os.fsync(output.fileno())

    def verify_worktree(self, target: Path, worktree: Path, plan: dict[str, Any]) -> list[str]:
        identity = physical(worktree)
        if identity[1] == "0":
            _state("The worktree does not expose a stable physical identity.")
        _linked_directory(self.store, worktree, target / ".git")
        _, ref = self._git(worktree, "symbolic-ref", "--quiet", "HEAD")
        _, commit = self._git(worktree, "rev-parse", "--verify", "HEAD^{commit}")
        _, tree = self._git(worktree, "rev-parse", "--verify", "HEAD^{tree}")
        if (
            ref.decode("ascii").strip(),
            commit.decode("ascii").strip(),
            tree.decode("ascii").strip(),
        ) != (
            plan["destination_ref"],
            plan["candidate_sha"],
            plan["tree_sha"],
        ):
            _state("The linked worktree does not match the approved branch, commit and tree.")
        blobs = self._tree(worktree, plan["candidate_sha"])
        self._index(worktree, blobs)
        self._attributes(worktree, blobs)
        self._files(worktree, blobs)
        _, status = self._git(
            worktree,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--ignore-submodules=none",
        )
        if status:
            _state("The linked worktree is not clean under its Git configuration.")
        if physical(worktree) != identity:
            _state("The linked worktree identity changed.")
        return identity

"""Trusted owner staging primitives; never write to an existing actor worktree."""

from __future__ import annotations

import stat
import unicodedata
from pathlib import Path
from typing import Any

from agentsync.workspaces.git import GitWorkspaceStore, fail, physical, valid_sha


def tree_modes(store: GitWorkspaceStore, repo: Path, head: str) -> dict[str, str]:
    store._tree(repo, head)
    _, raw = store._git(repo, "ls-tree", "-r", "-z", valid_sha(head))
    result = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, _, _ = metadata.decode("ascii").split()
        path = name.decode("utf-8")
        if any(part.casefold() in {".gitattributes", ".gitmodules"} for part in path.split("/")):
            fail("unsupported", "Proposal staging does not support Git attribute/module files.")
        result[path] = mode
    return result


def check_paths(modes: dict[str, str], files: list[dict[str, str]]) -> None:
    names = set(modes) | {item["path"] for item in files}
    seen: dict[str, str] = {}
    for name in sorted(names):
        parts = name.split("/")
        for length in range(1, len(parts) + 1):
            prefix = "/".join(parts[:length])
            folded = unicodedata.normalize("NFC", prefix).casefold()
            if parts[length - 1].casefold() in {".gitattributes", ".gitmodules"}:
                fail("unsupported", "Proposal staging does not support Git attribute/module files.")
            if (folded in seen and seen[folded] != prefix) or (
                length < len(parts) and prefix in names
            ):
                fail(
                    "proposal_path_conflict", "Proposal paths conflict with the existing Git tree."
                )
            seen[folded] = prefix


def stage_worktree(
    store: GitWorkspaceStore,
    snapshot: dict[str, Any],
    original: dict[str, Any],
    files: list[dict[str, str]],
    head: str,
    identity: str,
) -> tuple[dict[str, Any], str]:
    """Called only after a durable owner intent and current-boundary validation.

    The ordinary create receipt continues to identify the snapshot baseline. The
    staged commit is a real descendant, checked through ordinary workspace APIs.
    Failures retain the newly owned worktree; this function does not retry/clean.
    """
    repo = Path(snapshot["repository_path"])
    modes = tree_modes(store, repo, head)
    check_paths(modes, files)
    path = store._path("worktrees", identity)
    if path.exists() or path.is_symlink():
        fail("proposal_staging_exists", "The dedicated staging destination already exists.")
    created = store.create_worktree(snapshot, identity, task_id=original["task_id"])
    if head != snapshot["base_sha"]:
        # This destination was exclusively created by this attempt, never a user
        # or producer worktree. Attributes/configuration were checked beforehand.
        store._git(path, "reset", "--hard", valid_sha(head))
    for item in files:
        target = path.joinpath(*item["path"].split("/"))
        parent = path
        for part in item["path"].split("/")[:-1]:
            parent /= part
            if not parent.exists():
                parent.mkdir()
            physical(parent)
            if not parent.is_dir():
                fail("workspace_boundary", "Staging parent is not a directory.")
        try:
            info = target.lstat()
        except FileNotFoundError:
            mode = "xb"
        else:
            physical(target)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                fail("workspace_boundary", "Staging target is not a private regular file.")
            mode = "wb"
        with target.open(mode) as stream:
            stream.write(item["content"].encode("utf-8"))
        physical(target)
        _, raw_oid = store._git(repo, "hash-object", "--no-filters", "-w", "--", str(target))
        oid = valid_sha(raw_oid.decode("ascii").strip())
        store._git(
            path,
            "update-index",
            "--add",
            "--cacheinfo",
            f"{modes.get(item['path'], '100644')},{oid},{item['path']}",
        )
    _, tree_raw = store._git(path, "write-tree")
    tree = valid_sha(tree_raw.decode("ascii").strip())
    _, commit_raw = store._git(
        repo, "commit-tree", tree, "-p", head, "-m", "Owner-approved inert proposal staging"
    )
    staged = valid_sha(commit_raw.decode("ascii").strip())
    store._git(path, "update-ref", "--no-deref", "HEAD", staged, head)
    actual = store.inspect_worktree(created)
    if actual["dirty"] or actual["head_sha"] != staged:
        fail("workspace_boundary", "Staged worktree differs from its committed proposal.")
    for item in files:
        target = path.joinpath(*item["path"].split("/"))
        physical(target)
        _, blob = store._git(repo, "show", staged + ":" + item["path"])
        if blob != item["content"].encode("utf-8") or target.read_bytes() != blob:
            fail("workspace_boundary", "Staged content differs from the reviewed bytes.")
    return created, staged

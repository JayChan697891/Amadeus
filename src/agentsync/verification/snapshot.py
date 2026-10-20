"""Read bounded immutable Git objects without checking out or importing candidate code."""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentsync.workspaces.git import (
    MAX_REPOSITORY,
    GitWorkspaceStore,
    fail,
    physical,
    valid_sha,
)

MAX_FILES = 256
MAX_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024


@dataclass(frozen=True)
class CandidateSnapshot:
    """Content-only input; paths and mutable worktree state are deliberately absent."""

    commit_sha: str
    tree_sha: str
    source: bytes
    manifest: tuple[tuple[str, str, int], ...]
    input_sha256: str


def _repository(store: GitWorkspaceStore, receipt: dict[str, Any]) -> Path:
    """Only trusted service receipts are supported, never caller-selected host paths."""
    if receipt.get("operation") == "capture":
        snapshot = receipt
    elif receipt.get("operation") == "create":
        snapshot = {
            "id": receipt["snapshot_id"],
            "base_sha": receipt["base_sha"],
            "repository_path": receipt["repository_path"],
            "root_identity": receipt["repository_identity"],
            "config_sha256": receipt["config_sha256"],
        }
    else:
        fail("verification_input_invalid", "A trusted managed repository receipt is required.")
    repo = store._path("repositories", snapshot["id"])
    if (
        physical(store.root) != store.root_identity
        or str(repo) != snapshot["repository_path"]
        or physical(repo) != snapshot["root_identity"]
    ):
        fail("workspace_boundary", "Managed repository identity changed.")
    # Objects must be local physical files, including packed objects and metadata.
    # Checking only the repository directory would permit a replaced objects child.
    total = entries = 0
    for directory, dirs, files in os.walk(repo, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(directory) / name
            physical(path)
            entries += 1
            total += path.stat().st_size
            if entries > 100000 or total > MAX_REPOSITORY:
                fail("repository_too_large", "Managed metadata exceeds supported limits.")
    for name in ("objects/info/alternates", "objects/info/http-alternates", "commondir"):
        if (repo / name).exists():
            fail("workspace_boundary", "External object stores are forbidden.")
    store.verify_snapshot(snapshot)
    return repo


def _git(store: GitWorkspaceStore, repo: Path, *args: str) -> bytes:
    _, result = store._git(repo, *args)
    # The store bounds real subprocess output; also keep this boundary explicit.
    if len(result) > MAX_BYTES:
        fail("verification_input_invalid", "Git output exceeds the verification limit.")
    return result


def _object(store: GitWorkspaceStore, repo: Path, kind: str, oid: str) -> bytes:
    content = _git(store, repo, "cat-file", kind, oid)
    algorithm = "sha1" if len(oid) == 40 else "sha256"
    framed = kind.encode("ascii") + b" " + str(len(content)).encode("ascii") + b"\0" + content
    if hashlib.new(algorithm, framed).hexdigest() != oid:
        fail("verification_input_invalid", "Candidate object integrity verification failed.")
    return content


def export_candidate(
    store: GitWorkspaceStore, repository_receipt: dict[str, Any], candidate_sha: str
) -> CandidateSnapshot:
    """Export root solution.py from a pinned managed commit, ignoring archive attributes.

    The receipt is an internal trusted-service value. This function is not a Core
    operation or a boundary that authenticates arbitrary agent-submitted dictionaries.
    All other tree entries are validated and hashed but are never executed or exported.
    """
    commit_sha = valid_sha(candidate_sha)
    repo = _repository(store, repository_receipt)
    kind = _git(store, repo, "cat-file", "-t", commit_sha)
    if kind != b"commit\n":
        fail("verification_input_invalid", "Candidate must identify a commit object directly.")
    commit = _object(store, repo, "commit", commit_sha)
    try:
        first_line = commit.split(b"\n", 1)[0]
        if not first_line.startswith(b"tree "):
            fail("verification_input_invalid", "Candidate commit lacks its root tree binding.")
        tree_sha = valid_sha(first_line[5:].decode("ascii"))
    except UnicodeError:
        fail("verification_input_invalid", "Candidate commit tree binding is invalid.")
    _object(store, repo, "tree", tree_sha)
    listing = _git(store, repo, "ls-tree", "-r", "-t", "-l", "-z", tree_sha)
    manifest: list[tuple[str, str, int]] = []
    seen: dict[str, str] = {}
    paths: set[str] = set()
    total = entries = 0
    trees: list[str] = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, object_type, raw_sha, raw_size = metadata.split()
            blob_sha = valid_sha(raw_sha.decode("ascii"))
            size = int(raw_size) if raw_size != b"-" else 0
        except (ValueError, UnicodeError):
            fail("verification_input_invalid", "Candidate tree metadata is invalid.")
        is_tree = mode == b"040000" and object_type == b"tree"
        if not is_tree and (
            mode not in {b"100644", b"100755"} or object_type != b"blob" or size < 0
        ):
            fail("verification_input_invalid", "Only regular files and directories are supported.")
        if not raw_path:
            fail("verification_input_invalid", "Empty Git tree names are forbidden.")
        path = store._names(raw_path + b"\0")[0]
        if path in paths:
            fail("verification_input_invalid", "Duplicate Git tree entries are forbidden.")
        paths.add(path)
        # Detect aliases in directory components as well as complete leaf paths.
        components = path.split("/")
        for index in range(1, len(components) + 1):
            prefix = "/".join(components[:index])
            folded = unicodedata.normalize("NFC", prefix).casefold()
            if folded in seen and seen[folded] != prefix:
                fail("verification_input_invalid", "Case or Unicode path aliases are forbidden.")
            seen[folded] = prefix
        if any(ord(char) == 127 for char in path):
            fail("verification_input_invalid", "Control characters in paths are forbidden.")
        entries += 1
        if entries > MAX_FILES * 2 or len(components) > 64 or len(raw_path) > 4096:
            fail(
                "verification_input_invalid", "Candidate tree metadata exceeds verification limits."
            )
        if is_tree:
            trees.append(blob_sha)
            continue
        total += size
        manifest.append((path, blob_sha, size))
        if len(manifest) > MAX_FILES or total > MAX_BYTES:
            fail("verification_input_invalid", "Candidate tree exceeds verification limits.")
    manifest.sort(key=lambda entry: entry[0].encode("utf-8"))
    sources = [entry for entry in manifest if entry[0] == "solution.py"]
    if len(sources) != 1 or sources[0][2] > MAX_SOURCE_BYTES:
        fail("verification_input_invalid", "A bounded root solution.py is required.")
    for oid in trees:
        _object(store, repo, "tree", oid)
    source = b""
    for path, blob_sha, size in manifest:
        content = _object(store, repo, "blob", blob_sha)
        if len(content) != size:
            fail("verification_input_invalid", "Candidate blob integrity verification failed.")
        if path == "solution.py":
            source = content
    try:
        source.decode("utf-8", errors="strict")
    except UnicodeError:
        fail("verification_input_invalid", "The root solution must contain UTF-8 source bytes.")
    # Bind the profile input to both immutable Git IDs and the exact executed bytes.
    canonical = json.dumps(
        {
            "format": "agentsync-candidate-v1",
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "manifest": manifest,
            "source_sha256": hashlib.sha256(source).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    # Recheck trusted storage after potentially slow object reads.
    _repository(store, repository_receipt)
    return CandidateSnapshot(
        commit_sha, tree_sha, source, tuple(manifest), hashlib.sha256(canonical).hexdigest()
    )

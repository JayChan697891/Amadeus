"""Bind saved source hashes to local Git objects without fetching or checking out."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path, PurePosixPath
from threading import Timer
from typing import Any

_OID = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TREE_BYTES = 16 * 1024 * 1024
_MAX_BLOB = 1024 * 1024 * 1024


@contextmanager
def _git(repo: Path, *args: str, input_pipe: bool = False) -> Iterator[subprocess.Popen[bytes]]:
    environment = {name: value for name, value in os.environ.items() if not name.upper().startswith("GIT_")}
    environment.update(
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1",
        GIT_ALLOW_PROTOCOL="", GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
    )
    process = subprocess.Popen(
        ["git", "-C", str(repo), *args],
        env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.PIPE if input_pipe else subprocess.DEVNULL,
    )

    def stop() -> None:
        if process.poll() is None:
            with suppress(OSError):
                process.kill()

    timer = Timer(120, stop)
    timer.daemon = True
    timer.start()
    try:
        yield process
        if process.wait() != 0:
            raise ValueError("Local Git source objects are unavailable.")
    finally:
        timer.cancel()
        stop()
        process.wait()
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def _output(repo: Path, *args: str, maximum: int) -> bytes:
    with _git(repo, *args) as process:
        assert process.stdout is not None
        output = process.stdout.read(maximum + 1)
        if len(output) > maximum:
            raise ValueError("Git source metadata exceeds its limit.")
        return output


def _excluded(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.name.startswith(".env") or path.suffix.lower() in {".pem", ".key"}
        or path.name.lower() in {"auth.json", "credentials.json", "secrets.json"}
    )


def _tree_entries(repo: Path, commit: str) -> dict[str, str]:
    data = _output(repo, "ls-tree", "-r", "-z", "--full-tree", commit, maximum=_TREE_BYTES)
    result: dict[str, str] = {}
    for record in data.split(b"\0"):
        if not record:
            continue
        fields, raw_name = record.split(b"\t", 1)
        mode, kind, raw_oid = fields.split()
        name = raw_name.decode("utf-8")
        if mode == b"120000" or _excluded(name):
            continue
        oid = raw_oid.decode("ascii")
        if (
            mode not in (b"100644", b"100755") or kind != b"blob"
            or not _OID.fullmatch(oid) or name in result or len(result) >= 20000
        ):
            raise ValueError("Git source includes an unsupported tree member.")
        result[name] = oid
    return result


def verify_git_source(repo: Path, commit: str, tree: str, snapshot: list[dict[str, Any]]) -> dict[str, Any]:
    """Match all included paths, sizes and SHA-256 values against committed blobs."""
    if not _OID.fullmatch(commit) or not _OID.fullmatch(tree):
        raise ValueError("Invalid frozen Git source identity.")
    repo = repo.resolve(strict=True)
    if _output(repo, "cat-file", "-t", commit, maximum=128).strip() != b"commit":
        raise ValueError("The frozen source object is not a Git commit.")
    actual_tree = _output(repo, "rev-parse", "--verify", commit + "^{tree}", maximum=128)
    if actual_tree.decode("ascii").strip() != tree:
        raise ValueError("Report tree does not match its Git commit.")
    expected = {row["path"]: (row["size"], row["sha256"]) for row in snapshot}
    objects = _tree_entries(repo, commit)
    if len(expected) != len(snapshot) or expected.keys() != objects.keys():
        raise ValueError("Source snapshot paths differ from the frozen Git tree.")
    unique: dict[str, tuple[int, str]] = {}
    for name, oid in objects.items():
        size, digest = expected[name]
        if type(size) is not int or not 0 <= size <= _MAX_BLOB or not _SHA256.fullmatch(digest):
            raise ValueError("Invalid frozen source byte pin.")
        if oid in unique and unique[oid] != (size, digest):
            raise ValueError("One Git object has conflicting source byte pins.")
        unique[oid] = (size, digest)
    if sum(size for size, _ in unique.values()) > 4 * _MAX_BLOB:
        raise ValueError("Git source bytes exceed their total verification limit.")
    with _git(repo, "cat-file", "--batch", input_pipe=True) as process:
        assert process.stdin is not None and process.stdout is not None
        for oid, (size, digest) in unique.items():
            process.stdin.write(oid.encode("ascii") + b"\n")
            process.stdin.flush()
            header = process.stdout.readline(256)
            if header != f"{oid} blob {size}\n".encode("ascii"):
                raise ValueError("Git object type or size does not match the source snapshot.")
            checksum = hashlib.sha256()
            object_hash = hashlib.sha1(f"blob {size}\0".encode("ascii"), usedforsecurity=False)
            remaining = size
            while remaining:
                data = process.stdout.read(min(remaining, 1024 * 1024))
                if not data:
                    raise ValueError("Git source object ended prematurely.")
                remaining -= len(data)
                checksum.update(data)
                object_hash.update(data)
            if process.stdout.read(1) != b"\n" or checksum.hexdigest() != digest or object_hash.hexdigest() != oid:
                raise ValueError("Git object bytes differ from the recorded source.")
        process.stdin.close()
        if process.stdout.read(1):
            raise ValueError("Unexpected output followed the Git source objects.")
    return {"tree_sha": tree, "git_source_paths": len(objects), "unique_git_blobs": len(unique)}

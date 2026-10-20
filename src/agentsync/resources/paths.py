"""Validate pinned roots and inspect bounded files without modifying user data.

Repeated checks detect common replacements; they do not promise confinement against
malicious processes racing directory replacements between checks.
"""

import hashlib
import os
import re
import sqlite3
import stat
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, NoReturn

from agentsync.errors import AgentSyncError

MAX_FILE_SIZE = 16 * 1024 * 1024
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedResource:
    absolute: Path
    relative: str
    key: str
    kind: Literal["file", "directory", "missing"]
    exists: bool


def _reject(message: str, code: str = "invalid_path") -> NoReturn:
    raise AgentSyncError(code, message)


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _checked_stat(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        _reject("Resource could not be inspected.", "path_boundary")
    if _is_link(info):
        _reject("Links and reparse points are not supported.", "path_boundary")
    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
        _reject("Multiply linked files are not supported.", "path_boundary")
    return info


def _root_stat(root: Path) -> os.stat_result:
    if not root.is_absolute():
        _reject("Project root must be absolute.", "path_boundary")
    # Inspect the full ancestor chain so a newly introduced junction is rejected.
    for ancestor in (*reversed(root.parents), root):
        info = _checked_stat(ancestor)
        if not stat.S_ISDIR(info.st_mode):
            _reject("Project root ancestor is not a directory.", "path_boundary")
    return info


def pin_root(db: sqlite3.Connection, project_id: str, root: Path) -> None:
    info = _root_stat(root)
    try:
        canonical = str(root.resolve(strict=True))
    except (OSError, RuntimeError):
        _reject("Project root identity could not be resolved.", "path_boundary")
    old = db.execute(
        "SELECT root_path,device,inode FROM project_resource_roots WHERE project_id=?",
        (project_id,),
    ).fetchone()
    fingerprint = (canonical, str(info.st_dev), str(info.st_ino))
    if old is None:
        db.execute("INSERT INTO project_resource_roots VALUES(?,?,?,?)", (project_id, *fingerprint))
    elif tuple(old) != fingerprint:
        _reject("The pinned project root was replaced or moved.", "path_boundary")


def _root(db: sqlite3.Connection, project_id: str) -> Path:
    project = db.execute("SELECT root_path FROM projects WHERE id=?", (project_id,)).fetchone()
    if project is None:
        raise AgentSyncError("not_found", "Project not found.", 404)
    root = Path(project["root_path"])
    pin_root(db, project_id, root)
    return root


def _relative_parts(value: str) -> list[str]:
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _reject("A nonempty relative path without control characters is required.")
    windows = PureWindowsPath(value)
    if windows.drive or windows.root or value.startswith(("/", "\\")) or ":" in value:
        _reject("Absolute, device, drive and alternate-stream paths are forbidden.")
    if value == ".":
        return []
    parts = value.replace("\\", "/").split("/")
    for part in parts:
        if (
            part in {"", ".", ".."}
            or part.endswith((".", " "))
            or part.casefold() == ".git"
            or _RESERVED.match(part)
        ):
            _reject("Path contains a forbidden component.")
    return parts


def resolve_resource(db: sqlite3.Connection, project_id: str, path: str) -> ResolvedResource:
    parts = _relative_parts(path)
    root = _root(db, project_id)
    current = root
    exists = True
    info = _checked_stat(root)
    for index, part in enumerate(parts):
        current = current / part
        if not exists:
            continue
        try:
            info = current.lstat()
        except FileNotFoundError:
            exists = False
            continue
        except OSError:
            _reject("Resource could not be inspected.", "path_boundary")
        if _is_link(info):
            _reject("Links and reparse points are not supported.", "path_boundary")
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            _reject("Multiply linked files are not supported.", "path_boundary")
        if stat.S_ISDIR(info.st_mode):
            marker = current / ".git"
            try:
                marker.lstat()
            except FileNotFoundError:
                pass
            except OSError:
                _reject("Nested repository boundary could not be inspected.", "path_boundary")
            else:
                _reject("Nested repositories are not supported.", "path_boundary")
        elif index != len(parts) - 1:
            _reject("Resource parent is not a directory.", "path_boundary")
    kind: Literal["file", "directory", "missing"] = "missing"
    if exists:
        if stat.S_ISREG(info.st_mode):
            kind = "file"
        elif stat.S_ISDIR(info.st_mode):
            kind = "directory"
        else:
            _reject("Only ordinary files and directories are supported.", "unsupported_resource")
    try:
        # Resolve filesystem aliases (including Windows short names) for conflict
        # identity, after rejecting links; retain original case for actual IO.
        key = current.resolve(strict=False).as_posix()
    except (OSError, RuntimeError):
        _reject("Resource identity could not be resolved.", "path_boundary")
    if sys.platform == "darwin":
        # Some macOS filesystems alias composed/decomposed Unicode names.
        # Conservative collisions are preferable to bypassing a shared lease.
        key = unicodedata.normalize("NFC", key).casefold()
    elif sys.platform == "win32":
        key = key.casefold()
    return ResolvedResource(current, "/".join(parts) or ".", key, kind, exists)


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inspect_resource(db: sqlite3.Connection, project_id: str, path: str) -> dict[str, Any]:
    resource = resolve_resource(db, project_id, path)
    result: dict[str, Any] = {
        "path": resource.relative,
        "exists": resource.exists,
        "kind": resource.kind,
        "sha256": None,
        "size": None,
    }
    if resource.kind != "file":
        return result
    before = _checked_stat(resource.absolute)
    if before.st_size > MAX_FILE_SIZE:
        _reject("File exceeds the 16 MiB inspection limit.", "resource_too_large")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resource.absolute, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            # Windows Python versions can expose creation time via lstat's
            # deprecated ctime but change time via fstat. Compare ctime only
            # between observations from the same API, retaining both checks.
            if (
                _identity(opened)[:4] != _identity(before)[:4]
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink > 1
            ):
                _reject("Resource changed while being inspected.", "unstable_resource")
            hashed = hashlib.sha256()
            total = 0
            while chunk := stream.read(min(65536, MAX_FILE_SIZE + 1 - total)):
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    _reject("Resource grew while being inspected.", "unstable_resource")
                hashed.update(chunk)
            after = os.fstat(stream.fileno())
        checked = resolve_resource(db, project_id, path)
        final = _checked_stat(checked.absolute)
        if (
            checked != resource
            or _identity(opened) != _identity(after)
            or _identity(before) != _identity(final)
            or total != before.st_size
        ):
            _reject("Resource changed while being inspected.", "unstable_resource")
    except OSError:
        _reject("Resource changed or could not be read.", "unstable_resource")
    result.update(sha256=hashed.hexdigest(), size=total)
    return result

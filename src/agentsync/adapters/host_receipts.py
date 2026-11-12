"""Private receipts for explicitly approved host launches and controlled relays."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, NoReturn

from agentsync.errors import AgentSyncError
from agentsync.workspaces.git import physical

_LIMIT = 4096


def _unavailable() -> AgentSyncError:
    return AgentSyncError(
        "receipt_unavailable", "The private receipt directory is unavailable.", 409
    )


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate receipt field.")
        value[key] = item
    return value


def _invalid_constant(_name: str) -> NoReturn:
    raise ValueError("Invalid receipt number.")


def _file_stamp(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _ordinary(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and not getattr(info, "st_file_attributes", 0) & 0x400
        and info.st_nlink == 1
    )


def _exclusive_receipt_fd(path: str, flags: int) -> int:
    """Create the fence once and request write-through for Windows metadata."""
    if sys.platform != "win32":
        return os.open(path, flags, 0o600)

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    generic_write = 0x40000000
    share_read_write = 0x00000003
    create_new = 1
    write_through = 0x80000000
    handle = create_file(
        path, generic_write, share_read_write, None, create_new, write_through, None
    )
    if handle is None or handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    close_handle = kernel.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    try:
        return msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        close_handle(handle)
        raise


class _ReceiptDirectory:
    """Check the pinned local directory before treating a receipt as present or absent."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise _unavailable()
        self.root = root
        self._identity = self._physical()
        if not root.is_dir():
            raise _unavailable()

    def _physical(self) -> list[str]:
        try:
            return physical(self.root)
        except AgentSyncError:
            raise _unavailable() from None

    def check(self) -> None:
        if self._physical() != self._identity or not self.root.is_dir():
            raise _unavailable()

    def location_pin(self) -> str:
        """Return a host-local identity for a separate trusted anchor, not a movable path."""
        self.check()
        if self._identity[1] == "0":
            raise _unavailable()
        normalized = os.path.normcase(str(self.root))
        data = json.dumps([normalized, *self._identity], ensure_ascii=True).encode("ascii")
        return hashlib.sha256(data).hexdigest()

    def _path(self, name: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,179}\.json", name):
            raise _unavailable()
        self.check()
        return self.root / name

    def _sync_directory_entry(self) -> None:
        # A POSIX file fsync alone does not persist the name used as the replay fence.
        if os.name != "posix":
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.root, flags)
        try:
            directory = os.fstat(descriptor)
            identity = [str(directory.st_dev), str(directory.st_ino)]
            if not stat.S_ISDIR(directory.st_mode) or identity != self._identity:
                raise _unavailable()
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def write(self, name: str, data: dict[str, object]) -> None:
        """An exclusive write remains a fence even if interrupted."""
        path = self._path(name)
        try:
            with open(
                path, "x", encoding="ascii", newline="\n", opener=_exclusive_receipt_fd
            ) as stream:
                self.check()
                json.dump(data, stream, ensure_ascii=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
                self._sync_directory_entry()
                current = path.lstat()
                opened = os.fstat(stream.fileno())
                if not _ordinary(current) or _file_stamp(opened)[:2] != _file_stamp(current)[:2]:
                    raise _unavailable()
                self.check()
        except FileExistsError:
            self.check()
            raise AgentSyncError(
                "attempt_already_reserved", "An attempt is already reserved.", 409
            ) from None
        except OSError:
            raise _unavailable() from None

    def read(self, name: str, *, durable: bool = False) -> dict[str, Any] | None:
        """None denotes absence; corrupt or unreadable entries remain fences."""
        path = self._path(name)
        try:
            info = path.lstat()
        except FileNotFoundError:
            self.check()
            return None
        except OSError:
            self.check()
            return {}
        try:
            if not _ordinary(info) or not 1 <= info.st_size <= _LIMIT:
                return {}
            with path.open("r+b" if durable else "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not _ordinary(opened) or _file_stamp(opened) != _file_stamp(info):
                    return {}
                self.check()
                raw = stream.read(_LIMIT + 1)
                if len(raw) != info.st_size or _file_stamp(path.lstat()) != _file_stamp(info):
                    return {}
                if durable:
                    os.fsync(stream.fileno())
                    self._sync_directory_entry()
                    if _file_stamp(path.lstat()) != _file_stamp(info):
                        return {}
            value = json.loads(raw, object_pairs_hook=_members, parse_constant=_invalid_constant)
            return value if type(value) is dict else {}
        except (OSError, ValueError, RecursionError):
            return {}
        finally:
            self.check()

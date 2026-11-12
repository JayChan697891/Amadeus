"""Explicit file storage for an owner's private usage checkpoint.

Use an owner-controlled directory and a single writer per checkpoint. A save
flushes a temporary file in the same directory before replacing the destination.
On POSIX a save also requests a directory flush after replacement. Storage
durability depends on the filesystem and hardware. Checkpoints are observations
and cannot recover active Agent runs.
"""

import os
import stat
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from agentsync.errors import AgentSyncError
from agentsync.model_usage import ModelCallMeter, ModelUsageSummary
from agentsync.model_usage_checkpoint import (
    MODEL_CHECKPOINT_LIMIT,
    dump_model_usage,
    load_model_usage,
)
from agentsync.usage import _JSON_LIMIT, UsageLedger
from agentsync.workspaces.git import physical


def _checkpoint_path(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or not path.name:
        raise AgentSyncError("validation_error", "An absolute usage checkpoint path is required.")


def _file_stamp(info: os.stat_result) -> tuple[int, int, int, int]:
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ):
        raise OSError("A regular checkpoint file is required.")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _existing_stamp(path: Path) -> tuple[int, int, int, int] | None:
    try:
        return _file_stamp(path.lstat())
    except FileNotFoundError:
        return None


def save_usage_checkpoint(path: Path, ledger: UsageLedger) -> None:
    """Replace one explicit checkpoint after the complete document is flushed."""
    _checkpoint_path(path)
    if type(ledger) is not UsageLedger:
        raise AgentSyncError("validation_error", "A usage ledger is required.")
    _save(path, ledger.to_json().encode("utf-8"))


def _save(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    parent: list[str] | None = None
    descriptor: int | None = None
    try:
        parent = physical(path.parent)
        before = _existing_stamp(path)
        if os.name == "posix":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path.parent, flags)
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) or [str(info.st_dev), str(info.st_ino)] != parent:
                raise OSError("Checkpoint directory changed.")
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".agentsync-", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if physical(path.parent) != parent or _existing_stamp(path) != before:
            raise OSError("Checkpoint location changed.")
        temporary.replace(path)
        temporary = None
        if descriptor is not None:
            os.fsync(descriptor)
    except (AgentSyncError, OSError, ValueError):
        raise AgentSyncError(
            "checkpoint_unavailable", "Could not confirm the usage checkpoint was saved."
        ) from None
    finally:
        if temporary is not None:
            with suppress(AgentSyncError, OSError):
                if physical(path.parent) == parent:
                    temporary.unlink(missing_ok=True)
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)


def load_usage_checkpoint(path: Path, project_id: str) -> UsageLedger:
    """Load an explicit checkpoint and validate it against the expected project."""
    return UsageLedger.from_json(project_id, _read(path, _JSON_LIMIT))


def save_model_usage_checkpoint(path: Path, project_id: str, meter: ModelCallMeter) -> None:
    """Save a model usage observation in an explicit owner-controlled location."""
    _checkpoint_path(path)
    _save(path, dump_model_usage(project_id, meter).encode("ascii"))


def load_model_usage_checkpoint(path: Path, project_id: str) -> ModelUsageSummary:
    """Read model usage counts, without restoring an active model meter."""
    return load_model_usage(project_id, _read(path, MODEL_CHECKPOINT_LIMIT))


def _read(path: Path, limit: int) -> str:
    _checkpoint_path(path)
    try:
        parent = physical(path.parent)
        before = _file_stamp(path.lstat())
        flags = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with open(path, "rb", opener=lambda name, mode: os.open(name, mode | flags)) as file:
            if _file_stamp(os.fstat(file.fileno())) != before:
                raise OSError("Checkpoint file changed.")
            data = file.read(limit + 1)
            if _file_stamp(os.fstat(file.fileno())) != before:
                raise OSError("Checkpoint file changed.")
        if physical(path.parent) != parent or _existing_stamp(path) != before:
            raise OSError("Checkpoint location changed.")
    except (AgentSyncError, OSError, ValueError):
        raise AgentSyncError(
            "checkpoint_unavailable", "Could not read the usage checkpoint."
        ) from None
    if len(data) > limit:
        raise AgentSyncError("validation_error", "Invalid usage checkpoint content.")
    try:
        return data.decode("utf-8")
    except UnicodeError:
        raise AgentSyncError("validation_error", "Invalid usage checkpoint content.") from None

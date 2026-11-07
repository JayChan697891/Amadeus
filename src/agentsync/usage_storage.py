"""Explicit file storage for an owner's private usage checkpoint.

Use an owner-controlled directory and a single writer per checkpoint. A save
flushes a temporary file in the same directory before replacing the destination.
Atomic replacement protects readers from partial writes on supported local file
systems. This does not guarantee power-loss durability or recover Agent runs.
"""

import os
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile

from agentsync.errors import AgentSyncError
from agentsync.usage import _JSON_LIMIT, UsageLedger


def _checkpoint_path(path: Path) -> None:
    if not isinstance(path, Path) or not path.is_absolute() or not path.name:
        raise AgentSyncError("validation_error", "An absolute usage checkpoint path is required.")


def save_usage_checkpoint(path: Path, ledger: UsageLedger) -> None:
    """Replace one explicit checkpoint after the complete document is flushed."""
    _checkpoint_path(path)
    if type(ledger) is not UsageLedger:
        raise AgentSyncError("validation_error", "A usage ledger is required.")
    data = ledger.to_json().encode("utf-8")
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".agentsync-", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
        temporary = None
    except (OSError, ValueError):
        raise AgentSyncError(
            "checkpoint_unavailable", "Could not save the usage checkpoint."
        ) from None
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def load_usage_checkpoint(path: Path, project_id: str) -> UsageLedger:
    """Load an explicit checkpoint and validate it against the expected project."""
    _checkpoint_path(path)
    try:
        if not path.is_file():
            raise OSError("A regular checkpoint file is required.")
        with path.open("rb") as file:
            data = file.read(_JSON_LIMIT + 1)
    except (OSError, ValueError):
        raise AgentSyncError(
            "checkpoint_unavailable", "Could not read the usage checkpoint."
        ) from None
    if len(data) > _JSON_LIMIT:
        raise AgentSyncError("validation_error", "Invalid usage checkpoint content.")
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise AgentSyncError("validation_error", "Invalid usage checkpoint content.") from None
    return UsageLedger.from_json(project_id, text)

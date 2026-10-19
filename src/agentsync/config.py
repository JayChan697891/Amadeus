import os
import sys
from pathlib import Path

from agentsync.errors import AgentSyncError


def resolve_data_dir(data_dir: str | Path | None = None, *, create: bool = True) -> Path:
    value = data_dir if data_dir is not None else os.environ.get("AGENTSYNC_DATA_DIR")
    if value is not None:
        path = Path(value)
    elif sys.platform == "win32":
        path = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            / "AgentSync"
        )
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "AgentSync"
    else:
        path = (
            Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
            / "AgentSync"
        )
    if not path.is_absolute():
        raise AgentSyncError("invalid_data_dir", "Data directory must be absolute.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path.resolve()

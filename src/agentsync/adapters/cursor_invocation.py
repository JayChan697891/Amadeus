"""Prepare an explicit trusted-host Cursor CLI plan using bounded path reads.

The executable digest pins inspected bytes. The host declares a CLI version,
and preparation performs no version or login probe. The fixed ask and sandbox
flags leave authentication, billing, tool isolation and compatibility unverified.
Only separately approved synthetic, non-secret instructions belong in the
positional prompt, which the operating system can expose in process arguments.
Path checks can become stale before any later launch.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path, PosixPath, WindowsPath
from typing import Literal, NoReturn

from agentsync.adapters.base import AdapterTask, _bounded_text, _identifier
from agentsync.errors import AgentSyncError

MAX_BINARY_BYTES = 512 * 1024 * 1024
_MAX_ARGUMENT_BYTES = 4096  # Shared capture's per-argument limit.
_SHA256 = re.compile(r"[0-9a-fA-F]{64}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_ENV_KEYS = frozenset({"LANG", "LC_ALL", "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"})


def _invalid(code: str = "validation_error") -> NoReturn:
    raise AgentSyncError(code, "Invalid Cursor invocation input.") from None


def _path(value: Path) -> None:
    if type(value) not in (PosixPath, WindowsPath) or not value.is_absolute():
        _invalid()
    _bounded_text(str(value), _MAX_ARGUMENT_BYTES)
    if ".." in value.parts:
        _invalid()
    if type(value) is WindowsPath and (
        value.drive.startswith("\\\\")
        or any(":" in part or part.endswith((".", " ")) for part in value.parts[1:])
    ):
        _invalid()


@dataclass(frozen=True, slots=True)
class CursorHostProfile:
    """Explicit trusted host configuration with a required version declaration."""

    project_id: str
    session_id: str
    executable: Path = field(repr=False)
    root: Path = field(repr=False)
    expected_binary_sha256: str
    expected_cli_version: str
    model: str | None = None
    max_timeout_seconds: float = 300.0
    output_limit: int = 1024 * 1024

    def __post_init__(self) -> None:
        _identifier(self.project_id)
        _identifier(self.session_id)
        _path(self.executable)
        _path(self.root)
        # A native Windows executable avoids the OS's batch-file shell handling.
        if type(self.executable) is WindowsPath and self.executable.suffix.lower() != ".exe":
            _invalid()
        _bounded_text(self.expected_cli_version, 64)
        if (
            type(self.expected_binary_sha256) is not str
            or _SHA256.fullmatch(self.expected_binary_sha256) is None
            or _TOKEN.fullmatch(self.expected_cli_version) is None
            or (
                self.model is not None
                and (type(self.model) is not str or _TOKEN.fullmatch(self.model) is None)
            )
            or type(self.max_timeout_seconds) not in (int, float)
            or not 1 <= self.max_timeout_seconds <= 300
            or type(self.output_limit) is not int
            or not 1 <= self.output_limit <= 1024 * 1024
        ):
            _invalid()


@dataclass(frozen=True, slots=True)
class CursorInvocation:
    """Private terminal-JSON preparation data for an explicit host caller."""

    project_id: str
    session_id: str
    task_id: str
    request_id: str
    argv: tuple[str, ...] = field(repr=False)
    cwd: Path = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    timeout_seconds: float
    output_limit: int
    expected_cli_version: str
    binary_sha256: str
    stdin_text: str = field(default="", init=False, repr=False)
    scope: Literal["cursor_ask_cli_plan"] = field(default="cursor_ask_cli_plan", init=False)
    executes: Literal[False] = field(default=False, init=False)
    version_verified: Literal[False] = field(default=False, init=False)
    auth_verified: Literal[False] = field(default=False, init=False)
    billing_verified: Literal[False] = field(default=False, init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    sandbox_verified: Literal[False] = field(default=False, init=False)
    tool_restrictions_verified: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)

    def child_env(self) -> dict[str, str]:
        return dict(self.environment)


def _environment(environment: dict[str, str]) -> tuple[tuple[str, str], ...]:
    if type(environment) is not dict or len(environment) > len(_ENV_KEYS):
        _invalid()
    selected = tuple(environment.items())
    if len(selected) > len(_ENV_KEYS):
        _invalid()
    for key, value in selected:
        if type(key) is not str or key not in _ENV_KEYS:
            _invalid()
        _bounded_text(value, _MAX_ARGUMENT_BYTES)
    return tuple(sorted(selected))


def _ordinary(info: os.stat_result, *, directory: bool) -> bool:
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def _inspect_path(path: Path, *, directory: bool) -> os.stat_result:
    for parent in reversed(path.parents):
        if not _ordinary(parent.lstat(), directory=True):
            _invalid("host_path_invalid")
    info = path.lstat()
    if not _ordinary(info, directory=directory):
        _invalid("host_path_invalid")
    return info


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _binary_hash(profile: CursorHostProfile) -> str:
    try:
        root_before = _inspect_path(profile.root, directory=True)
        before = _inspect_path(profile.executable, directory=False)
        if before.st_size > MAX_BINARY_BYTES:
            _invalid("binary_too_large")
        if before.st_size <= 0:
            _invalid("host_path_invalid")
        digest = hashlib.sha256()
        read_flags = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with open(
            profile.executable,
            "rb",
            buffering=0,
            opener=lambda name, flags: os.open(name, flags | read_flags),
        ) as source:
            opened = os.fstat(source.fileno())
            if (
                not _ordinary(opened, directory=False)
                or _file_identity(opened) != _file_identity(before)
            ):
                _invalid("binary_changed")
            remaining = opened.st_size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    _invalid("binary_changed")
                digest.update(chunk)
                remaining -= len(chunk)
            if _file_identity(os.fstat(source.fileno())) != _file_identity(opened):
                _invalid("binary_changed")
        after = _inspect_path(profile.executable, directory=False)
        if _file_identity(after) != _file_identity(before):
            _invalid("binary_changed")
        root_after = _inspect_path(profile.root, directory=True)
        if (root_after.st_dev, root_after.st_ino) != (root_before.st_dev, root_before.st_ino):
            _invalid("root_changed")
    except (OSError, ValueError):
        _invalid("host_path_unavailable")
    binary_sha256 = digest.hexdigest()
    if binary_sha256 != profile.expected_binary_sha256.lower():
        _invalid("binary_pin_mismatch")
    return binary_sha256


def prepare_invocation(
    profile: CursorHostProfile, task: AdapterTask, *, environment: dict[str, str]
) -> CursorInvocation:
    """Validate input before path inspection and prepare fixed argv without launch.

    The environment accepts only explicit system variables from the allowlist.
    Host or client configuration can still influence a later process. The fixed
    argument count and the executable, model and prompt bounds also cap argv.
    """
    if type(profile) is not CursorHostProfile or type(task) is not AdapterTask:
        _invalid()
    profile = replace(profile)
    task = replace(task)
    if (task.project_id, task.session_id) != (profile.project_id, profile.session_id):
        _invalid("namespace_mismatch")
    if not task.instruction.strip():
        _invalid()
    # Keep the positional prompt from starting with an option-like token.
    prompt = f"Instruction:\n{task.instruction}"
    _bounded_text(prompt, _MAX_ARGUMENT_BYTES)
    selected_environment = _environment(environment)
    binary_sha256 = _binary_hash(profile)
    model_args = ("--model", profile.model) if profile.model is not None else ()
    argv = (
        str(profile.executable),
        "--print",
        "--output-format",
        "json",
        "--mode",
        "ask",
        "--sandbox",
        "enabled",
        *model_args,
        prompt,
    )
    return CursorInvocation(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        argv,
        profile.root,
        selected_environment,
        min(task.timeout_seconds, profile.max_timeout_seconds),
        profile.output_limit,
        profile.expected_cli_version,
        binary_sha256,
    )

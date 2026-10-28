"""Trusted-host Claude CLI preparation with bounded explicit filesystem reads.

Never launches, probes a version/account, discovers environment or authorizes.
The fixed flag combination is unexecuted. Ordinary hooks are disabled by the
settings declaration, but managed hooks are not; managed MCP may reject strict
configuration. Never fall back to weaker flags. Home/config can still supply
credentials/providers: this is no subscription-only or sandbox guarantee.
Host version/model declarations and path checks remain unverified and may become
stale, including OS ABA races. Real execution needs fresh authorization and M5.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, NoReturn

from agentsync.adapters.base import AdapterTask, _identifier
from agentsync.errors import AgentSyncError

SUPPORTED_CLI_VERSION = "2.1.295"
MAX_BINARY_BYTES = 512 * 1024 * 1024
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_()]*\Z")
_ENV_KEYS = frozenset(
    {
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "USERPROFILE",
        "HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CLAUDE_CONFIG_DIR",
    }
)


def _invalid(code: str = "validation_error") -> NoReturn:
    raise AgentSyncError(code, "Invalid Claude invocation input.") from None


def _text(value: object, maximum: int) -> bytes:
    if type(value) is not str or len(value) > maximum or "\x00" in value:
        _invalid()
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        _invalid()
    if len(encoded) > maximum:
        _invalid()
    return encoded


def _path(value: object) -> None:
    if not isinstance(value, Path) or not value.is_absolute():
        _invalid()
    _text(str(value), 4096)


@dataclass(frozen=True, slots=True)
class ClaudeHostProfile:
    project_id: str
    session_id: str
    executable: Path
    root: Path
    expected_binary_sha256: str
    model: str
    expected_cli_version: str = SUPPORTED_CLI_VERSION
    max_timeout_seconds: float = 300.0
    output_limit: int = 1024 * 1024

    def __post_init__(self) -> None:
        # Structural validation: no stat, file reads or host environment discovery.
        try:
            _identifier(self.project_id)
            _identifier(self.session_id)
        except AgentSyncError:
            _invalid()
        _path(self.executable)
        _path(self.root)
        if (
            type(self.expected_binary_sha256) is not str
            or _SHA256.fullmatch(self.expected_binary_sha256) is None
            or type(self.model) is not str
            or _MODEL.fullmatch(self.model) is None
        ):
            _invalid()
        _text(self.expected_cli_version, 64)
        try:
            valid_timeout = (
                type(self.max_timeout_seconds) in (int, float)
                and math.isfinite(self.max_timeout_seconds)
                and 1 <= self.max_timeout_seconds <= 300
            )
        except (OverflowError, ValueError):
            valid_timeout = False
        if (
            not valid_timeout
            or type(self.output_limit) is not int
            or not 1 <= self.output_limit <= 1024 * 1024
        ):
            _invalid()


@dataclass(frozen=True, slots=True)
class ClaudeInvocation:
    project_id: str
    session_id: str
    task_id: str
    request_id: str
    argv: tuple[str, ...]
    cwd: Path
    stdin_text: str = field(repr=False)
    environment: tuple[tuple[str, str], ...] = field(repr=False)
    timeout_seconds: float
    output_limit: int
    expected_cli_version: str
    binary_sha256: str
    scope: Literal["restricted_cli_plan"] = field(default="restricted_cli_plan", init=False)
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
        """Fresh explicit environment copy, without reading the host environment."""
        return dict(self.environment)


def _environment(value: dict[str, str]) -> tuple[tuple[str, str], ...]:
    if type(value) is not dict or len(value) > 256:
        _invalid()
    selected = {}
    total = 0
    for key, content in value.items():
        name, encoded = _text(key, 256), _text(content, 16384)
        if _ENV_NAME.fullmatch(key) is None:
            _invalid()
        total += len(name) + len(encoded) + 2
        if total > 65536:
            _invalid()
        canonical = key.upper()
        if canonical in _ENV_KEYS:
            if canonical in selected:
                _invalid("ambiguous_environment")
            selected[canonical] = content
    return tuple(sorted(selected.items()))


def _ordinary(info: os.stat_result, *, directory: bool = False) -> bool:
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _binary_hash(profile: ClaudeHostProfile) -> str:
    try:
        root = profile.root.lstat()
        initial = profile.executable.lstat()
        if not _ordinary(root, directory=True) or not _ordinary(initial):
            _invalid("host_path_invalid")
        if initial.st_size > MAX_BINARY_BYTES:
            _invalid("binary_too_large")
        value = hashlib.sha256()
        with profile.executable.open("rb") as source:
            opened = os.fstat(source.fileno())
            if not _ordinary(opened) or _identity(opened) != _identity(initial):
                _invalid("binary_changed")
            remaining = opened.st_size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    _invalid("binary_changed")
                value.update(chunk)
                remaining -= len(chunk)
            if _identity(os.fstat(source.fileno())) != _identity(opened):
                _invalid("binary_changed")
        final = profile.executable.lstat()
        if not _ordinary(final) or _identity(final) != _identity(initial):
            _invalid("binary_changed")
        final_root = profile.root.lstat()
        if not _ordinary(final_root, directory=True) or (root.st_dev, root.st_ino) != (
            final_root.st_dev,
            final_root.st_ino,
        ):
            _invalid("host_path_invalid")
    except (OSError, ValueError):
        _invalid("host_path_unavailable")
    result = value.hexdigest()
    if result != profile.expected_binary_sha256.lower():
        _invalid("binary_pin_mismatch")
    return result


def prepare_invocation(
    profile: ClaudeHostProfile, task: AdapterTask, *, environment: dict[str, str]
) -> ClaudeInvocation:
    """Bounded explicit binary/path inspection and fixed argv/stdin preparation.

    This is not strictly pure: the supplied executable is hashed and ordinary
    path identities are checked. Environment is an explicit bounded allowlist;
    API keys/tokens, provider overrides and code-injection variables are omitted.
    Home/config paths can still provide credentials or managed policy. No weaker
    flag fallback, actual CLI probe, execution or credential discovery occurs.
    """
    if type(profile) is not ClaudeHostProfile or type(task) is not AdapterTask:
        _invalid()
    try:
        task, profile = replace(task), replace(profile)
    except AgentSyncError:
        _invalid()
    if task.project_id != profile.project_id or task.session_id != profile.session_id:
        _invalid("namespace_mismatch")
    if profile.expected_cli_version != SUPPORTED_CLI_VERSION:
        _invalid("unsupported_cli_version")
    selected = _environment(environment)
    binary_sha256 = _binary_hash(profile)
    argv = (
        str(profile.executable),
        "-p",
        "--restricted",
        "--tools",
        "",
        "--disallowedTools",
        "*",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--disable-slash-commands",
        "--settings",
        '{"disableAllHooks":true}',
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        profile.model,
    )
    if len(argv) > 64 or sum(len(_text(argument, 4096)) for argument in argv) > 32768:
        _invalid()
    return ClaudeInvocation(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        argv,
        profile.root,
        task.instruction,
        selected,
        float(min(task.timeout_seconds, profile.max_timeout_seconds)),
        profile.output_limit,
        profile.expected_cli_version,
        binary_sha256,
    )

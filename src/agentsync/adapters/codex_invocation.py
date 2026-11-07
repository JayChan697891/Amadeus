"""Pure trusted-host Codex CLI plans, never client launch or authorization.

Only explicitly supplied paths are read, for a bounded binary hash and final
path checks. Version and model are host assertions; no CLI/version/login probe
or environment discovery occurs. This is not a sandbox or credential boundary:
even the fixed read-only flags cannot prove credentials are unreadable. A plan
may become stale after preparation; filesystem checks do not guarantee OS ABA
atomicity or authorize later execution. A real launch needs fresh authorization.
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

SUPPORTED_CLI_VERSION = "0.164.0-alpha.11.1"
SUPPORTED_CLI_VERSIONS = frozenset({SUPPORTED_CLI_VERSION, "0.166.0-alpha.6"})
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
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CODEX_HOME",
        "CODEX_CA_CERTIFICATE",
    }
)
_CONFIG = (
    'forced_login_method="chatgpt"',
    'model_provider="openai"',
    'web_search="disabled"',
    "mcp_servers={}",
    'history.persistence="none"',
    'model_reasoning_effort="low"',
    'service_tier="default"',
)
_DISABLE = (
    "shell_tool",
    "shell_snapshot",
    "apps",
    "multi_agent",
    "hooks",
    "remote_plugin",
    "skill_search",
    "skill_mcp_dependency_install",
)


def _invalid(code: str = "validation_error") -> NoReturn:
    raise AgentSyncError(code, "Invalid Codex invocation input.") from None


def _text(value: object, maximum: int) -> bytes:
    if type(value) is not str or "\x00" in value:
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
class CodexHostProfile:
    project_id: str
    session_id: str
    executable: Path
    root: Path
    expected_binary_sha256: str
    expected_cli_version: str = SUPPORTED_CLI_VERSION
    model: str = "gpt-6.1-sol"
    max_timeout_seconds: float = 300.0
    output_limit: int = 1024 * 1024

    def __post_init__(self) -> None:
        # Structural validation performs no filesystem or environment reads.
        _identifier(self.project_id)
        _identifier(self.session_id)
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
                type(self.max_timeout_seconds) in {int, float}
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
class CodexInvocation:
    """Private preparation data; effective timeout is capped by the host profile."""

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
    scope: Literal["read_only_cli_plan"] = field(default="read_only_cli_plan", init=False)
    executes: Literal[False] = field(default=False, init=False)
    version_verified: Literal[False] = field(default=False, init=False)
    auth_verified: Literal[False] = field(default=False, init=False)
    billing_verified: Literal[False] = field(default=False, init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)
    sandbox_verified: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)

    def child_env(self) -> dict[str, str]:
        """Return a fresh explicit environment copy; no host environment is read."""
        return dict(self.environment)


def _environment(value: dict[str, str]) -> tuple[tuple[str, str], ...]:
    if type(value) is not dict or len(value) > 256:
        _invalid()
    selected = {}
    total = 0
    for key, content in value.items():
        name = _text(key, 256)
        encoded = _text(content, 16384)
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
    # On Windows reparse points include junctions, not just symbolic links.
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        return False
    return stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    # Windows lstat/fstat can expose different ctime meanings. Identity, size
    # and mtime are comparable across both; the actual bytes still need the pin.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _binary_hash(profile: CodexHostProfile) -> str:
    try:
        if not _ordinary(profile.root.lstat(), directory=True):
            _invalid("host_path_invalid")
        initial = profile.executable.lstat()
        if not _ordinary(initial):
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
        if _identity(profile.executable.lstat()) != _identity(initial):
            _invalid("binary_changed")
    except (OSError, ValueError):
        _invalid("host_path_unavailable")
    result = value.hexdigest()
    if result != profile.expected_binary_sha256.lower():
        _invalid("binary_pin_mismatch")
    return result


def prepare_invocation(
    profile: CodexHostProfile, task: AdapterTask, *, environment: dict[str, str]
) -> CodexInvocation:
    """Prepare fixed flags after namespace validation; never start or authorize.

    Explicit environment input is bounded and filtered, not fetched from this
    process. Only standard SSL_CERT_FILE/DIR are allowed, not arbitrary matching
    prefixes. Unknown keys, API keys, tokens and provider URL overrides are not
    propagated. Profile timeout bounds the effective requested timeout.
    """
    if type(profile) is not CodexHostProfile or type(task) is not AdapterTask:
        _invalid()
    task = replace(task)
    profile = replace(profile)
    if task.project_id != profile.project_id or task.session_id != profile.session_id:
        _invalid("namespace_mismatch")
    if profile.expected_cli_version not in SUPPORTED_CLI_VERSIONS:
        _invalid("unsupported_cli_version")
    selected_environment = _environment(environment)
    binary_sha256 = _binary_hash(profile)
    argv = (
        str(profile.executable),
        "-a",
        "never",
        "exec",
        "--ignore-user-config",
        "--strict-config",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--json",
        "--color",
        "never",
        "--model",
        profile.model,
        "-C",
        str(profile.root),
        *(argument for config in _CONFIG for argument in ("-c", config)),
        *(argument for feature in _DISABLE for argument in ("--disable", feature)),
        "-",
    )
    if len(argv) > 64 or sum(len(_text(argument, 4096)) for argument in argv) > 32768:
        _invalid()
    return CodexInvocation(
        task.project_id,
        task.session_id,
        task.task_id,
        task.request_id,
        argv,
        profile.root,
        task.instruction,
        selected_environment,
        float(min(task.timeout_seconds, profile.max_timeout_seconds)),
        profile.output_limit,
        profile.expected_cli_version,
        binary_sha256,
    )

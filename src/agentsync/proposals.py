"""Bounded source proposals as inert data, never candidate or execution evidence."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, NoReturn

from agentsync.errors import AgentSyncError
from agentsync.resources.paths import _relative_parts

CHECKPOINT_PROTOCOL = "amadeus-proposal-checkpoint-v1"


def _invalid() -> NoReturn:
    raise AgentSyncError("proposal_invalid", "Source proposal does not match its data contract.")


def _members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _constant(_value: str) -> NoReturn:
    _invalid()


def _text(value: Any, limit: int) -> str:
    if type(value) is not str or len(value) > limit or "\0" in value:
        _invalid()
    try:
        if len(value.encode("utf-8")) > limit:
            _invalid()
    except UnicodeError:
        _invalid()
    return value


def _path(value: Any) -> str:
    value = _text(value, 512)
    if (
        value == "."
        or any(char in value for char in '\\<>"|?*')
        or unicodedata.normalize("NFC", value) != value
    ):
        _invalid()
    try:
        _relative_parts(value)
    except AgentSyncError:
        _invalid()
    return value


def proposal_paths(allowed_paths: list[str]) -> tuple[str, ...]:
    """Validate and canonicalize inert file labels without touching the filesystem."""
    if type(allowed_paths) is not list or not 1 <= len(allowed_paths) <= 8:
        _invalid()
    allowed = [_path(value) for value in allowed_paths]
    folded = sorted(value.casefold() for value in allowed)
    if len(set(folded)) != len(folded) or any(
        right.startswith(left + "/") for left in folded for right in folded if left != right
    ):
        _invalid()
    return tuple(sorted(allowed))


def parse_proposal(text: str, allowed_paths: list[str]) -> list[dict[str, str]]:
    """Require exactly the declared files; paths are labels, not write authority.

    At most eight UTF-8 text files, 8192 bytes each, within a 32768-byte JSON
    message. No Markdown extraction, extra fields, duplicate keys, aliases or
    partial-path matching. This function performs no filesystem operations.
    """
    allowed = proposal_paths(allowed_paths)
    _text(text, 32768)
    try:
        value = json.loads(text, object_pairs_hook=_members, parse_constant=_constant)
    except (ValueError, RecursionError):
        _invalid()
    if type(value) is not dict or set(value) != {"files"}:
        _invalid()
    files = value["files"]
    if type(files) is not list or len(files) != len(allowed):
        _invalid()
    contents: dict[str, str] = {}
    for item in files:
        if type(item) is not dict or set(item) != {"path", "content"}:
            _invalid()
        path = _path(item["path"])
        if path not in allowed or path in contents:
            _invalid()
        contents[path] = _text(item["content"], 8192)
    if set(contents) != set(allowed):
        _invalid()
    return [{"path": path, "content": contents[path]} for path in sorted(contents)]


def parse_checkpoint_message(
    text: str, allowed_paths: list[str], *, phase: str
) -> list[dict[str, str]]:
    """Require one exact phase envelope, retaining the proposal's existing bounds."""
    _text(text, 32768)
    try:
        value = json.loads(text, object_pairs_hook=_members, parse_constant=_constant)
    except (ValueError, RecursionError):
        _invalid()
    if (
        phase not in ("checkpoint", "final")
        or type(value) is not dict
        or set(value) != {"phase", "files"}
        or value["phase"] != phase
    ):
        _invalid()
    return parse_proposal(
        json.dumps({"files": value["files"]}, ensure_ascii=False, separators=(",", ":")),
        allowed_paths,
    )

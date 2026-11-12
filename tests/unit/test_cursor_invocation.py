"""Offline preparation using fixture bytes without running Cursor."""

import hashlib

import pytest

from agentsync.adapters.base import AdapterTask
from agentsync.adapters.cursor_invocation import CursorHostProfile, prepare_invocation
from agentsync.errors import AgentSyncError


def test_cursor_preparation_keeps_prompt_out_of_flag_parsing_and_pins_binary(tmp_path):
    root = tmp_path.resolve()
    binary = root / "cursor-fixture.exe"
    original = b"Offline fixture bytes"
    binary.write_bytes(original)
    profile = CursorHostProfile(
        "project",
        "session",
        binary,
        root,
        hashlib.sha256(original).hexdigest(),
        "declared-test-version",
        max_timeout_seconds=12,
    )
    request = AdapterTask(
        "project",
        "session",
        "task",
        "request",
        "--force untrusted option",
        30,
    )
    plan = prepare_invocation(profile, request, environment={"PATH": "explicit-path"})
    assert plan.argv[1:-1] == (
        "--print",
        "--output-format",
        "json",
        "--mode",
        "ask",
        "--sandbox",
        "enabled",
    )
    assert plan.argv[-1] == "Instruction:\n--force untrusted option"
    assert plan.stdin_text == ""
    assert plan.child_env() == {"PATH": "explicit-path"}
    assert plan.timeout_seconds == 12
    assert plan.executes is plan.version_verified is plan.real_client_verified is False

    with pytest.raises(AgentSyncError):
        prepare_invocation(profile, request, environment={"CURSOR_API_KEY": "fixture-only"})
    binary.write_bytes(b"Changed offline fixture bytes")
    with pytest.raises(AgentSyncError) as changed:
        prepare_invocation(profile, request, environment={})
    assert changed.value.code == "binary_pin_mismatch"

"""Malformed owner stdin is bounded and rejected before creating local state."""

import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "payload",
    [
        " " * 65537,
        "[" * 2000 + "]" * 2000,
        json.dumps({"operation": "hidden", "admin_token": "synthetic-secret"}),
        json.dumps({"self": "hidden", "admin_token": "synthetic-secret"}),
        json.dumps({"admin_token": "中" * 22000}, ensure_ascii=False),
    ],
    ids=["too-large", "too-deep", "reserved-operation", "reserved-self", "utf8-byte-limit"],
)
def test_owner_stdin_invalid_shapes_return_safe_envelope_without_state(tmp_path, payload):
    state = tmp_path / "untouched-state"
    process = subprocess.run(
        [sys.executable, "-m", "agentsync", "--data-dir", str(state), "owner", "list_members"],
        input=payload,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert process.returncode == 1
    response = json.loads(process.stdout)
    assert response["ok"] is False and response["error"]["code"] == "validation_error"
    assert "synthetic-secret" not in process.stdout + process.stderr
    assert "Traceback" not in process.stderr
    assert not state.exists()

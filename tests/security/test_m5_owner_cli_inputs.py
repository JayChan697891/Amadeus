"""Owner CLI rejects malformed input and missing state before opening Core."""

import json
import os
import subprocess
import sys

import pytest

from agentsync.sdk import AgentSyncClient


def run_owner(operation, payload, *, data_dir=None, env=None):
    command = [sys.executable, "-B", "-m", "agentsync"]
    if data_dir is not None:
        command.extend(("--data-dir", str(data_dir)))
    return subprocess.run(
        [*command, "owner", operation],
        input=payload,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=20,
        check=False,
        env=env,
    )


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
    process = run_owner("list_members", payload, data_dir=state)
    assert process.returncode == 1
    response = json.loads(process.stdout)
    assert response["ok"] is False and response["error"]["code"] == "validation_error"
    assert "synthetic-secret" not in process.stdout + process.stderr
    assert "Traceback" not in process.stderr
    assert not state.exists()


@pytest.mark.parametrize("source", ["argument", "environment"])
@pytest.mark.parametrize("directory_exists", [False, True], ids=["missing-dir", "empty-dir"])
def test_owner_missing_database_does_not_create_state(tmp_path, source, directory_exists):
    state = tmp_path / "wrong-project"
    if directory_exists:
        state.mkdir()
    payload = json.dumps(
        {
            "project_id": "11111111-1111-4111-8111-111111111111",
            "admin_token": "synthetic-secret",
        }
    )
    process = run_owner(
        "list_members",
        payload,
        data_dir=state if source == "argument" else None,
        env=os.environ | {"AGENTSYNC_DATA_DIR": str(state)},
    )
    assert process.returncode == 1
    if directory_exists:
        assert list(state.iterdir()) == []
    else:
        assert not state.exists()
    response = json.loads(process.stdout)
    assert response["ok"] is False and response["error"]["code"] == "not_found"
    assert "--data-dir" in response["error"]["message"]
    assert "synthetic-secret" not in process.stdout + process.stderr
    assert str(state) not in process.stdout + process.stderr
    assert not process.stderr


def test_owner_existing_database_supports_explicit_write_and_env_read(tmp_path):
    state, wrong = tmp_path / "project", tmp_path / "unused"
    client = AgentSyncClient(state)
    owner = client.call("create_project", name="Owner CLI fixture", root_path=str(tmp_path))["data"]
    actor = client.call("register_agent", **owner, name="Worker fixture")["data"]
    payload = owner | {
        "agent_id": actor["agent_id"],
        "roles": ["worker"],
        "expected_version": 1,
        "request_id": "owner-cli-grant",
    }
    added = run_owner(
        "set_agent_roles",
        json.dumps(payload),
        data_dir=state,
        env=os.environ | {"AGENTSYNC_DATA_DIR": str(wrong)},
    )
    assert added.returncode == 0
    assert not wrong.exists()

    listed = run_owner(
        "list_members",
        json.dumps(owner),
        env=os.environ | {"AGENTSYNC_DATA_DIR": str(state)},
    )
    assert listed.returncode == 0
    (membership,) = json.loads(listed.stdout)["data"]["members"]
    assert membership == json.loads(added.stdout)["data"]
    assert membership["agent_id"] == actor["agent_id"] and membership["roles"] == ["worker"]
    assert owner["admin_token"] not in added.stdout + added.stderr + listed.stdout + listed.stderr

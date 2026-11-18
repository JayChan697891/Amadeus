"""Dedicated initializer checks; no model, client account or candidate execution."""

import json
import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from agentsync.sdk import AgentSyncClient


@pytest.fixture
def initializer():
    path = Path(__file__).resolve().parents[2] / "examples/initialize_terminal_project.py"
    return runpy.run_path(str(path))


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux permissions and Git")
def test_initialize_real_project_and_preserve_owner(initializer, tmp_path, capsys, monkeypatch):
    root = tmp_path / "new-project"
    # Ambient Git overrides must not redirect the initializer or activate a hook.
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "foreign.git"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(tmp_path / "foreign-hooks"))
    assert initializer["main"]([str(root)]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert not captured.err
    owner_file = root / "private-owner.json"
    owner = json.loads(owner_file.read_bytes())
    assert set(owner) == {"project_id", "admin_token"}
    assert report == {
        "project_id": owner["project_id"],
        "root": str(root),
        "private_owner_file": str(owner_file),
    }
    assert owner["admin_token"] not in captured.out
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(owner_file.stat().st_mode) == 0o600
    assert AgentSyncClient(root / "core").owner_call("list_members", **owner)["ok"]
    repo = root / "repo"
    env = {"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    for args, expected in (
        (["status", "--porcelain"], b""),
        (
            ["log", "-1", "--format=%an <%ae>"],
            b"Amadeus terminal owner <terminal-owner@example.invalid>\n",
        ),
    ):
        result = subprocess.run(
            ["git", "-C", str(repo), *args], env=env, capture_output=True, check=True
        )
        assert result.stdout == expected
    saved_owner = owner_file.read_bytes()
    saved_database = (root / "core/agentsync.db").read_bytes()
    assert initializer["main"]([str(root)]) == 1
    assert owner_file.read_bytes() == saved_owner
    assert (root / "core/agentsync.db").read_bytes() == saved_database


@pytest.mark.skipif(sys.platform != "linux", reason="Actual Linux initializer")
def test_credential_sync_failure_preserves_partial_project(
    initializer, tmp_path, monkeypatch, capsys
):
    root = tmp_path / "partial-project"

    def failed_sync(_descriptor):
        raise OSError("Fixture disk sync failure")

    monkeypatch.setattr(initializer["os"], "fsync", failed_sync)
    assert initializer["main"]([str(root)]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "Fixture disk sync failure" not in captured.err
    assert json.loads(captured.err)["partial_state_retained"] is True
    owner_file = root / "private-owner.json"
    assert stat.S_IMODE(owner_file.stat().st_mode) == 0o600
    owner = json.loads(owner_file.read_bytes())
    assert owner["admin_token"] not in captured.err
    assert (root / "core/agentsync.db").is_file() and (root / "repo/.git").is_dir()
    assert initializer["main"]([str(root)]) == 1
    assert owner_file.read_bytes() == (json.dumps(owner) + "\n").encode()


@pytest.mark.skipif(sys.platform == "linux", reason="Actual unsupported platform")
def test_unsupported_platform_creates_nothing(initializer, tmp_path, capsys):
    root = tmp_path / "unsupported-project"
    assert initializer["main"]([str(root)]) == 1
    assert not root.exists() and not capsys.readouterr().out


def test_relative_root_creates_nothing(initializer, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert initializer["main"](["relative-project"]) == 1
    assert not (tmp_path / "relative-project").exists()
    assert not capsys.readouterr().out

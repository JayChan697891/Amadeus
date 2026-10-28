"""Preparation using fake non-executable bytes; no Claude execution or account probes."""

import hashlib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import agentsync.adapters.claude_invocation as invocation
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.claude_invocation import ClaudeHostProfile, prepare_invocation
from agentsync.errors import AgentSyncError


def fixture(tmp_path):
    binary = tmp_path / "fake-claude.exe"
    binary.write_bytes(b"Synthetic fixture, not executable Claude bytes.\n")
    root = tmp_path / "project"
    root.mkdir()
    return ClaudeHostProfile(
        "project",
        "session",
        binary,
        root,
        hashlib.sha256(binary.read_bytes()).hexdigest(),
        model="explicit-host-model",
    )


def task(**changes):
    return AdapterTask(
        **dict(
            project_id="project",
            session_id="session",
            task_id="task",
            request_id="request",
            instruction="private-prompt --model injected",
            **changes,
        )
    )


def test_fixed_argv_stdin_environment_privacy_and_unverified_markers(tmp_path, monkeypatch):
    profile = fixture(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-host-key")
    source = {
        "Path": "explicit-bin",
        "home": "private-home",
        "https_proxy": "explicit-proxy",
        "SSL_CERT_FILE": "ca",
        "SSL_CERT_DIR": "ca-dir",
        "claude_config_dir": "private-config",
        "ANTHROPIC_API_KEY": "private-api-key",
        "ANTHROPIC_AUTH_TOKEN": "private-token",
        "ANTHROPIC_BASE_URL": "private-provider",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CODEX_HOME": "private-codex-home",
        "NODE_OPTIONS": "private-injection",
        "PYTHONPATH": "private-import",
        "SSL_CERT_PASSWORD": "private-certificate",
    }
    before = source.copy()
    plan = prepare_invocation(profile, task(), environment=source)
    assert plan.argv == (
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
        "explicit-host-model",
    )
    assert plan.stdin_text == task().instruction and task().instruction not in plan.argv
    assert plan.cwd == profile.root and plan.expected_cli_version == "2.1.295"
    assert (plan.project_id, plan.session_id, plan.task_id, plan.request_id) == (
        "project",
        "session",
        "task",
        "request",
    )
    expected = {
        "PATH": "explicit-bin",
        "HOME": "private-home",
        "HTTPS_PROXY": "explicit-proxy",
        "SSL_CERT_FILE": "ca",
        "SSL_CERT_DIR": "ca-dir",
        "CLAUDE_CONFIG_DIR": "private-config",
    }
    assert plan.child_env() == expected and source == before
    source["Path"] = "changed"
    child = plan.child_env()
    child["PATH"] = "changed"
    assert plan.child_env() == expected and "private" not in repr(plan)
    assert prepare_invocation(profile, task(), environment={}).environment == ()
    assert plan.scope == "restricted_cli_plan"
    assert not any(
        (
            plan.executes,
            plan.version_verified,
            plan.auth_verified,
            plan.billing_verified,
            plan.real_client_verified,
            plan.sandbox_verified,
            plan.tool_restrictions_verified,
        )
    )
    assert plan.verification == plan.core_authorization == "unverified"
    with pytest.raises(FrozenInstanceError):
        plan.environment = ()


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"expected_cli_version": "2.1.294"}, "unsupported_cli_version"),
        ({"expected_binary_sha256": "0" * 64}, "binary_pin_mismatch"),
    ],
)
def test_bad_version_or_binary_pin_returns_fixed_claude_error(tmp_path, changes, code):
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(replace(fixture(tmp_path), **changes), task(), environment={})
    assert error.value.code == code
    assert error.value.message == "Invalid Claude invocation input."


def test_profile_namespace_version_and_environment_validation_precede_io(tmp_path, monkeypatch):
    profile = fixture(tmp_path)
    monkeypatch.setattr(Path, "lstat", lambda *_args, **_kwargs: pytest.fail("Premature I/O"))
    for change in (
        {"root": Path("relative")},
        {"model": "--flag"},
        {"project_id": ""},
        {"expected_binary_sha256": "bad"},
        {"max_timeout_seconds": True},
        {"max_timeout_seconds": float("nan")},
        {"max_timeout_seconds": 10**400},
        {"max_timeout_seconds": 301},
        {"output_limit": 1048577},
        {"output_limit": False},
    ):
        with pytest.raises(AgentSyncError) as error:
            replace(profile, **change)
        assert error.value.code == "validation_error"
        assert error.value.message == "Invalid Claude invocation input."
    for change in ({"project_id": "foreign"}, {"session_id": "foreign"}):
        request = replace(task(), **change)
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(profile, request, environment={})
        assert error.value.code == "namespace_mismatch"
    for value, code in (
        ({"PATH": "one", "Path": "two"}, "ambiguous_environment"),
        ({"PATH": False}, "validation_error"),
        ({"PATH": "\ud800"}, "validation_error"),
        ({"PATH": "x" * 16385}, "validation_error"),
        ({"BAD=KEY": ""}, "validation_error"),
        ({f"KEY_{index}": "" for index in range(257)}, "validation_error"),
        ({f"KEY_{index}": "x" * 16384 for index in range(4)}, "validation_error"),
    ):
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(profile, task(), environment=value)
        assert error.value.code == code
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(replace(profile, expected_cli_version="other"), task(), environment={})
    assert error.value.code == "unsupported_cli_version"


def test_preparation_only_reads_owned_paths_and_caps_timeout(tmp_path):
    profile = fixture(tmp_path)
    marker = profile.root / "unchanged.txt"
    marker.write_bytes(b"Caller-owned unchanged contents")
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (profile.executable, marker)
    }
    plan = prepare_invocation(
        replace(profile, max_timeout_seconds=2, output_limit=128),
        replace(task(), timeout_seconds=20),
        environment={},
    )
    assert plan.timeout_seconds == 2.0 and plan.output_limit == 128
    assert set(tmp_path.iterdir()) == {profile.executable, profile.root}
    assert list(profile.root.iterdir()) == [marker]
    assert before == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before}
    for change in ({"executable": profile.root}, {"root": profile.executable}):
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(replace(profile, **change), task(), environment={})
        assert error.value.code == "host_path_invalid"


def test_binary_changes_during_bounded_hash_and_size_limit_fail_closed(tmp_path, monkeypatch):
    profile = fixture(tmp_path)
    original = invocation.os.fstat
    calls = []

    def mutate_after_read(descriptor):
        calls.append(1)
        if len(calls) == 2:
            with profile.executable.open("ab") as binary:
                binary.write(b"changed")
        return original(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(invocation.os, "fstat", mutate_after_read)
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(profile, task(), environment={})
        assert error.value.code == "binary_changed"
    monkeypatch.setattr(invocation, "MAX_BINARY_BYTES", 1)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task(), environment={})
    assert error.value.code == "binary_too_large"

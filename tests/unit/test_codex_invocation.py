"""Pure plans using synthetic, non-executable fake binaries; never actual CLI tests."""

import hashlib
import os
import tomllib
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from agentsync.adapters import codex_invocation
from agentsync.adapters.approved_launch import prepare_launch_review
from agentsync.adapters.base import AdapterTask
from agentsync.adapters.codex_invocation import CodexHostProfile, prepare_invocation
from agentsync.errors import AgentSyncError


def profile_for(tmp_path, **changes):
    binary = tmp_path / "synthetic-fake.exe"
    binary.write_bytes(b"Synthetic fixture bytes; not a Codex executable.\n")
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    fields = dict(
        project_id="project-fixture",
        session_id="session-fixture",
        executable=binary,
        root=root,
        expected_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
    )
    fields.update(changes)
    return CodexHostProfile(**fields)


def task(**changes):
    fields = dict(
        project_id="project-fixture",
        session_id="session-fixture",
        task_id="task-fixture",
        request_id="request-fixture",
        instruction="Literal instruction; never a command",
    )
    fields.update(changes)
    return AdapterTask(**fields)


def test_read_only_invocation_uses_fixed_host_flags_and_never_claims_execution(tmp_path):
    profile = profile_for(tmp_path)
    request = task()
    plan = prepare_invocation(profile, request, environment={})
    assert plan.argv == (
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
        "gpt-6.1-sol",
        "-C",
        str(profile.root),
        "-c",
        'forced_login_method="chatgpt"',
        "-c",
        'model_provider="openai"',
        "-c",
        'web_search="disabled"',
        "-c",
        "mcp_servers={}",
        "-c",
        'history.persistence="none"',
        "-c",
        'model_reasoning_effort="low"',
        "-c",
        'service_tier="default"',
        "--disable",
        "shell_tool",
        "--disable",
        "shell_snapshot",
        "--disable",
        "apps",
        "--disable",
        "multi_agent",
        "--disable",
        "hooks",
        "--disable",
        "remote_plugin",
        "--disable",
        "skill_search",
        "--disable",
        "skill_mcp_dependency_install",
        "-",
    )
    assert plan.cwd == profile.root
    assert plan.stdin_text == request.instruction
    assert plan.timeout_seconds == 300.0 and plan.output_limit == 1024 * 1024
    assert plan.environment == ()
    assert plan.executes is False
    assert plan.version_verified is False
    assert plan.auth_verified is False
    assert plan.billing_verified is False
    assert plan.real_client_verified is False
    assert plan.verification == plan.core_authorization == "unverified"
    assert plan.sandbox_verified is False
    assert isinstance(plan.cwd, Path)


def test_task_text_cannot_choose_host_executable_model_root_or_provider(tmp_path):
    profile = profile_for(tmp_path, model="host-model.v1")
    instruction = "private-instruction --model other --sandbox bypass; OPENAI_API_KEY=dummy"
    request = task(instruction=instruction)
    plan = prepare_invocation(profile, request, environment={})
    assert plan.stdin_text == instruction
    assert plan.argv[0] == str(profile.executable)
    assert plan.argv[plan.argv.index("--model") + 1] == "host-model.v1"
    assert plan.cwd == profile.root
    assert instruction not in plan.argv
    assert "private-instruction" not in repr(plan)
    assert "bypass" not in plan.argv
    assert not any("model_providers.openai." in value for value in plan.argv)
    assert (plan.project_id, plan.session_id, plan.task_id, plan.request_id) == (
        request.project_id,
        request.session_id,
        request.task_id,
        request.request_id,
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ({"expected_binary_sha256": "0" * 64}, "binary_pin_mismatch"),
        ({"expected_cli_version": "0.163.0"}, "unsupported_cli_version"),
    ],
)
def test_wrong_binary_pin_or_unreviewed_version_fails_with_static_error(tmp_path, change, code):
    profile = profile_for(tmp_path, **change)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task(), environment={})
    assert error.value.code == code
    assert error.value.message == "Invalid Codex invocation input."
    assert str(tmp_path) not in str(error.value)


def test_foreign_task_namespace_rejects_before_missing_binary_or_root_is_read(tmp_path):
    profile = profile_for(tmp_path)
    profile.executable.unlink()
    profile.root.rmdir()
    for changes in ({"project_id": "foreign-project"}, {"session_id": "foreign-session"}):
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(profile, task(**changes), environment={})
        assert error.value.code == "namespace_mismatch"


def test_preparation_preserves_explicit_binary_and_project_contents(tmp_path):
    profile = profile_for(tmp_path)
    marker = profile.root / "fixture.txt"
    marker.write_text("caller-owned contents", encoding="utf-8")
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (profile.executable, marker)
    }
    listing = tuple(sorted(path.name for path in tmp_path.iterdir()))
    prepare_invocation(profile, task(), environment={})
    assert tuple(sorted(path.name for path in tmp_path.iterdir())) == listing
    assert tuple(profile.root.iterdir()) == (marker,)
    for path, original in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == original


def test_explicit_environment_filters_dummy_secrets_and_copies_immutable_plan(tmp_path):
    profile = profile_for(tmp_path)
    source = {
        "Path": "fixture-bin",
        "SystemRoot": "fixture-system-root",
        "SystemDrive": "C:",
        "TEMP": "fixture-temp",
        "TMP": "fixture-tmp",
        "https_proxy": "fixture-proxy",
        "SSL_CERT_FILE": "fixture-ca-file",
        "SSL_CERT_DIR": "fixture-ca-directory",
        "CODEX_CA_CERTIFICATE": "fixture-codex-ca",
        "codex_home": "private-dummy-home",
        "OPENAI_API_KEY": "dummy-key-never-real",
        "OPENAI_BASE_URL": "dummy-provider-url",
        "ANTHROPIC_AUTH_TOKEN": "dummy-auth-token",
        "SSL_CERT_PASSWORD": "dummy-certificate-secret",
        "SSL_CERT_CUSTOM": "dummy-unknown-ssl-setting",
    }
    original = source.copy()
    plan = prepare_invocation(profile, task(instruction="private-dummy-prompt"), environment=source)
    expected = {
        "PATH": "fixture-bin",
        "SYSTEMROOT": "fixture-system-root",
        "SYSTEMDRIVE": "C:",
        "TEMP": "fixture-temp",
        "TMP": "fixture-tmp",
        "HTTPS_PROXY": "fixture-proxy",
        "SSL_CERT_FILE": "fixture-ca-file",
        "SSL_CERT_DIR": "fixture-ca-directory",
        "CODEX_CA_CERTIFICATE": "fixture-codex-ca",
        "CODEX_HOME": "private-dummy-home",
    }
    assert plan.environment == tuple(sorted(expected.items()))
    assert plan.child_env() == expected
    assert source == original
    assert "private-dummy" not in repr(plan)
    assert "dummy-key" not in repr(plan)
    copied = plan.child_env()
    copied["PATH"] = "changed-copy"
    source["Path"] = "changed-source"
    assert plan.child_env() == expected
    with pytest.raises(FrozenInstanceError):
        plan.environment = ()
    with pytest.raises(FrozenInstanceError):
        profile.model = "changed"


def test_case_ambiguous_allowed_environment_is_rejected_not_arbitrarily_selected(tmp_path):
    profile = profile_for(tmp_path)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task(), environment={"PATH": "one", "Path": "two"})
    assert error.value.code == "ambiguous_environment"
    plan = prepare_invocation(
        profile, task(), environment={"DUMMY_TOKEN": "one", "dummy_token": "two"}
    )
    assert plan.environment == ()


@pytest.mark.skipif(os.name != "nt", reason="The opt-in MXC plan requires native Windows")
def test_mxc_plan_pins_readonly_roots_and_disabled_action_routes_within_argv_limit(tmp_path):
    profile = profile_for(tmp_path, windows_mxc=True, expected_cli_version="0.167.0-alpha.3.2")
    environment = {
        key: "explicit-fixture-value"
        for key in (
            "SYSTEMROOT",
            "SYSTEMDRIVE",
            "LOCALAPPDATA",
            "USERPROFILE",
            "CODEX_HOME",
            "TEMP",
            "TMP",
        )
    }
    plan = prepare_invocation(profile, task(), environment=environment)
    configs = [plan.argv[index + 1] for index, value in enumerate(plan.argv) if value == "-c"]
    effective = tomllib.loads("\n".join(configs))
    assert effective["windows"]["sandbox"] == "mxc"
    assert effective["default_permissions"] == "amadeus_readonly"
    assert effective["permissions"]["amadeus_readonly"] == {
        "filesystem": {":minimal": "read", profile.root.as_posix(): "read"},
        "network": {"enabled": False},
    }
    assert effective["browser_use"]["default_origin_policy"]["access"] == "deny"
    assert effective["computer_use"]["default_app_access"] == "deny"
    assert effective["features"]["image_generation"] is False
    assert effective["features"]["goals"] is False
    assert effective["agents"]["enabled"] is False
    assert all(value is False for value in effective["features"].values())
    assert effective["forced_login_method"] == "chatgpt"
    assert effective["model_provider"] == "openai"
    assert "--sandbox" not in plan.argv  # The legacy setting would override the named profile.
    assert len(plan.argv) <= 64
    assert plan.child_env() == environment
    assert plan.sandbox_verified is plan.auth_verified is plan.billing_verified is False
    native_review = prepare_launch_review(profile, task(), environment=environment)
    legacy_review = prepare_launch_review(
        replace(profile, windows_mxc=False), task(), environment=environment
    )
    assert native_review.plan_sha256 != legacy_review.plan_sha256
    with pytest.raises(AgentSyncError) as missing_environment:
        prepare_invocation(profile, task(), environment={})
    assert missing_environment.value.code == "host_environment_unavailable"


def test_mxc_plan_rejects_legacy_cli_before_binary_access(tmp_path):
    profile = profile_for(tmp_path, windows_mxc=True)
    profile.executable.unlink()
    with pytest.raises(AgentSyncError) as rejected:
        prepare_invocation(profile, task(), environment={})
    assert rejected.value.code == "unsupported_mxc_profile"


def test_environment_type_text_count_and_total_size_bounds_are_strict(tmp_path):
    profile = profile_for(tmp_path)
    invalid = [
        None,
        {"PATH": False},
        {"PATH": "bad\x00value"},
        {"PATH": "\ud800"},
        {"PATH": "x" * 16385},
        {"x" * 257: "value"},
        {"BAD=NAME": "value"},
        {f"DUMMY_{index}": "" for index in range(257)},
        {f"DUMMY_{index}": "x" * 16384 for index in range(4)},
    ]
    for value in invalid:
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(profile, task(), environment=value)
        assert error.value.code == "validation_error"
        assert error.value.message == "Invalid Codex invocation input."


def test_host_profile_limits_reject_unsafe_or_unsupported_shapes(tmp_path):
    profile = profile_for(tmp_path)
    invalid = [
        {"executable": Path("relative.exe")},
        {"root": "string-instead-of-Path"},
        {"expected_binary_sha256": "x" * 64},
        {"expected_binary_sha256": "a" * 63},
        {"model": "--injected-flag"},
        {"model": "model\nother"},
        {"max_timeout_seconds": True},
        {"max_timeout_seconds": 0},
        {"max_timeout_seconds": 301},
        {"max_timeout_seconds": float("nan")},
        {"max_timeout_seconds": 2**10000},
        {"output_limit": True},
        {"output_limit": 0},
        {"output_limit": 1048577},
    ]
    for change in invalid:
        with pytest.raises(AgentSyncError) as error:
            replace(profile, **change)
        assert error.value.code == "validation_error"


def test_effective_timeout_is_explicitly_bounded_by_host_and_request(tmp_path):
    profile = profile_for(tmp_path, max_timeout_seconds=2, output_limit=128)
    bounded = prepare_invocation(profile, task(timeout_seconds=50), environment={})
    shorter = prepare_invocation(profile, task(timeout_seconds=1), environment={})
    assert bounded.timeout_seconds == 2.0
    assert shorter.timeout_seconds == 1.0
    assert bounded.output_limit == shorter.output_limit == 128
    assert bounded.expected_cli_version == "0.164.0-alpha.11.1"
    assert bounded.version_verified is False


def test_frozen_request_and_profile_are_revalidated_before_path_access(tmp_path):
    profile = profile_for(tmp_path)
    profile.executable.unlink()
    request = task()
    object.__setattr__(request, "timeout_seconds", True)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, request, environment={})
    assert error.value.code == "validation_error"
    object.__setattr__(profile, "output_limit", False)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task(), environment={})
    assert error.value.code == "validation_error"


def test_binary_hash_reads_multiple_chunks_and_requires_ordinary_explicit_paths(tmp_path):
    profile = profile_for(tmp_path)
    raw = b"Synthetic bytes, never executed.\n" * 40000
    profile.executable.write_bytes(raw)
    profile = replace(profile, expected_binary_sha256=hashlib.sha256(raw).hexdigest().upper())
    plan = prepare_invocation(profile, task(), environment={})
    assert plan.binary_sha256 == hashlib.sha256(raw).hexdigest()
    assert plan.version_verified is False and plan.executes is False
    for change in ({"executable": profile.root}, {"root": profile.executable}):
        with pytest.raises(AgentSyncError) as error:
            prepare_invocation(replace(profile, **change), task(), environment={})
        assert error.value.code == "host_path_invalid"


def test_desktop_version_preserves_legacy_default_and_changes_only_asserted_version(tmp_path):
    profile = profile_for(tmp_path)
    assert (
        profile.expected_cli_version
        == codex_invocation.SUPPORTED_CLI_VERSION
        == "0.164.0-alpha.11.1"
    )
    supplied = {"CODEX_HOME": "synthetic-home", "OPENAI_API_KEY": "synthetic-excluded-secret"}
    legacy = prepare_invocation(profile, task(), environment=supplied)
    desktop = prepare_invocation(
        replace(profile, expected_cli_version="0.166.0-alpha.6"), task(), environment=supplied
    )
    assert desktop == replace(legacy, expected_cli_version="0.166.0-alpha.6")
    assert codex_invocation.SUPPORTED_CLI_VERSIONS == frozenset(
        {"0.164.0-alpha.11.1", "0.166.0-alpha.6", "0.167.0-alpha.3.2"}
    )
    assert type(codex_invocation.SUPPORTED_CLI_VERSIONS) is frozenset
    assert desktop.scope == "read_only_cli_plan"
    assert desktop.verification == desktop.core_authorization == "unverified"
    assert all(
        getattr(desktop, marker) is False
        for marker in (
            "executes",
            "version_verified",
            "auth_verified",
            "billing_verified",
            "real_client_verified",
            "sandbox_verified",
        )
    )


def test_current_desktop_version_changes_only_asserted_version(tmp_path):
    profile = profile_for(tmp_path)
    supplied = {"CODEX_HOME": "synthetic-home", "OPENAI_API_KEY": "synthetic-excluded-secret"}
    legacy = prepare_invocation(profile, task(), environment=supplied)
    current = prepare_invocation(
        replace(profile, expected_cli_version="0.167.0-alpha.3.2"), task(), environment=supplied
    )
    assert current == replace(legacy, expected_cli_version="0.167.0-alpha.3.2")


@pytest.mark.parametrize(
    "version",
    [
        "0.162.0",
        "0.164.0-alpha.11.2",
        "0.166.0-alpha.5",
        "0.166.0-alpha.7",
        "0.167.0-alpha.1",
        "0.167.0-alpha.3.1",
        "0.167.0-alpha.3.3",
        "0.167.0-alpha.3",
        "0.167.0-alpha.3.2 ",
        "0.166.0-alpha.6 ",
    ],
)
def test_unlisted_versions_are_rejected_before_filesystem_access(tmp_path, monkeypatch, version):
    profile = replace(profile_for(tmp_path), expected_cli_version=version)

    def no_io(*args, **kwargs):
        pytest.fail("Unlisted version reached filesystem access")

    monkeypatch.setattr(Path, "lstat", no_io)
    monkeypatch.setattr(Path, "open", no_io)
    with pytest.raises(AgentSyncError) as error:
        prepare_invocation(profile, task(), environment={})
    assert error.value.code == "unsupported_cli_version"
    assert error.value.message == "Invalid Codex invocation input."

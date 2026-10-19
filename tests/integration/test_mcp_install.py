"""Installer mutation-safety checks. Subprocess fixtures are not host acceptance."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MISSING = subprocess.CompletedProcess([], 1, "", "Error: No MCP server named 'agentsync' found.\n")
OK = subprocess.CompletedProcess([], 0, "", "")


@pytest.fixture
def installer(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "agentsync_codex_installer", ROOT / "examples/mcp_clients/install_codex.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    binary = tmp_path / "Codex CLI.exe"
    python = tmp_path / "Python env.exe"
    binary.touch()
    python.touch()
    calls = []
    responses = []

    def execute(argv):
        calls.append([str(item) for item in argv])
        if "-I" in argv:
            return OK
        assert responses, "Unexpected subprocess call"
        return responses.pop(0)

    monkeypatch.setattr(module, "run_process", execute)
    return module, binary, python, tmp_path / "Shared data; $literal", calls, responses


def configured(python, data, **extra):
    entry = {
        "name": "agentsync",
        "enabled": True,
        "transport": {
            "type": "stdio",
            "command": str(python),
            "args": ["-m", "agentsync", "--data-dir", str(data), "mcp"],
            "env": None,
            "env_vars": [],
            "cwd": None,
        },
        "enabled_tools": None,
        "disabled_tools": None,
    }
    entry.update(extra)
    return subprocess.CompletedProcess([], 0, json.dumps(entry), "")


def test_dry_run_never_mutates_configuration_or_creates_data(installer):
    module, binary, python, data, calls, responses = installer
    responses.append(MISSING)
    result = module.install(binary, python, data, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["planned_argv"] == [
        str(binary),
        "mcp",
        "add",
        "agentsync",
        "--",
        str(python),
        "-m",
        "agentsync",
        "--data-dir",
        str(data),
        "mcp",
    ]
    assert not data.exists()
    assert all("add" not in argv for argv in calls)


def test_identical_configuration_is_noop(installer):
    module, binary, python, data, calls, responses = installer
    responses.append(configured(python, data))
    assert module.install(binary, python, data) == {
        "status": "already_configured",
        "changed": False,
    }
    assert all("add" not in argv for argv in calls)


@pytest.mark.parametrize("difference", ["path", "disabled", "filtered_tools", "environment"])
def test_conflicting_configuration_is_never_overwritten(installer, difference):
    module, binary, python, data, calls, responses = installer
    entry = json.loads(configured(python, data).stdout)
    if difference == "path":
        entry["transport"]["args"][3] = str(data / "other")
    elif difference == "disabled":
        entry["enabled"] = False
    elif difference == "filtered_tools":
        entry["enabled_tools"] = []
    else:
        entry["transport"]["env"] = {"SECRET": "never-log-this"}
    responses.append(subprocess.CompletedProcess([], 0, json.dumps(entry), ""))
    with pytest.raises(module.InstallError, match="Nothing was overwritten") as caught:
        module.install(binary, python, data)
    assert "never-log-this" not in str(caught.value)
    assert all("add" not in argv for argv in calls)


@pytest.mark.parametrize(
    "reply",
    [
        subprocess.CompletedProcess([], 0, "not JSON secret", ""),
        subprocess.CompletedProcess([], 0, "[]", ""),
        subprocess.CompletedProcess([], 1, "", "Error: malformed config contains secret"),
        subprocess.CompletedProcess([], 0, '{"name":"agentsync","transport":{}}', ""),
    ],
)
def test_unrecognized_read_response_fails_closed(installer, reply):
    module, binary, python, data, calls, responses = installer
    responses.append(reply)
    with pytest.raises(module.InstallError) as caught:
        module.install(binary, python, data)
    assert "secret" not in str(caught.value)
    assert all("add" not in argv for argv in calls)


def test_registration_uses_public_argv_and_verifies_readback(installer):
    module, binary, python, data, calls, responses = installer
    responses.extend([MISSING, MISSING, OK, configured(python, data)])
    assert module.install(binary, python, data) == {"status": "installed", "changed": True}
    adds = [argv for argv in calls if "add" in argv]
    assert adds == [
        [
            str(binary),
            "mcp",
            "add",
            "agentsync",
            "--",
            str(python),
            "-m",
            "agentsync",
            "--data-dir",
            str(data),
            "mcp",
        ]
    ]
    assert calls[-1] == [str(binary), "mcp", "get", "agentsync", "--json"]
    assert not data.exists()


def test_entry_appearing_before_mutation_is_not_overwritten(installer):
    module, binary, python, data, calls, responses = installer
    responses.extend([MISSING, configured(python, data)])
    with pytest.raises(module.InstallError, match="appeared"):
        module.install(binary, python, data)
    assert all("add" not in argv for argv in calls)


def test_relative_data_path_rejected_before_configuration_read(installer):
    module, binary, python, _, calls, _ = installer
    with pytest.raises(module.InstallError, match="absolute"):
        module.install(binary, python, "relative-data")
    assert len(calls) == 1  # Only isolated Python prerequisite was inspected.


def test_subprocess_boundary_preserves_literal_argv_and_disables_shell(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "agentsync_codex_installer_boundary", ROOT / "examples/mcp_clients/install_codex.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorded = []

    def execute(argv, **kwargs):
        recorded.append((argv, kwargs))
        return OK

    monkeypatch.setattr(module.subprocess, "run", execute)
    argv = ["native.exe", "--", "spaces; $(not-a-command) & literal"]
    module.run_process(argv)
    assert recorded[0][0] == argv
    assert recorded[0][1]["shell"] is False
    assert recorded[0][1]["timeout"] == 30


def test_windows_shell_shim_is_rejected(installer):
    module, _, _, data, calls, _ = installer
    shim = data.parent / "codex.cmd"
    shim.touch()
    with pytest.raises(module.InstallError, match="shell shim"):
        module.install(shim, data_dir=data)
    assert calls == []


def test_python_shell_shim_is_rejected(installer):
    module, binary, _, data, calls, _ = installer
    shim = data.parent / "python.cmd"
    shim.touch()
    with pytest.raises(module.InstallError, match="shell shim"):
        module.install(binary, shim, data)
    assert calls == []


def test_missing_installed_python_package_prevents_config_mutation(installer, monkeypatch):
    module, binary, python, data, _, _ = installer
    calls = []

    def missing_package(argv):
        calls.append(argv)
        return subprocess.CompletedProcess([], 1, "", "private local interpreter traceback")

    monkeypatch.setattr(module, "run_process", missing_package)
    with pytest.raises(module.InstallError, match="not installed") as caught:
        module.install(binary, python, data)
    assert len(calls) == 1 and "-I" in calls[0]
    assert "private" not in str(caught.value)
    assert not data.exists()


def test_wrong_registration_readback_is_reported_not_rolled_back(installer):
    module, binary, python, data, calls, responses = installer
    responses.extend([MISSING, MISSING, OK, configured(python, data / "different")])
    with pytest.raises(module.InstallError, match="could not be verified"):
        module.install(binary, python, data)
    assert [argv[2] for argv in calls[1:]] == ["get", "get", "add", "get"]

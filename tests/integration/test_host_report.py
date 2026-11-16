"""Validate saved native-run evidence; these tests are not live host acceptance."""

import copy
import json
import re
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE = runpy.run_path(str(ROOT / "tests/manual/probe_codex_collaboration.py"))


@pytest.fixture
def report():
    return json.loads((ROOT / "docs/codex-collaboration-probe.json").read_text(encoding="utf-8"))


def test_saved_native_evidence_has_exact_workflow(report):
    PROBE["validate_report"](report)


@pytest.mark.parametrize(
    "corruption",
    [
        "status",
        "version",
        "result",
        "reviewer",
        "evidence",
        "duplicate",
        "desktop_claim",
    ],
)
def test_evidence_validator_rejects_corruption(report, corruption):
    changed = copy.deepcopy(report)
    observations = changed["task_observations"]
    if corruption == "status":
        observations[4]["status"] = "review"
    elif corruption == "version":
        observations[5]["version"] = 4
    elif corruption == "result":
        observations[6]["result_sha256"] = "different"
    elif corruption == "reviewer":
        observations[4]["review"]["reviewer"] = "A"
    elif corruption == "evidence":
        observations[6]["review"]["evidence"] = ""
    elif corruption == "duplicate":
        changed["duplicate_claim"]["ok"] = True
    elif corruption == "desktop_claim":
        changed["desktop_ui_tested"] = True
    with pytest.raises(AssertionError):
        PROBE["validate_report"](changed)


def test_saved_evidence_contains_no_credentials_ids_or_machine_paths(report):
    serialized = json.dumps(report)
    for forbidden in (
        "session_token",
        "admin_token",
        "lease_token",
        "session_id",
        "agent_id",
        "project_id",
        "root_path",
        "data_dir",
    ):
        assert forbidden not in serialized
    assert not re.search(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", serialized)
    assert not re.search(r"[A-Za-z]:[\\/]", serialized)


@pytest.mark.parametrize(
    ("statuses", "expected", "polls"),
    [
        (["starting", "connected"], "connected", 2),
        (["starting"], "mcp_startup_timeout", 2),
        (["failed"], "mcp_not_connected", 1),
        (["starting-with-error"], "tool_discovery_error", 1),
        (["private-unrecognized-status"], "mcp_status_unavailable", 1),
    ],
)
def test_native_mcp_polls_only_starting(monkeypatch, statuses, expected, polls):
    host_type = PROBE["NativeHost"]
    host = object.__new__(host_type)
    host.use_registered_config = True
    clock = [0.0]
    calls = []

    def sleep(seconds):
        clock[0] += seconds

    def send(method, params, *, timeout=None):
        if method == "thread/start":
            return {"thread": {"id": "stub"}}
        assert method == "mcpServerStatus/list"
        calls.append(timeout)
        runtime = statuses[min(len(statuses), len(calls)) - 1]
        tools_error = None
        if runtime == "starting-with-error":
            runtime, tools_error = "starting", "private-discovery-error"
        return {
            "data": [
                {
                    "name": "agentsync",
                    "runtimeStatus": runtime,
                    "authStatus": "unsupported",
                    "toolsError": tools_error,
                    "tools": {},
                }
            ]
        }

    globals_ = host_type.start.__globals__
    monkeypatch.setitem(globals_, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep))
    monkeypatch.setitem(globals_, "MCP_STATUS_TIMEOUT", 0.5)
    host.send = send
    observations = []
    if expected == "connected":
        assert host.start(observations) == ("stub", "connected", [])
    else:
        with pytest.raises(PROBE["NativeHostBlocked"]) as error:
            host.start(observations)
        assert error.value.reason == expected
    assert len(calls) == polls == len(observations)
    assert all(0 < timeout <= 0.5 for timeout in calls)
    assert "private-" not in json.dumps(observations)

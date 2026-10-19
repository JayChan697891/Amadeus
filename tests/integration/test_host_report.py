"""Validate saved native-run evidence; these tests are not live host acceptance."""

import copy
import json
import re
import runpy
from pathlib import Path

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

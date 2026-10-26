"""Keep the release design complete without manufacturing execution evidence."""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "docs/acceptance/requirements.json").read_text(encoding="utf-8"))
REQUIREMENTS = MANIFEST["requirements"]
CODEX_COMPONENT_PATHS = {
    "tests/unit/test_codex_events.py",
    "tests/unit/test_codex_adapter.py",
    "tests/integration/test_codex_adapter_core_boundary.py",
}


def test_register_matches_authoritative_formal_requirement_tables():
    specification = (ROOT / "docs/SPECIFICATION.md").read_text(encoding="utf-8")
    # Later prose repeats the task brief; only section IV defines the formal IDs.
    formal_tables = specification.split("## 四、42 项详细开发任务", 1)[1].split("## 五、", 1)[0]
    formal_ids = re.findall(r"^\|\s*(M[0-9]-[0-9]{2})\s*\|", formal_tables, re.MULTILINE)
    recorded_ids = [requirement["id"] for requirement in REQUIREMENTS]
    assert len(formal_ids) == len(set(formal_ids)) == 42
    assert len(recorded_ids) == len(set(recorded_ids)) == MANIFEST["requirement_count"] == 42
    assert set(recorded_ids) == set(formal_ids)
    assert {requirement["milestone"] for requirement in REQUIREMENTS} == {
        f"M{number}" for number in range(10)
    }


@pytest.mark.parametrize("requirement", REQUIREMENTS, ids=lambda item: item["id"])
def test_requirement_has_reviewable_case_and_evidence_design(requirement):
    for field in ("title", "acceptance", "method", "expected", "evidence"):
        assert isinstance(requirement[field], str) and requirement[field].strip(), field
    assert requirement["milestone"] == requirement["id"].split("-", 1)[0]
    assert requirement["layers"]
    assert requirement["planned_cases"]
    for case in requirement["planned_cases"]:
        for field in ("id", "title", "method", "expected"):
            assert isinstance(case[field], str) and case[field].strip(), field


def test_all_cases_are_unique_and_original_scenarios_are_bidirectionally_mapped():
    case_ids = [case["id"] for item in REQUIREMENTS for case in item["planned_cases"]]
    assert len(case_ids) == len(set(case_ids))
    scenarios = MANIFEST["scenarios"]
    expected_ids = {f"T{number:02}" for number in range(1, 17)}
    assert len(scenarios) == len(expected_ids)
    assert {scenario["id"] for scenario in scenarios} == expected_ids
    assert {item for req in REQUIREMENTS for item in req["original_scenarios"]} == expected_ids
    for scenario in scenarios:
        assert scenario["requirements"], scenario["id"]
        assert set(scenario["requirements"]) == {
            requirement["id"]
            for requirement in REQUIREMENTS
            if scenario["id"] in requirement["original_scenarios"]
        }
        for field in ("title", "expected", "evidence"):
            assert isinstance(scenario[field], str) and scenario[field].strip(), field


@pytest.mark.parametrize("requirement", REQUIREMENTS, ids=lambda item: item["id"])
def test_existing_selectors_point_to_actual_repository_tests(requirement):
    for selector in requirement["existing_tests"]:
        path_text, *nodes = selector.split("::")
        path = (ROOT / path_text).resolve()
        assert path.is_relative_to(ROOT / "tests"), selector
        assert path.is_file(), selector
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node_name in nodes:
            # Parameter IDs are runtime values; the source function must exist.
            base_name = node_name.split("[", 1)[0]
            assert base_name in {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            }, selector


def test_static_design_does_not_imply_any_acceptance_was_executed():
    # Actual execution belongs in immutable per-run reports, not the design register.
    for item in [*REQUIREMENTS, *MANIFEST["scenarios"]]:
        assert item["execution_status"] == "not_run", item["id"]
    for requirement in REQUIREMENTS:
        assert requirement["coverage"] in MANIFEST["coverage_vocabulary"]
        assert requirement["release_gate"] == "required_for_v1_0"


def test_codex_protocol_parser_is_partial_and_keeps_real_start_requirements():
    item = next(item for item in REQUIREMENTS if item["id"] == "M6-03")
    assert item["coverage"] == "partial"
    assert set(item["existing_tests"]) == {
        "tests/unit/test_codex_events.py::test_complete_single_turn_requires_exit_zero_and_keeps_protocol_scope",
        "tests/unit/test_codex_events.py::test_exit_observation_prevents_protocol_only_success",
        "tests/unit/test_codex_events.py::test_upstream_errors_are_static_failed_observations",
        "tests/unit/test_codex_events.py::test_only_completed_agent_messages_are_projected_and_usage_can_be_absent",
        "tests/unit/test_codex_adapter.py::test_default_capabilities_do_not_authorize_or_start_any_client",
        "tests/unit/test_codex_adapter.py::test_factory_capture_reuse_is_unknown_without_cancelling_first_owner",
        "tests/unit/test_codex_adapter.py::test_factory_deadline_late_handle_cleanup_does_not_rewrite_unknown",
        "tests/integration/test_codex_adapter_core_boundary.py::test_codex_protocol_fixture_success_preserves_complete_core_and_reopened_state",
    }
    assert item["execution_status"] == "not_run"
    assert item["original_scenarios"] == ["T13", "T14"]
    assert "authorized subscription" in item["method"]
    assert "artifact validated" in item["acceptance"]
    for scenario in MANIFEST["scenarios"]:
        if scenario["id"] in {"T13", "T14"}:
            assert scenario["execution_status"] == "not_run"


def test_claude_protocol_components_remain_partial_without_real_client_acceptance():
    item = next(row for row in REQUIREMENTS if row["id"] == "M6-04")
    assert item["coverage"] == "partial"
    assert item["execution_status"] == "not_run"
    assert set(item["existing_tests"]) == {
        "tests/unit/test_claude_events.py::test_literal_complete_response_needs_exit_zero_and_is_unverified",
        "tests/unit/test_claude_events.py::test_unsuccessful_observations_never_expose_final_text",
        "tests/unit/test_claude_events.py::test_last_assistant_incomplete_stop_cannot_be_hidden_by_optimistic_result",
        "tests/unit/test_inspect_claude_events.py::test_cli_summarizes_explicit_fixture_with_no_raw_text_or_verified_claims",
        "tests/unit/test_claude_adapter.py::test_default_adapter_contract_is_unverified_and_start_unsupported",
        "tests/unit/test_claude_adapter.py::test_reused_capture_is_rejected_without_stopping_first_run_parent",
        "tests/unit/test_claude_adapter.py::test_factory_deadline_freezes_unknown_then_cleans_only_fresh_late_parent",
        "tests/integration/test_claude_adapter_core_boundary.py::test_claude_protocol_success_preserves_actual_core_and_reopened_state",
    }
    assert item["original_scenarios"] == ["T13", "T14"]
    assert "Claude Agent SDK/CLI" in item["method"]
    assert "real evidence" in item["acceptance"]
    assert len(REQUIREMENTS) == 42 and len(MANIFEST["scenarios"]) == 16
    assert all(row["execution_status"] == "not_run" for row in REQUIREMENTS)
    assert all(row["execution_status"] == "not_run" for row in MANIFEST["scenarios"])
    cursor = next(row for row in REQUIREMENTS if row["id"] == "M6-05")
    assert cursor["coverage"] == "missing" and cursor["existing_tests"] == []


def test_codex_host_factory_components_keep_actual_client_acceptance_unverified():
    item = next(item for item in REQUIREMENTS if item["id"] == "M6-03")
    assert item["coverage"] == "partial"
    assert item["execution_status"] == "not_run"
    assert len(item["existing_tests"]) == 8
    assert {
        "tests/unit/test_codex_adapter.py::test_default_capabilities_do_not_authorize_or_start_any_client",
        "tests/unit/test_codex_adapter.py::test_factory_capture_reuse_is_unknown_without_cancelling_first_owner",
        "tests/unit/test_codex_adapter.py::test_factory_deadline_late_handle_cleanup_does_not_rewrite_unknown",
        "tests/integration/test_codex_adapter_core_boundary.py::test_codex_protocol_fixture_success_preserves_complete_core_and_reopened_state",
    } <= set(item["existing_tests"])
    assert all(
        "::" in selector and selector.split("::")[0] in CODEX_COMPONENT_PATHS
        for selector in item["existing_tests"]
    )
    assert "public supported Codex SDK/CLI" in item["method"]
    assert "artifact validated" in item["acceptance"]
    assert len(REQUIREMENTS) == 42 and len(MANIFEST["scenarios"]) == 16
    assert all(row["execution_status"] == "not_run" for row in REQUIREMENTS)
    for requirement_id in ("M6-04", "M6-05"):
        missing = next(row for row in REQUIREMENTS if row["id"] == requirement_id)
        if requirement_id == "M6-04":
            assert missing["coverage"] == "partial" and len(missing["existing_tests"]) == 8
        else:
            assert missing["coverage"] == "missing" and missing["existing_tests"] == []
        assert missing["execution_status"] == "not_run"


def test_mock_foundation_is_partial_component_coverage_not_real_client_acceptance():
    by_id = {requirement["id"]: requirement for requirement in REQUIREMENTS}
    mock_paths = {
        "M6-01": {"tests/unit/test_adapters.py"},
        "M6-02": {
            "tests/unit/test_adapters.py",
            "tests/integration/test_mock_adapter_core_boundary.py",
            "tests/unit/test_mock_run_manager.py",
            "tests/integration/test_mock_run_manager_core_boundary.py",
        },
    }
    for requirement_id in ("M6-01", "M6-02"):
        item = by_id[requirement_id]
        assert item["coverage"] == "partial"
        assert item["existing_tests"]
        assert all("::" in selector for selector in item["existing_tests"])
        assert all(
            selector.split("::")[0] in mock_paths[requirement_id]
            for selector in item["existing_tests"]
        )
        assert item["execution_status"] == "not_run"
    assert {
        "tests/unit/test_mock_run_manager.py::test_global_running_limit_is_atomic_across_workers",
        "tests/unit/test_mock_run_manager.py::test_same_task_concurrently_started_on_workers_has_one_active_winner",
        "tests/unit/test_mock_run_manager.py::test_replay_precedes_running_and_history_capacity",
        "tests/integration/test_mock_run_manager_core_boundary.py::test_dispatch_plan_to_mock_manager_preserves_complete_core_snapshot",
    } <= set(by_id["M6-02"]["existing_tests"])
    assert by_id["M6-03"]["coverage"] == "partial"
    assert all(
        "::" in selector and selector.split("::")[0] in CODEX_COMPONENT_PATHS
        for selector in by_id["M6-03"]["existing_tests"]
    )
    assert by_id["M6-03"]["execution_status"] == "not_run"
    for requirement_id in ("M6-04", "M6-05"):
        item = by_id[requirement_id]
        if requirement_id == "M6-04":
            assert item["coverage"] == "partial" and len(item["existing_tests"]) == 8
        else:
            assert item["coverage"] == "missing" and item["existing_tests"] == []
        assert item["execution_status"] == "not_run"
    real_start = next(scenario for scenario in MANIFEST["scenarios"] if scenario["id"] == "T13")
    assert set(real_start["requirements"]) == {"M6-03", "M6-04", "M6-05"}
    assert real_start["execution_status"] == "not_run"


def test_planning_foundations_remain_partial_without_real_relay_or_execution_claims():
    by_id = {requirement["id"]: requirement for requirement in REQUIREMENTS}
    paths = {
        "M7-01": {
            "tests/unit/test_scheduling.py",
            "tests/integration/test_scheduling_core_boundary.py",
        },
        "M7-02": {
            "tests/unit/test_dispatch_planning.py",
            "tests/integration/test_dispatch_planning_core_boundary.py",
        },
    }
    for requirement_id, allowed_paths in paths.items():
        item = by_id[requirement_id]
        assert item["coverage"] == "partial"
        assert item["existing_tests"]
        assert all(
            "::" in selector and selector.split("::")[0] in allowed_paths
            for selector in item["existing_tests"]
        )
        assert item["execution_status"] == "not_run" and item["original_scenarios"] == []
    assert "real authorized agents" in by_id["M7-02"]["acceptance"]
    assert by_id["M6-03"]["coverage"] == "partial"
    assert all(
        "::" in selector and selector.split("::")[0] in CODEX_COMPONENT_PATHS
        for selector in by_id["M6-03"]["existing_tests"]
    )
    assert by_id["M6-04"]["coverage"] == "partial"
    assert len(by_id["M6-04"]["existing_tests"]) == 8
    assert by_id["M6-04"]["execution_status"] == "not_run"
    for requirement_id in ("M6-05", "M7-03", "M7-04"):
        assert by_id[requirement_id]["coverage"] == "missing"
        assert by_id[requirement_id]["existing_tests"] == []

"""Keep the release design complete without manufacturing execution evidence."""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "docs/acceptance/requirements.json").read_text(encoding="utf-8"))
REQUIREMENTS = MANIFEST["requirements"]


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

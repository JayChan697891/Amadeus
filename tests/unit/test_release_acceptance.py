"""Runner policy tests; these mocks do not represent actual-client acceptance."""

import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_acceptance", Path(__file__).resolve().parents[2] / "tools/release_acceptance.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.2.0a2"\n', encoding="utf-8")
    monkeypatch.setattr(runner, "git_value", lambda _repo, *_args: "test-revision")
    return repo


def passing_check(run):
    log = run / "sample.log"
    log.write_text("actual local subprocess evidence", encoding="utf-8")
    return {
        "id": "sample",
        "status": "pass",
        "log": "sample.log",
        "log_sha256": runner.sha256(log),
        "exit_code": 0,
        "provenance": "local_process",
    }


def test_design_mode_never_executes_and_preserves_manifest(repository, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Design mode executed a validation subprocess")

    monkeypatch.setattr(runner, "execute", forbidden)
    manifest = repository / "docs/acceptance/requirements.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"requirements": [{"id": "M9-01", "execution_status": "not_run"}]}')
    run = runner.collect(repository, tmp_path / "evidence", run_checks=False, package_install=False)
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert all(check["status"] == "not_run" for check in report["checks"])
    assert report["release_gate"]["status"] == "blocked"
    assert not report["release_gate"]["formal_acceptance"]
    assert json.loads((run / "requirements.json").read_text()) == json.loads(manifest.read_text())
    assert (run / "Release-Acceptance-Report.md").is_file()


def test_process_attempt_record_exists_before_command_and_survives_completion(
    repository, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    record_path = run / "logs" / "sample.process.json"

    def command_result(*_args, **_kwargs):
        started = json.loads(record_path.read_text(encoding="utf-8"))
        assert started["phase"] == "started"
        assert started["outcome"] == "unknown"
        assert started["formal_acceptance"] is False
        assert started["check_id"] == "sample"
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(runner.subprocess, "run", command_result)
    result = runner.execute("sample", ["local-test-command"], repository, run, scratch)
    saved = json.loads(record_path.read_text(encoding="utf-8"))
    assert saved["phase"] == "finished"
    assert saved["outcome"] == "exited" and saved["error_type"] is None
    assert saved["result"] == result
    assert saved["formal_acceptance"] is False
    assert saved["junit_validated"] is False
    assert result["status"] == "pass"


@pytest.mark.parametrize("existing", [False, True])
def test_execute_without_scratch_prepares_default_directory_and_keeps_existing_files(
    repository, tmp_path, monkeypatch, existing
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    temporary = run / "tmp"
    if existing:
        temporary.mkdir()
        (temporary / "keep.txt").write_text("existing temporary data", encoding="utf-8")

    def local_command(_command, **kwargs):
        assert temporary.is_dir()
        assert kwargs["env"]["TMP"] == str(temporary)
        assert kwargs["env"]["TEMP"] == str(temporary)
        assert kwargs["env"]["TMPDIR"] == str(temporary)
        kwargs["stdout"].write(b"default scratch command finished\n")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(runner.subprocess, "run", local_command)
    result = runner.execute("sample", ["local-test-command"], repository, run)
    assert result["status"] == "pass" and result["exit_code"] == 0
    assert (run / result["log"]).read_text(encoding="utf-8") == "default scratch command finished\n"
    remaining = list(temporary.iterdir())
    if existing:
        assert remaining == [temporary / "keep.txt"]
        assert remaining[0].read_text(encoding="utf-8") == "existing temporary data"
    else:
        assert not remaining


def test_execute_default_temporary_path_does_not_replace_existing_file(
    repository, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    (run / "tmp").write_text("caller-owned file", encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Command started with an invalid temporary directory")

    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    with pytest.raises(OSError):
        runner.execute("sample", ["local-test-command"], repository, run)
    assert (run / "tmp").read_text(encoding="utf-8") == "caller-owned file"


@pytest.mark.parametrize("outcome", ["nonzero", "launch_error", "timeout"])
def test_finished_attempt_preserves_failed_process_result(
    repository, tmp_path, monkeypatch, outcome
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    def command_result(command, **_kwargs):
        if outcome == "launch_error":
            raise OSError("unit-only launch failure")
        if outcome == "timeout":
            raise runner.subprocess.TimeoutExpired(command, 900)
        return type("Result", (), {"returncode": 7})()

    monkeypatch.setattr(runner.subprocess, "run", command_result)
    result = runner.execute("sample", ["local-test-command"], repository, run, scratch)
    saved = json.loads((run / "logs/sample.process.json").read_text(encoding="utf-8"))
    assert saved["phase"] == "finished" and saved["result"] == result
    expected_outcome = {
        "nonzero": "exited",
        "launch_error": "runner_error",
        "timeout": "timed_out",
    }[outcome]
    expected_error = {"nonzero": None, "launch_error": "OSError", "timeout": "TimeoutExpired"}[
        outcome
    ]
    assert saved["outcome"] == expected_outcome and saved["error_type"] == expected_error
    assert result["status"] == "fail"
    assert result["exit_code"] == (7 if outcome == "nonzero" else None)
    assert saved["formal_acceptance"] is False and saved["junit_validated"] is False
    assert not list(scratch.iterdir())
    assert not list((run / "logs").glob(".attempt-*.tmp"))


def test_interrupted_attempt_does_not_claim_command_or_junit_completion(
    repository, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner.subprocess, "run", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.execute("sample", ["local-test-command"], repository, run, scratch)
    saved = json.loads((run / "logs/sample.process.json").read_text(encoding="utf-8"))
    assert saved["phase"] == "started" and "result" not in saved
    assert saved["outcome"] == "unknown"
    assert saved["formal_acceptance"] is False and saved["junit_validated"] is False
    assert not list(scratch.iterdir())


def test_attempt_record_contains_only_redacted_command_metadata(repository, tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    def command_result(*_args, **_kwargs):
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(runner.subprocess, "run", command_result)
    runner.execute(
        "sample", ["local-test-command", "password=unit-placeholder"], repository, run, scratch
    )
    text = (run / "logs/sample.process.json").read_text(encoding="utf-8")
    assert "unit-placeholder" not in text and "[REDACTED]" in text


def test_record_write_failure_leaves_previous_record_and_does_not_start_command(
    repository, tmp_path, monkeypatch
):
    run = tmp_path / "run"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    record = run / "logs/sample.process.json"
    previous = '{"phase":"previous-completed-attempt"}\n'
    record.write_text(previous, encoding="utf-8")

    def write_failure(*_args, **_kwargs):
        raise OSError("unit-only replacement failure")

    def forbidden_command(*_args, **_kwargs):
        pytest.fail("Command started without its attempt record")

    monkeypatch.setattr(runner.os, "replace", write_failure)
    monkeypatch.setattr(runner.subprocess, "run", forbidden_command)
    with pytest.raises(OSError, match="unit-only replacement failure"):
        runner.execute("sample", ["local-test-command"], repository, run, scratch)
    assert record.read_text(encoding="utf-8") == previous
    assert not list((run / "logs").glob(".attempt-*.tmp"))


def test_completed_attempt_is_preserved_when_later_check_is_interrupted(
    repository, tmp_path, monkeypatch
):
    output = tmp_path / "evidence"

    def synthetic_command(command, **kwargs):
        if "pytest" in command:
            xml_path = Path(command[command.index("--junitxml") + 1])
            xml_path.write_text(
                '<testsuite tests="1"><testcase name="synthetic-unit-observation"/></testsuite>',
                encoding="utf-8",
            )
            kwargs["stdout"].write(b"synthetic unit command finished\n")
            return type("Result", (), {"returncode": 0})()
        raise KeyboardInterrupt

    monkeypatch.setattr(runner.subprocess, "run", synthetic_command)
    with pytest.raises(KeyboardInterrupt):
        runner.collect(repository, output, run_checks=True, package_install=False)
    run = next(output.glob("release-*"))
    completed = json.loads((run / "logs/pytest.process.json").read_text(encoding="utf-8"))
    interrupted = json.loads((run / "logs/ruff.process.json").read_text(encoding="utf-8"))
    assert completed["phase"] == "finished" and completed["result"]["exit_code"] == 0
    assert interrupted["phase"] == "started" and "result" not in interrupted
    assert completed["formal_acceptance"] is False and interrupted["formal_acceptance"] is False
    assert (run / "junit.xml").is_file()
    assert not (run / "report.json").exists(), "Partial records must not become final acceptance"
    assert not list(output.glob(".scratch-*"))


def test_each_run_uses_new_evidence_directory(repository, tmp_path):
    first = runner.collect(
        repository, tmp_path / "evidence", run_checks=False, package_install=False
    )
    (first / "keep.txt").write_text("previous evidence")
    second = runner.collect(
        repository, tmp_path / "evidence", run_checks=False, package_install=False
    )
    assert first != second
    assert (first / "keep.txt").read_text() == "previous evidence"
    assert repository not in first.parents


def test_all_local_checks_passing_still_cannot_accept_release(tmp_path):
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"]
    assert not gate["formal_acceptance"]
    assert "autonomous_relay" in gate["blockers"]
    assert "real_claude_adapter" in gate["blockers"]


@pytest.mark.parametrize("status", ["fail", "not_run", "restricted", "unverified"])
def test_nonpassing_status_never_counts_as_local_success(tmp_path, status):
    check = passing_check(tmp_path)
    check["status"] = status
    gate = runner.release_gate([check], tmp_path)
    assert not gate["local_checks_passed"]
    assert gate["invalid_or_incomplete_checks"] == ["sample"]


@pytest.mark.parametrize("kind", ["modified", "missing", "mock", "nonzero", "outside"])
def test_missing_tampered_or_mock_evidence_is_rejected(tmp_path, kind):
    run = tmp_path / "run"
    run.mkdir()
    check = passing_check(run)
    if kind == "modified":
        (run / "sample.log").write_text("replaced")
    elif kind == "missing":
        (run / "sample.log").unlink()
    elif kind == "mock":
        check["provenance"] = "mock"
    elif kind == "nonzero":
        check["exit_code"] = 1
    else:
        outside = tmp_path / "outside.log"
        outside.write_text("external evidence")
        check.update(log="../outside.log", log_sha256=runner.sha256(outside))
    assert not runner.release_gate([check], run)["local_checks_passed"]


def test_no_checks_is_not_success(tmp_path):
    assert not runner.release_gate([], tmp_path)["local_checks_passed"]


def test_junit_preserves_failures_errors_and_skips(tmp_path):
    xml = tmp_path / "junit.xml"
    xml.write_text(
        "<testsuites><testsuite><testcase/><testcase><skipped/></testcase>"
        "<testcase><failure/></testcase><testcase><error/></testcase></testsuite></testsuites>"
    )
    assert runner.junit_counts(xml) == {"tests": 4, "failures": 1, "errors": 1, "skipped": 1}


def test_passing_pytest_without_junit_fails(repository, tmp_path, monkeypatch):
    def fake_execute(check_id, command, repo, run, scratch):
        item = passing_check(run)
        item.update(id=check_id, command=command)
        return item

    monkeypatch.setattr(runner, "execute", fake_execute)
    run = runner.collect(repository, tmp_path / "evidence", run_checks=True, package_install=False)
    report = json.loads((run / "report.json").read_text())
    test = next(check for check in report["checks"] if check["id"] == "pytest")
    assert test["status"] == "fail"
    assert "missing" in test["error"]


def test_scratch_secrets_are_not_persisted(repository, tmp_path, monkeypatch):
    def fake_execute(check_id, command, repo, run, scratch):
        (scratch / "auth.json").write_text('{"token":"never-archive"}')
        return {"id": check_id, "status": "fail", "command": command}

    monkeypatch.setattr(runner, "execute", fake_execute)
    output = tmp_path / "evidence"
    run = runner.collect(repository, output, run_checks=True, package_install=False)
    assert not list(output.glob(".scratch-*"))
    assert not list(run.rglob("auth.json"))
    report = json.loads((run / "report.json").read_text())
    assert not any("auth.json" in entry["path"] for entry in report["artifacts"])


@pytest.mark.parametrize("relative", [".", "scratch", "nested/../scratch"])
def test_scratch_root_rejects_source_before_creating_any_directories(
    repository, tmp_path, relative
):
    output = tmp_path / "uncreated" / "reports"
    with pytest.raises(ValueError, match="Scratch.*outside"):
        runner.collect(
            repository,
            output,
            run_checks=False,
            package_install=False,
            scratch_root=repository / relative,
        )
    assert not output.parent.exists()
    assert not (repository / "scratch").exists()
    assert not (repository / "nested").exists()


def test_malformed_requirements_manifest_keeps_release_blocked(repository, tmp_path):
    manifest = repository / "docs/acceptance/requirements.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"requirements":false}')
    run = runner.collect(repository, tmp_path / "evidence", run_checks=False, package_install=False)
    report = json.loads((run / "report.json").read_text())
    assert report["requirements_manifest_error"]
    assert not report["release_gate"]["formal_acceptance"]


def test_output_cannot_contaminate_source(repository):
    with pytest.raises(ValueError, match="outside"):
        runner.collect(repository, repository / "evidence", run_checks=False, package_install=False)


def test_missing_manifest_is_explicit_and_cannot_accept(repository, tmp_path):
    run = runner.collect(repository, tmp_path / "evidence", run_checks=False, package_install=False)
    report = json.loads((run / "report.json").read_text())
    assert report["requirements"] == []
    assert report["coverage"]["requirements_manifest"] == "not_run"
    assert not report["release_gate"]["formal_acceptance"]
    assert "No valid requirements manifest" in (run / "Release-Acceptance-Report.md").read_text()


def test_requirement_rows_preserve_nonacceptance_with_exact_component_evidence(tmp_path):
    (tmp_path / "junit.xml").write_text(
        '<testsuites><testsuite><testcase classname="tests.unit.test_demo" name="test_read[a]"/>'
        '<testcase classname="tests.unit.test_demo" name="test_read[b]"><skipped/></testcase>'
        '<testcase classname="tests.unit.test_demo" name="test_reader"/>'
        '<testcase classname="tests.unit.other" name="test_read"/></testsuite></testsuites>'
    )
    manifest = {
        "requirements": [
            {
                "id": "M6-03",
                "title": "Real Codex",
                "execution_status": "passed",
                "existing_tests": ["tests/unit/test_demo.py::test_read"],
            }
        ]
    }
    row = runner.requirement_results(manifest, tmp_path)[0]
    assert row["execution_status"] == "not_run"
    assert row["declared_execution_status"] == "passed"
    assert row["acceptance_evidence_status"] == "unverified"
    assert row["component_evidence"][0]["observations"][0]["counts"] == {
        "tests": 2,
        "passed": 1,
        "failures": 0,
        "errors": 0,
        "skipped": 1,
    }


@pytest.mark.parametrize("junit_name", ["junit.xml", "wheel-junit.xml", "sdist-junit.xml"])
@pytest.mark.parametrize("include_matches", [False, True], ids=["neighbors-only", "components"])
def test_synthetic_claude_protocol_junit_never_promotes_real_client_or_relay(
    tmp_path, junit_name, include_matches
):
    """Generated fixture XML is not an actual Claude session or CLI capture."""
    manifest_path = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parser_names = [
        "test_literal_complete_response_needs_exit_zero_and_is_unverified",
        "test_unsuccessful_observations_never_expose_final_text",
        "test_last_assistant_incomplete_stop_cannot_be_hidden_by_optimistic_result",
    ]
    inspector_name = "test_cli_summarizes_explicit_fixture_with_no_raw_text_or_verified_claims"
    declared_cases = [
        ("tests.unit.test_claude_events", parser_names[0]),
        ("tests.unit.test_claude_events", parser_names[1] + "[synthetic-error]"),
        ("tests.unit.test_claude_events", parser_names[2] + "[max_tokens]"),
        ("tests.unit.test_claude_events", parser_names[2] + "[refusal]"),
        ("tests.unit.test_inspect_claude_events", inspector_name),
    ]
    cases = [(module, name.split("[", 1)[0] + "_extra") for module, name in declared_cases]
    cases += [("tests.unit.other", name) for _, name in declared_cases]
    # A neighboring function with its own parameter is not a declared function.
    cases += [("tests.unit.test_claude_events", parser_names[2] + "_extra[max_tokens]")]
    if include_matches:
        cases += declared_cases
    (tmp_path / junit_name).write_text(
        "<testsuites><testsuite name='synthetic-claude-protocol-only'>"
        + "".join(f'<testcase classname="{module}" name="{name}"/>' for module, name in cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    rows = runner.requirement_results(manifest, tmp_path)
    by_id = {row["id"]: row for row in rows}
    row = by_id["M6-04"]
    assert row["coverage"] == "partial"
    assert len(row["component_evidence"]) == 4
    total = 0
    for component in row["component_evidence"]:
        expected = (
            0
            if not include_matches
            else 2
            if component["selector"].endswith(parser_names[2])
            else 1
        )
        assert component["observations"] == [
            {
                "junit": junit_name,
                "counts": {
                    "tests": expected,
                    "passed": expected,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                },
            }
        ]
        total += expected
    assert total == (5 if include_matches else 0)
    assert row["acceptance_evidence_status"] == "unverified"
    assert len(rows) == 42 and all(item["execution_status"] == "not_run" for item in rows)
    for requirement_id in ("M6-01", "M6-02", "M6-03", "M7-01", "M7-02"):
        assert all(
            all(value == 0 for value in observation["counts"].values())
            for component in by_id[requirement_id]["component_evidence"]
            for observation in component["observations"]
        )
    assert by_id["M6-03"]["acceptance_evidence_status"] == "unverified"
    assert by_id["M6-05"]["coverage"] == "missing"
    assert by_id["M6-05"]["component_evidence"] == []
    assert by_id["M6-05"]["acceptance_evidence_status"] == "unverified"
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"] is True
    assert gate["formal_acceptance"] is False and gate["status"] == "blocked"
    assert {"real_claude_adapter", "autonomous_relay"} <= set(gate["blockers"])


@pytest.mark.parametrize("junit_name", ["junit.xml", "wheel-junit.xml", "sdist-junit.xml"])
def test_synthetic_codex_factory_and_core_records_do_not_verify_real_client(tmp_path, junit_name):
    """Synthetic host-factory/Core fixture records are not actual client captures."""
    manifest_path = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [
        "test_default_capabilities_do_not_authorize_or_start_any_client",
        "test_factory_capture_reuse_is_unknown_without_cancelling_first_owner",
        "test_factory_deadline_late_handle_cleanup_does_not_rewrite_unknown",
    ]
    core_name = "test_codex_protocol_fixture_success_preserves_complete_core_and_reopened_state"
    cases = [("tests.unit.test_codex_adapter", name) for name in names]
    cases += [
        ("tests.integration.test_codex_adapter_core_boundary", core_name + "[pending]"),
        ("tests.integration.test_codex_adapter_core_boundary", core_name + "[running]"),
    ]
    # Neighboring test names and wrong classes never satisfy an exact selector.
    cases += [("tests.unit.test_codex_adapter", name + "_extra") for name in names]
    cases += [("tests.unit.other", name) for name in names]
    cases += [
        ("tests.integration.test_codex_adapter_core_boundary", core_name + "_extra[pending]"),
        ("tests.integration.other", core_name + "[running]"),
    ]
    (tmp_path / junit_name).write_text(
        "<testsuites><testsuite name='synthetic-host-factory-core-only'>"
        + "".join(f'<testcase classname="{module}" name="{name}"/>' for module, name in cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    rows = runner.requirement_results(manifest, tmp_path)
    by_id = {row["id"]: row for row in rows}
    row = by_id["M6-03"]
    assert row["coverage"] == "partial"
    assert len(row["component_evidence"]) == 8
    counts = []
    for component in row["component_evidence"]:
        selector = component["selector"]
        expected = (
            0
            if selector.startswith("tests/unit/test_codex_events.py::")
            else 2
            if selector.startswith("tests/integration/test_codex_adapter_core_boundary.py::")
            else 1
        )
        assert component["observations"] == [
            {
                "junit": junit_name,
                "counts": {
                    "tests": expected,
                    "passed": expected,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                },
            }
        ]
        counts.append(expected)
    assert sum(counts) == 5
    assert row["acceptance_evidence_status"] == "unverified"
    assert len(rows) == 42 and all(item["execution_status"] == "not_run" for item in rows)
    for requirement_id in ("M6-01", "M6-02", "M7-01", "M7-02"):
        assert all(
            all(value == 0 for value in observation["counts"].values())
            for component in by_id[requirement_id]["component_evidence"]
            for observation in component["observations"]
        )
    for requirement_id in ("M6-04", "M6-05"):
        item = by_id[requirement_id]
        if requirement_id == "M6-04":
            assert item["coverage"] == "partial" and len(item["component_evidence"]) == 4
            assert all(
                all(value == 0 for value in observation["counts"].values())
                for component in item["component_evidence"]
                for observation in component["observations"]
            )
        else:
            assert item["coverage"] == "missing" and item["component_evidence"] == []
        assert item["acceptance_evidence_status"] == "unverified"
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"] is True
    assert gate["formal_acceptance"] is False and gate["status"] == "blocked"
    assert {"real_codex_adapter", "autonomous_relay"} <= set(gate["blockers"])


@pytest.mark.parametrize("junit_name", ["junit.xml", "wheel-junit.xml", "sdist-junit.xml"])
def test_protocol_only_codex_junit_cannot_promote_real_start_or_relay(tmp_path, junit_name):
    """Synthetic passing parser records are explicitly not actual CLI captures."""
    manifest_path = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = [
        "test_complete_single_turn_requires_exit_zero_and_keeps_protocol_scope",
        "test_exit_observation_prevents_protocol_only_success[None-incomplete]",
        "test_upstream_errors_are_static_failed_observations[event0]",
        "test_only_completed_agent_messages_are_projected_and_usage_can_be_absent",
    ]
    cases = [("tests.unit.test_codex_events", name) for name in names]
    cases += [
        ("tests.unit.other", names[0]),
        ("tests.unit.test_codex_events", names[0] + "_extra"),
    ]
    (tmp_path / junit_name).write_text(
        "<testsuites><testsuite name='synthetic-protocol-only'>"
        + "".join(f'<testcase classname="{module}" name="{name}"/>' for module, name in cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    rows = runner.requirement_results(manifest, tmp_path)
    by_id = {row["id"]: row for row in rows}
    row = by_id["M6-03"]
    assert row["coverage"] == "partial"
    assert len(row["component_evidence"]) == 8
    parser_components = [
        component
        for component in row["component_evidence"]
        if component["selector"].startswith("tests/unit/test_codex_events.py::")
    ]
    assert len(parser_components) == 4
    for component in row["component_evidence"]:
        expected = 1 if component in parser_components else 0
        assert component["observations"] == [
            {
                "junit": junit_name,
                "counts": {
                    "tests": expected,
                    "passed": expected,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                },
            }
        ]
    assert row["acceptance_evidence_status"] == "unverified"
    assert len(rows) == 42 and all(item["execution_status"] == "not_run" for item in rows)
    for requirement_id in ("M6-01", "M6-02", "M7-01", "M7-02"):
        assert all(
            all(value == 0 for value in observation["counts"].values())
            for component in by_id[requirement_id]["component_evidence"]
            for observation in component["observations"]
        )
    for requirement_id in ("M6-04", "M6-05"):
        item = by_id[requirement_id]
        if requirement_id == "M6-04":
            assert item["coverage"] == "partial" and len(item["component_evidence"]) == 4
            assert all(
                all(value == 0 for value in observation["counts"].values())
                for component in item["component_evidence"]
                for observation in component["observations"]
            )
        else:
            assert item["coverage"] == "missing" and item["component_evidence"] == []
        assert item["acceptance_evidence_status"] == "unverified"
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"] is True
    assert gate["formal_acceptance"] is False and gate["status"] == "blocked"
    assert {"real_codex_adapter", "autonomous_relay"} <= set(gate["blockers"])


@pytest.mark.parametrize("junit_name", ["junit.xml", "wheel-junit.xml", "sdist-junit.xml"])
def test_mock_junit_observations_cannot_promote_real_clients_or_formal_acceptance(
    tmp_path, junit_name
):
    manifest_path = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (tmp_path / junit_name).write_text(
        "<testsuites><testsuite>"
        '<testcase classname="tests.unit.test_adapters" '
        'name="test_capabilities_honestly_declare_simulation_and_cancel[True]"/>'
        '<testcase classname="tests.unit.test_adapters" '
        'name="test_unsupported_cancel_and_resume_do_not_change_run"/>'
        '<testcase classname="tests.unit.test_adapters" '
        'name="test_only_explicit_finish_produces_simulated_result[False]"/>'
        '<testcase classname="tests.integration.test_mock_adapter_core_boundary" '
        'name="test_mock_terminal_result_preserves_core_task_and_persisted_state[succeeded-pending]"/>'
        '<testcase classname="tests.unit.test_mock_run_manager" '
        'name="test_global_running_limit_is_atomic_across_workers"/>'
        '<testcase classname="tests.integration.test_mock_run_manager_core_boundary" '
        'name="test_dispatch_plan_to_mock_manager_preserves_complete_core_snapshot"/>'
        '<testcase classname="tests.unit.other" '
        'name="test_capabilities_honestly_declare_simulation_and_cancel[True]"/>'
        '<testcase classname="tests.unit.test_adapters" '
        'name="test_unsupported_cancel_and_resume_do_not_change_run_extra"/>'
        '<testcase classname="tests.unit.other" '
        'name="test_global_running_limit_is_atomic_across_workers"/>'
        '<testcase classname="tests.integration.test_mock_run_manager_core_boundary" '
        'name="test_dispatch_plan_to_mock_manager_preserves_complete_core_snapshot_extra"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    rows = runner.requirement_results(manifest, tmp_path)
    by_id = {row["id"]: row for row in rows}
    assert len(rows) == 42 and all(row["execution_status"] == "not_run" for row in rows)
    for requirement_id in ("M6-01", "M6-02"):
        row = by_id[requirement_id]
        assert row["coverage"] == "partial"
        counts = [
            observation["counts"]
            for component in row["component_evidence"]
            for observation in component["observations"]
        ]
        assert sum(count["passed"] for count in counts) == (2 if requirement_id == "M6-01" else 4)
        assert sum(count["tests"] for count in counts) == (2 if requirement_id == "M6-01" else 4)
        assert row["acceptance_evidence_status"] == "not_run"
    for requirement_id in ("M6-03", "M6-04", "M6-05"):
        row = by_id[requirement_id]
        assert row["coverage"] == ("partial" if requirement_id in {"M6-03", "M6-04"} else "missing")
        if requirement_id in {"M6-03", "M6-04"}:
            assert len(row["component_evidence"]) == (8 if requirement_id == "M6-03" else 4)
            assert all(
                all(value == 0 for value in observation["counts"].values())
                for component in row["component_evidence"]
                for observation in component["observations"]
            )
        else:
            assert row["component_evidence"] == []
        assert row["acceptance_evidence_status"] == "unverified"
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"] is True
    assert gate["formal_acceptance"] is False and gate["status"] == "blocked"
    assert {"real_codex_adapter", "real_claude_adapter", "real_other_adapters"} <= set(
        gate["blockers"]
    )


@pytest.mark.parametrize("junit_name", ["junit.xml", "wheel-junit.xml", "sdist-junit.xml"])
def test_all_planning_component_observations_leave_relay_unverified_and_release_blocked(
    tmp_path, junit_name
):
    manifest_path = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = [
        (
            "tests.unit.test_scheduling",
            "test_dependencies_require_completed_and_missing_is_never_completed",
        ),
        (
            "tests.unit.test_scheduling",
            "test_priority_then_created_at_then_id_sort_is_input_order_independent",
        ),
        (
            "tests.unit.test_scheduling",
            "test_cycles_duplicate_ids_and_oversized_snapshots_are_invalid",
        ),
        (
            "tests.integration.test_scheduling_core_boundary",
            "test_planning_uses_core_dependencies_and_priority_without_changing_tasks",
        ),
        (
            "tests.integration.test_scheduling_core_boundary",
            "test_core_rejects_stale_recommendation_after_another_worker_claims",
        ),
        (
            "tests.integration.test_scheduling_core_boundary",
            "test_in_flight_handoff_is_not_a_candidate_but_other_pending_work_is",
        ),
        (
            "tests.unit.test_dispatch_planning",
            "test_global_priority_order_and_least_load_balancing_are_deterministic",
        ),
        (
            "tests.unit.test_dispatch_planning",
            "test_load_aggregates_all_sessions_but_dispatch_selects_one_fresh_session",
        ),
        (
            "tests.unit.test_dispatch_planning",
            "test_reserved_worker_at_capacity_does_not_fall_back_to_another_worker",
        ),
        (
            "tests.integration.test_dispatch_planning_core_boundary",
            "test_real_task_load_limits_suggestions_without_mutating_core",
        ),
        (
            "tests.integration.test_dispatch_planning_core_boundary",
            "test_expired_lease_keeps_slot_until_explicit_core_reclamation",
        ),
        (
            "tests.integration.test_dispatch_planning_core_boundary",
            "test_offline_handoff_recipient_is_not_replaced_by_another_available_worker",
        ),
        # Ordinary neighboring names/classes are not the declared selectors.
        (
            "tests.unit.test_scheduling",
            "test_dependencies_require_completed_and_missing_is_never_completed_extra",
        ),
        ("tests.unit.other", "test_dependencies_require_completed_and_missing_is_never_completed"),
    ]
    (tmp_path / junit_name).write_text(
        "<testsuites><testsuite>"
        + "".join(f'<testcase classname="{module}" name="{name}"/>' for module, name in cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    rows = runner.requirement_results(manifest, tmp_path)
    by_id = {row["id"]: row for row in rows}
    assert by_id["M7-02"]["acceptance_evidence_status"] == "unverified"
    assert by_id["M7-01"]["acceptance_evidence_status"] == "not_run"
    assert len(rows) == 42 and all(row["execution_status"] == "not_run" for row in rows)
    for requirement_id in ("M7-01", "M7-02"):
        row = by_id[requirement_id]
        assert row["coverage"] == "partial" and len(row["component_evidence"]) == 6
        for component in row["component_evidence"]:
            assert component["observations"] == [
                {
                    "junit": junit_name,
                    "counts": {
                        "tests": 1,
                        "passed": 1,
                        "failures": 0,
                        "errors": 0,
                        "skipped": 0,
                    },
                }
            ]
    for requirement_id in ("M6-03", "M6-04", "M6-05"):
        assert by_id[requirement_id]["coverage"] == (
            "partial" if requirement_id in {"M6-03", "M6-04"} else "missing"
        )
        if requirement_id in {"M6-03", "M6-04"}:
            assert len(by_id[requirement_id]["component_evidence"]) == (
                8 if requirement_id == "M6-03" else 4
            )
            assert all(
                all(value == 0 for value in observation["counts"].values())
                for component in by_id[requirement_id]["component_evidence"]
                for observation in component["observations"]
            )
        else:
            assert by_id[requirement_id]["component_evidence"] == []
        assert by_id[requirement_id]["acceptance_evidence_status"] == "unverified"
    gate = runner.release_gate([passing_check(tmp_path)], tmp_path)
    assert gate["local_checks_passed"] is True
    assert gate["formal_acceptance"] is False and gate["status"] == "blocked"
    assert "autonomous_relay" in gate["blockers"]


def test_all_manifest_requirements_appear_in_json_and_markdown(repository, tmp_path):
    source = Path(__file__).resolve().parents[2] / "docs/acceptance/requirements.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    target = repository / "docs/acceptance/requirements.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(manifest))
    run = runner.collect(repository, tmp_path / "evidence", run_checks=False, package_install=False)
    report = json.loads((run / "report.json").read_text())
    markdown = (run / "Release-Acceptance-Report.md").read_text()
    assert [r["id"] for r in report["requirements"]] == [r["id"] for r in manifest["requirements"]]
    assert all(r["execution_status"] == "not_run" for r in report["requirements"])
    assert all(f"| {r['id']} |" in markdown for r in report["requirements"])


def test_source_snapshot_includes_untracked_source_but_omits_secret_files(repository, monkeypatch):
    (repository / "new.py").write_text("print('new')")
    (repository / ".env").write_text("SECRET=never archive")
    monkeypatch.setattr(runner, "git_value", lambda *_args: "new.py\0.env\0")
    snapshot = runner.source_snapshot(repository)
    assert snapshot == [
        {"path": "new.py", "sha256": runner.sha256(repository / "new.py"), "size": 12}
    ]


@pytest.mark.parametrize("flag,expected", [([], 0), (["--require-release"], 2)])
def test_cli_distinguishes_local_validation_from_release_acceptance(
    tmp_path, monkeypatch, flag, expected
):
    report = tmp_path / "report.json"
    report.write_text(
        '{"checks": [{"status": "pass"}], "release_gate": {"formal_acceptance": false}}'
    )
    monkeypatch.setattr(runner, "collect", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(
        runner.sys, "argv", ["release_acceptance.py", "--output", str(tmp_path), *flag]
    )
    assert runner.main() == expected


def test_execute_records_real_process_exit_and_log(repository, tmp_path):
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    (run / "tmp").mkdir()
    item = runner.execute(
        "probe",
        [runner.sys.executable, "-c", "print('probe'); raise SystemExit(7)"],
        repository,
        run,
    )
    assert item["status"] == "fail"
    assert item["exit_code"] == 7
    assert "probe" in (run / item["log"]).read_text()
    assert item["log_sha256"] == runner.sha256(run / item["log"])


def test_failed_subprocess_credentials_are_redacted_before_evidence_hash(repository, tmp_path):
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    secrets = [
        "fixture-session-12345",
        "fixture-admin-12345",
        "fixture-lease-12345",
        "fixture-bearer-12345",
        "sk-proj-0123456789abcdefghijk",
    ]
    payload = repr(
        {"session_token": secrets[0], "admin_token": secrets[1], "lease_token": secrets[2]}
    )
    script = f"print({payload!r}); print('Authorization: Bearer {secrets[3]}'); print('{secrets[4]}'); print('traceback context kept'); raise SystemExit(7)"
    item = runner.execute(
        "failed_probe", [runner.sys.executable, "-c", script], repository, run, scratch
    )
    saved = (run / item["log"]).read_text()
    assert item["exit_code"] == 7 and item["status"] == "fail"
    assert all(secret not in saved for secret in secrets)
    assert "[REDACTED]" in saved and "traceback context kept" in saved
    assert item["credential_redactions"] >= len(secrets)
    assert item["log_sha256"] == runner.sha256(run / item["log"])
    assert not list(scratch.iterdir()), "Raw capture must self-delete"


@pytest.mark.parametrize(
    "text",
    [
        "token budget exceeded; token_count = 3",
        "def read_session_token(value): return value",
        "assert candidate['status'] == 'awaiting_human_approval'",
        "HTTP status 429; retry after 3 seconds",
    ],
)
def test_redaction_keeps_innocent_identifiers_and_failure_context(text):
    assert runner.redact_credentials(text) == (text, 0)


@pytest.mark.parametrize(
    "text",
    [
        '{"session_token": "fixture-secret"}',
        "{'admin_token': 'fixture-secret'}",
        "lease_token='fixture-secret'",
        "AGENTSYNC_HTTP_TOKEN = fixture-secret",
        "Authorization: Bearer fixture-secret",
    ],
)
def test_redaction_handles_json_repr_assignment_and_bearer_forms(text):
    clean, count = runner.redact_credentials(text)
    assert "fixture-secret" not in clean
    assert "[REDACTED]" in clean and count > 0


def test_junit_redacts_traceback_and_attributes_without_losing_counts(tmp_path):
    raw = tmp_path / "scratch.xml"
    durable = tmp_path / "junit.xml"
    raw.write_text(
        '<testsuites><testsuite><testcase name="example"><failure message="admin_token=fixture-admin">'
        "Traceback: {'session_token': 'fixture-session'}; Authorization: Bearer fixture-bearer"
        '</failure></testcase><testcase name="skipped"><skipped/></testcase></testsuite></testsuites>'
    )
    before = runner.junit_counts(raw)
    assert runner.persist_junit(raw, durable) >= 3
    saved = durable.read_text()
    assert all(
        secret not in saved for secret in ("fixture-admin", "fixture-session", "fixture-bearer")
    )
    assert "Traceback" in saved and "[REDACTED]" in saved
    assert runner.junit_counts(durable) == before


def test_log_limit_is_explicit_and_hash_covers_bounded_evidence(repository, tmp_path, monkeypatch):
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    (run / "tmp").mkdir()
    monkeypatch.setattr(runner, "MAX_LOG_BYTES", 64)
    item = runner.execute(
        "bounded", [runner.sys.executable, "-c", "print('x' * 200)"], repository, run
    )
    assert item["log_truncated"]
    assert "OUTPUT TRUNCATED" in (run / item["log"]).read_text()
    assert item["log_sha256"] == runner.sha256(run / item["log"])


@pytest.fixture
def isolated_install_plan(tmp_path, monkeypatch):
    """Unit-only command recorder, never actual distribution/client acceptance evidence."""
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    (run / "artifacts").mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    archive = run / "artifacts/agentsync_local-0.3.0a1.tar.gz"
    archive.write_bytes(b"unit-only archive placeholder")
    calls = []
    failures = set()
    xml = {
        "value": '<testsuites><testsuite><testcase classname="tests.unit.example" name="test_example"/></testsuite></testsuites>'
    }

    def fake_execute(check_id, command, repo, evidence, temporary):
        calls.append((check_id, command, repo, temporary))
        log = evidence / "logs" / (check_id + ".log")
        log.write_text("Unit simulation only")
        if "--junitxml" in command and xml["value"] is not None:
            Path(command[command.index("--junitxml") + 1]).write_text(xml["value"])
        return {
            "id": check_id,
            "command": command,
            "status": "fail" if check_id in failures else "pass",
            "exit_code": 1 if check_id in failures else 0,
            "log": log.relative_to(evidence).as_posix(),
            "log_sha256": runner.sha256(log),
            "provenance": "local_process",
        }

    monkeypatch.setattr(runner, "execute", fake_execute)
    return run, scratch, archive, calls, failures, xml


def test_sdist_uses_exact_archive_fresh_venv_isolated_origin_and_full_suite(
    repository, isolated_install_plan
):
    run, scratch, archive, calls, _, _ = isolated_install_plan
    checks = runner.sdist_checks(repository, run, scratch, "0.3.0a1", True)
    assert len(checks) == 6 and all(c["status"] == "pass" for c in checks)
    commands = {check_id: command for check_id, command, _, _ in calls}
    install = commands["sdist_install"]
    assert install[-1] == str(archive) + "[dev]"
    assert "--use-pep517" in install and "--no-cache-dir" in install
    assert not any(arg in install for arg in ("-e", "--editable", "--no-build-isolation"))
    environment = Path(commands["sdist_venv"][-1])
    assert environment.is_relative_to(scratch) and environment.name.startswith("sdist-")
    assert all(command[1] == "-I" for name, command in commands.items() if name != "sdist_venv")
    assert "origin.is_relative_to" in commands["sdist_origin_sdk"][-1]
    assert str(repository / "tests") in commands["sdist_pytest"]
    assert all(cwd == run for _, _, cwd, _ in calls)
    assert checks[1]["artifact"]["sha256"] == runner.sha256(archive)
    assert checks[-1]["junit"]["tests"] == 1
    assert (run / "sdist-junit.xml").exists()


@pytest.mark.parametrize("scenario", ["missing", "duplicate", "build_failed"])
def test_requested_sdist_without_unique_successful_archive_fails(
    repository, isolated_install_plan, scenario
):
    run, scratch, archive, calls, _, _ = isolated_install_plan
    if scenario == "missing":
        archive.unlink()
    elif scenario == "duplicate":
        (archive.parent / "second.tar.gz").write_bytes(b"ambiguous")
    checks = runner.sdist_checks(repository, run, scratch, "0.3.0a1", scenario != "build_failed")
    assert checks[0]["status"] == "fail"
    assert not calls


@pytest.mark.parametrize(
    "failure,not_run",
    [
        ("sdist_venv", "sdist_install"),
        ("sdist_install", "sdist_origin_sdk"),
        ("sdist_origin_sdk", "sdist_pytest"),
    ],
)
def test_sdist_install_and_origin_failures_never_fall_back(
    repository, isolated_install_plan, failure, not_run
):
    run, scratch, _, calls, failures, _ = isolated_install_plan
    failures.add(failure)
    checks = runner.sdist_checks(repository, run, scratch, "0.3.0a1", True)
    results = {c["id"]: c["status"] for c in checks}
    assert results[failure] == "fail" and results[not_run] == "not_run"
    assert not any(name == not_run for name, *_ in calls)


@pytest.mark.parametrize(
    "xml",
    [
        None,
        "not xml",
        "<testsuites/>",
        "<testsuites><testsuite><testcase><failure/></testcase></testsuite></testsuites>",
        "<testsuites><testsuite><testcase><error/></testcase></testsuite></testsuites>",
    ],
)
def test_sdist_junit_missing_invalid_empty_and_failures_are_not_passes(
    repository, isolated_install_plan, xml
):
    run, scratch, _, _, _, settings = isolated_install_plan
    settings["value"] = xml
    checks = runner.sdist_checks(repository, run, scratch, "0.3.0a1", True)
    assert next(c for c in checks if c["id"] == "sdist_pytest")["status"] == "fail"


@pytest.mark.parametrize(
    "failed,package_install",
    [
        ("wheel_install", True),
        ("sdist_install", True),
        ("wheel_missing", True),
        ("wheel_duplicate", True),
        ("none", False),
    ],
)
def test_wheel_and_sdist_results_remain_independent(
    repository, tmp_path, monkeypatch, failed, package_install
):
    calls = []

    def fake_execute(check_id, command, repo, run, scratch):
        calls.append(check_id)
        if check_id == "build":
            if failed != "wheel_missing":
                (run / "artifacts/agentsync_local-0.3.0a1.whl").write_bytes(b"unit wheel")
            if failed == "wheel_duplicate":
                (run / "artifacts/second.whl").write_bytes(b"ambiguous wheel")
            (run / "artifacts/agentsync_local-0.3.0a1.tar.gz").write_bytes(b"unit sdist")
        if "--junitxml" in command:
            Path(command[command.index("--junitxml") + 1]).write_text(
                "<testsuites><testsuite><testcase/></testsuite></testsuites>"
            )
        log = run / "logs" / (check_id + ".log")
        log.write_text("Unit simulation only")
        return {
            "id": check_id,
            "status": "fail" if check_id == failed else "pass",
            "exit_code": 1 if check_id == failed else 0,
            "log": log.relative_to(run).as_posix(),
            "log_sha256": runner.sha256(log),
            "provenance": "local_process",
        }

    monkeypatch.setattr(runner, "execute", fake_execute)
    run = runner.collect(
        repository,
        tmp_path / "evidence",
        run_checks=True,
        package_install=package_install,
        sdist_install=True,
    )
    report = json.loads((run / "report.json").read_text())
    checks = {c["id"]: c["status"] for c in report["checks"]}
    if failed == "none":
        assert checks["sdist_install"] == "pass" and checks["wheel_install"] == "not_run"
        assert "wheel_install" not in calls
    else:
        failed_id = "wheel_install" if failed.startswith("wheel_") else failed
        other = "wheel_install" if failed == "sdist_install" else "sdist_install"
        assert checks[failed_id] == "fail" and checks[other] == "pass"
    assert "sdist_install" in calls
    assert len(report["distribution_installations"]) == 2
    assert not list((tmp_path / "evidence").glob(".scratch-*"))


def test_sdist_archive_modified_during_tests_is_not_accepted(
    repository, isolated_install_plan, monkeypatch
):
    run, scratch, archive, _, _, _ = isolated_install_plan
    simulate = runner.execute

    def mutate_after_test(check_id, *args):
        result = simulate(check_id, *args)
        if check_id == "sdist_pytest":
            archive.write_bytes(b"changed archive")
        return result

    monkeypatch.setattr(runner, "execute", mutate_after_test)
    checks = runner.sdist_checks(repository, run, scratch, "0.3.0a1", True)
    assert checks[-1]["id"] == "sdist_artifact_stability" and checks[-1]["status"] == "fail"


@pytest.mark.parametrize("change", ["replace", "delete"])
def test_wheel_archive_changed_after_successful_installation_is_not_accepted(
    repository, tmp_path, monkeypatch, change
):
    original = b"original wheel"

    def simulate(check_id, command, repo, run, scratch):
        archive = run / "artifacts/agentsync_local-0.3.0a1.whl"
        if check_id == "build":
            archive.write_bytes(original)
        if "--junitxml" in command:
            Path(command[command.index("--junitxml") + 1]).write_text(
                "<testsuites><testsuite><testcase/></testsuite></testsuites>"
            )
        if check_id == "wheel_pytest":
            if change == "replace":
                archive.write_bytes(b"different wheel")
            else:
                archive.unlink()
        log = run / "logs" / (check_id + ".log")
        log.write_text("Unit simulation only")
        return {
            "id": check_id,
            "status": "pass",
            "exit_code": 0,
            "log": log.relative_to(run).as_posix(),
            "log_sha256": runner.sha256(log),
            "provenance": "local_process",
        }

    monkeypatch.setattr(runner, "execute", simulate)
    run = runner.collect(repository, tmp_path / "evidence", run_checks=True, package_install=True)
    report = json.loads((run / "report.json").read_text())
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["wheel_install"]["status"] == "pass"
    assert checks["wheel_pytest"]["status"] == "pass"
    assert checks["wheel_artifact_stability"]["status"] == "fail"
    assert checks["wheel_artifact_stability"]["artifact"] == checks["wheel_install"]["artifact"]
    assert not report["release_gate"]["local_checks_passed"]


@pytest.mark.parametrize("check_id", ["pytest", "wheel_pytest", "sdist_pytest"])
def test_full_suite_subprocess_cannot_inherit_pytest_selection_or_plugins(
    repository, tmp_path, monkeypatch, check_id
):
    inherited = {
        "PYTEST_ADDOPTS": "-k one_test --ignore=tests/integration",
        "PYTEST_PLUGINS": "external_plugin",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    probe = (
        "import os; "
        f"assert not set({list(inherited)!r}).intersection(os.environ); "
        "print('pytest invocation environment is isolated')"
    )
    result = runner.execute(
        check_id, [runner.sys.executable, "-c", probe], repository, run, scratch
    )
    assert result["status"] == "pass"
    assert all(runner.os.environ[name] == value for name, value in inherited.items())


def test_sdist_flag_requires_run_and_is_independent_of_wheel(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner.sys, "argv", ["runner", "--output", str(tmp_path), "--sdist-install"]
    )
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2


def test_sdist_component_evidence_has_distinct_junit_source(tmp_path):
    for name in ("junit.xml", "wheel-junit.xml", "sdist-junit.xml"):
        (tmp_path / name).write_text(
            '<testsuites><testsuite><testcase classname="tests.unit.example" name="test_example"/></testsuite></testsuites>'
        )
    manifest = {
        "requirements": [{"id": "M9-02", "existing_tests": ["tests/unit/example.py::test_example"]}]
    }
    component = runner.requirement_results(manifest, tmp_path)[0]["component_evidence"][0]
    assert [o["junit"] for o in component["observations"]] == [
        "junit.xml",
        "wheel-junit.xml",
        "sdist-junit.xml",
    ]


def test_saved_working_tree_diff_is_redacted_with_original_hash(repository, tmp_path, monkeypatch):
    diff = "+session_token = 'literal-fixture-secret'\n+normal_code = 3"
    monkeypatch.setattr(runner, "git_value", lambda _repo, *args: diff if args[0] == "diff" else "")
    run = runner.collect(repository, tmp_path / "evidence", run_checks=False, package_install=False)
    report = json.loads((run / "report.json").read_text())
    assert "literal-fixture-secret" not in (run / "working-tree.patch").read_text()
    assert "normal_code = 3" in (run / "working-tree.patch").read_text()
    assert report["working_tree_patch_redactions"] > 0
    assert (
        report["original_working_tree_patch_sha256"]
        == runner.hashlib.sha256(diff.encode()).hexdigest()
    )
    assert report["working_tree_patch_sha256"] != report["original_working_tree_patch_sha256"]


@pytest.mark.parametrize("prefix", ["wheel", "sdist", "build"])
def test_installer_subprocess_cannot_inherit_external_write_targets(
    repository, tmp_path, monkeypatch, prefix
):
    dangerous = [
        "PIP_TARGET",
        "PIP_PREFIX",
        "PIP_ROOT",
        "PIP_USER",
        "PIP_PYTHON",
        "PIP_LOG",
        "PIP_REPORT",
        "PIP_SRC",
        "PIP_BUILD_TRACKER",
        "PIP_NO_BUILD_ISOLATION",
    ]
    for name in dangerous:
        monkeypatch.setenv(name, "must-not-inherit")
    monkeypatch.setenv("PIP_CONFIG_FILE", "malicious-user-config")
    monkeypatch.setenv("PIP_INDEX_URL", "https://packages.example.invalid/simple")
    run = tmp_path / "evidence"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    script = (
        "import os; "
        f"assert all(name not in os.environ for name in {dangerous!r}); "
        "assert os.environ['PIP_CONFIG_FILE'] == os.devnull; "
        "assert os.environ['PIP_INDEX_URL'] == 'https://packages.example.invalid/simple'; "
        f"assert os.environ['PIP_CACHE_DIR'] == {str(scratch / 'pip-cache')!r}; "
        "print('installer controls isolated')"
    )
    item = runner.execute(
        "build" if prefix == "build" else prefix + "_probe",
        [runner.sys.executable, "-I", "-c", script],
        repository,
        run,
        scratch,
    )
    assert item["status"] == "pass"


def test_explicit_scratch_root_keeps_reports_durable_and_cleans_only_own_child(
    repository, tmp_path, monkeypatch
):
    scratch_root = tmp_path / "short"
    scratch_root.mkdir()
    sentinel = scratch_root / "keep.txt"
    sentinel.write_text("caller-owned contents")
    output = tmp_path / "durable" / "reports"
    temporary_paths = []

    def record_check(check_id, command, repo, run, scratch):
        assert scratch.parent == scratch_root.resolve()
        assert scratch != scratch_root and scratch.is_dir()
        assert run.parent == output.resolve()
        temporary_paths.append(scratch)
        (scratch / "transient.txt").write_text("temporary test data")
        return {"id": check_id, "status": "fail", "command": command}

    monkeypatch.setattr(runner, "execute", record_check)
    run = runner.collect(
        repository, output, run_checks=True, package_install=False, scratch_root=scratch_root
    )
    assert temporary_paths and all(not path.exists() for path in temporary_paths)
    assert (run / "report.json").is_file()
    assert (run / "Release-Acceptance-Report.md").is_file()
    assert sentinel.read_text() == "caller-owned contents"
    assert list(scratch_root.iterdir()) == [sentinel]
    assert not list(output.glob(".scratch-*"))


def test_cli_scratch_root_reaches_collect(tmp_path, monkeypatch):
    scratch_root = tmp_path / "short"
    output = tmp_path / "reports"
    output.mkdir()
    (output / "report.json").write_text(
        '{"checks": [], "release_gate": {"formal_acceptance": false}}'
    )
    observed = []

    def fake_collect(
        repo, destination, *, run_checks, package_install, sdist_install, scratch_root
    ):
        observed.append((destination, scratch_root, run_checks, package_install, sdist_install))
        return output

    monkeypatch.setattr(runner, "collect", fake_collect)
    monkeypatch.setattr(
        runner.sys, "argv", ["runner", "--output", str(output), "--scratch-root", str(scratch_root)]
    )
    assert runner.main() == 0
    assert observed == [(output.resolve(), scratch_root, False, False, False)]


def test_scratch_child_is_cleaned_on_exception_without_removing_parent_contents(
    repository, tmp_path, monkeypatch
):
    scratch_root = tmp_path / "short"
    scratch_root.mkdir()
    sentinel = scratch_root / "keep.txt"
    sentinel.write_text("caller-owned contents")
    temporary_paths = []

    def fail_check(_check_id, _command, _repo, _run, scratch):
        temporary_paths.append(scratch)
        assert scratch.is_dir() and scratch.parent == scratch_root.resolve()
        (scratch / "unfinished.txt").write_text("unfinished check")
        raise RuntimeError("unit-only collector failure")

    monkeypatch.setattr(runner, "execute", fail_check)
    with pytest.raises(RuntimeError, match="unit-only collector failure"):
        runner.collect(
            repository,
            tmp_path / "reports",
            run_checks=True,
            package_install=False,
            scratch_root=scratch_root,
        )
    assert temporary_paths and all(not path.exists() for path in temporary_paths)
    assert sentinel.read_text() == "caller-owned contents"
    assert list(scratch_root.iterdir()) == [sentinel]


@pytest.mark.parametrize("explicit_none", [False, True])
def test_default_scratch_parent_remains_output(repository, tmp_path, monkeypatch, explicit_none):
    output = tmp_path / "reports"
    temporary_paths = []

    def record_check(check_id, command, _repo, _run, scratch):
        temporary_paths.append(scratch)
        assert scratch.parent == output.resolve()
        return {"id": check_id, "status": "fail", "command": command}

    monkeypatch.setattr(runner, "execute", record_check)
    options = {"scratch_root": None} if explicit_none else {}
    run = runner.collect(repository, output, run_checks=True, package_install=False, **options)
    assert temporary_paths and all(not path.exists() for path in temporary_paths)
    assert (run / "report.json").is_file()


def test_cli_without_scratch_root_preserves_existing_collect_signature(tmp_path, monkeypatch):
    (tmp_path / "report.json").write_text(
        '{"checks": [], "release_gate": {"formal_acceptance": false}}'
    )
    observed = []

    def fake_collect(repo, output, *, run_checks, package_install, sdist_install):
        observed.append(output)
        return tmp_path

    monkeypatch.setattr(runner, "collect", fake_collect)
    monkeypatch.setattr(runner.sys, "argv", ["runner", "--output", str(tmp_path)])
    assert runner.main() == 0
    assert observed == [tmp_path.resolve()]


def test_missing_scratch_parent_is_created_outside_durable_output(repository, tmp_path):
    scratch_root = tmp_path / "new" / "short"
    output = tmp_path / "reports"
    run = runner.collect(
        repository, output, run_checks=False, package_install=False, scratch_root=scratch_root
    )
    assert scratch_root.is_dir() and not list(scratch_root.iterdir())
    assert (run / "report.json").is_file()
    report = json.loads((run / "report.json").read_text())
    command = next(check["command"] for check in report["checks"] if check["id"] == "pytest")
    recorded_temporary = Path(command[command.index("--basetemp") + 1]).parent
    assert recorded_temporary.parent == scratch_root.resolve()
    assert not recorded_temporary.exists()


def test_pytest_controller_uses_requested_timeout(repository, tmp_path, monkeypatch):
    run = tmp_path / "reports"
    (run / "logs").mkdir(parents=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    deadlines = []

    def fake_subprocess(command, **options):
        deadlines.append(options["timeout"])
        return runner.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess)
    check = runner.execute(
        "pytest", ["python", "-m", "pytest"], repository, run, scratch, pytest_timeout=1800
    )
    assert deadlines == [1800]
    assert check["timeout_seconds"] == 1800


@pytest.mark.parametrize("value", [0, -1, 7201, True, False, 1.0, 900.0, "900", None])
def test_collect_rejects_invalid_pytest_timeout_before_mkdir(repository, tmp_path, value):
    output = tmp_path / "uncreated" / "reports"
    scratch = tmp_path / "uncreated-scratch"
    with pytest.raises(ValueError, match="pytest.*timeout"):
        runner.collect(
            repository,
            output,
            run_checks=False,
            package_install=False,
            scratch_root=scratch,
            pytest_timeout=value,
        )
    assert not output.parent.exists()
    assert not scratch.exists()


@pytest.mark.parametrize("check_id", ["build", "pip_check", "ruff", "wheel_install", "sdist_venv"])
def test_custom_pytest_timeout_rejected_for_other_controllers(repository, tmp_path, check_id):
    with pytest.raises(ValueError, match="pytest.*timeout"):
        runner.execute(
            check_id, ["unit-only"], repository, tmp_path / "absent", pytest_timeout=1800
        )


@pytest.mark.parametrize("deadline", [1, 900, 1800, 7200])
def test_collect_timeout_reaches_all_suite_controllers_and_saved_metadata(
    repository, tmp_path, monkeypatch, deadline
):
    observed = []

    def fake_subprocess(command, **options):
        suite = None
        if "--outdir" in command:
            artifacts = Path(command[command.index("--outdir") + 1])
            (artifacts / "unit.whl").write_bytes(b"unit-only wheel")
            (artifacts / "unit.tar.gz").write_bytes(b"unit-only sdist")
        if "--junitxml" in command:
            junit = Path(command[command.index("--junitxml") + 1])
            junit.write_text("<testsuites><testsuite><testcase/></testsuite></testsuites>")
            suite = {
                "junit.xml": "pytest",
                "wheel-junit.xml": "wheel_pytest",
                "sdist-junit.xml": "sdist_pytest",
            }[junit.name]
        observed.append((suite, options["timeout"]))
        return runner.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess)
    run = runner.collect(
        repository,
        tmp_path / "reports",
        run_checks=True,
        package_install=True,
        sdist_install=True,
        pytest_timeout=deadline,
    )
    suites = {suite: timeout for suite, timeout in observed if suite is not None}
    assert suites == {"pytest": deadline, "wheel_pytest": deadline, "sdist_pytest": deadline}
    assert all(timeout == 900 for suite, timeout in observed if suite is None)
    report = json.loads((run / "report.json").read_text())
    assert all(check["status"] == "pass" for check in report["checks"])
    for check in report["checks"]:
        if deadline != 900 and check["id"] in suites:
            assert check["timeout_seconds"] == deadline
        else:
            assert "timeout_seconds" not in check


@pytest.mark.parametrize("deadline", [1, 900, 1800, 7200])
def test_cli_pytest_timeout_passes_only_nondefault_collect_option(tmp_path, monkeypatch, deadline):
    (tmp_path / "report.json").write_text(
        '{"checks": [], "release_gate": {"formal_acceptance": false}}'
    )
    observed = []

    def fake_collect(_repo, _output, *, run_checks, package_install, sdist_install, **options):
        observed.append(options)
        return tmp_path

    monkeypatch.setattr(runner, "collect", fake_collect)
    monkeypatch.setattr(
        runner.sys, "argv", ["runner", "--output", str(tmp_path), "--pytest-timeout", str(deadline)]
    )
    assert runner.main() == 0
    assert observed == ([{}] if deadline == 900 else [{"pytest_timeout": deadline}])


@pytest.mark.parametrize("value", ["0", "-1", "7201", "true", "1.5"])
def test_cli_invalid_pytest_timeout_never_calls_collect(tmp_path, monkeypatch, value):
    def forbidden(*_args, **_options):
        pytest.fail("Invalid CLI timeout reached collect")

    output = tmp_path / "uncreated"
    monkeypatch.setattr(runner, "collect", forbidden)
    monkeypatch.setattr(
        runner.sys, "argv", ["runner", "--output", str(output), "--pytest-timeout", value]
    )
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert not output.exists()


def test_design_report_records_custom_pytest_deadline_without_executing(
    repository, tmp_path, monkeypatch
):
    def forbidden(*_args, **_options):
        pytest.fail("Design-only report executed a subprocess")

    monkeypatch.setattr(runner.subprocess, "run", forbidden)
    run = runner.collect(
        repository,
        tmp_path / "reports",
        run_checks=False,
        package_install=False,
        pytest_timeout=1800,
    )
    report = json.loads((run / "report.json").read_text())
    suite = next(check for check in report["checks"] if check["id"] == "pytest")
    assert suite["status"] == "not_run" and suite["timeout_seconds"] == 1800
    assert all(
        "timeout_seconds" not in check for check in report["checks"] if check["id"] != "pytest"
    )

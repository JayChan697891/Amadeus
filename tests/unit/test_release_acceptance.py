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

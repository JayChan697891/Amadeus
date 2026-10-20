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

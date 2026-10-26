"""Local pytest subprocesses and private synthetic failures; no actual clients."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def launch(project, *arguments):
    # Use the actual base executable, avoiding a Windows venv redirector parent
    # so the supervisor terminates precisely the owned pytest process.
    executable = Path(sys.base_prefix) / ("python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        executable = Path(sys.executable)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT), str(Path(pytest.__file__).parent.parent))
    )
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTEST_ADDOPTS", None)
    return subprocess.Popen(
        [str(executable), "-m", "pytest", "-p", "tools.pytest_case_journal", "-q", *arguments],
        cwd=project,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run(project, *arguments):
    process = launch(project, *arguments)
    stdout, stderr = process.communicate(timeout=15)
    return process.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def test_failure_phase_survives_owned_pytest_termination_without_final_junit(tmp_path):
    (tmp_path / "test_fixture.py").write_text(
        "import time\nfrom pathlib import Path\n"
        "def test_a_failure():\n assert False, 'journal-private-failure'\n"
        "def test_b_slow():\n Path('slow-entered').write_text('owned slow fixture')\n time.sleep(120)\n",
        encoding="utf-8",
    )
    journal, junit = tmp_path / "private.jsonl", tmp_path / "unfinished.xml"
    process = launch(tmp_path, "--case-journal", str(journal), "--junitxml", str(junit))
    observed = []
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if journal.exists():
                observed = records(journal)
                if (
                    any(row.get("phase_outcome") == "failed" for row in observed)
                    and (tmp_path / "slow-entered").exists()
                ):
                    break
            if process.poll() is not None:
                break
            time.sleep(0.02)
        assert any(row.get("phase_outcome") == "failed" for row in observed)
        assert (tmp_path / "slow-entered").is_file()
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)
    saved = records(journal)
    failure = next(row for row in saved if row.get("phase_outcome") == "failed")
    assert failure["phase"] == "call"
    assert "journal-private-failure" in failure["failure_text"]
    assert not junit.exists()
    assert not any(row.get("event") == "finish" for row in saved)
    assert saved[0]["status"] == "incomplete"
    (tmp_path / "supervisor.json").write_text(
        json.dumps(
            {
                "owned_pid": process.pid,
                "command": process.args,
                "return_code_after_termination": process.returncode,
                "earlier_failure_flushed": True,
                "later_slow_fixture_entered": True,
                "valid_jsonl_records": len(saved),
                "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest(),
                "final_junit_exists": junit.exists(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_pass_skip_setup_error_are_phase_observations_not_acceptance(tmp_path):
    (tmp_path / "test_fixture.py").write_text(
        "import pytest\ndef test_pass(): pass\n"
        "@pytest.mark.skip(reason='known skip')\ndef test_skip(): pass\n"
        "@pytest.fixture\ndef broken(): raise RuntimeError('private-setup-marker')\n"
        "def test_error(broken): pass\n",
        encoding="utf-8",
    )
    path = tmp_path / "private.jsonl"
    code, stdout, stderr = run(tmp_path, "--case-journal", str(path), "--tb=no", "-rN")
    assert code == 1
    saved = records(path)
    phases = [row for row in saved if row["event"] == "phase"]
    assert any(row["phase"] == "call" and row["phase_outcome"] == "passed" for row in phases)
    assert any(row["phase_outcome"] == "skipped" for row in phases)
    failure = next(row for row in phases if row["phase_outcome"] == "failed")
    assert failure["phase"] == "setup" and "private-setup-marker" in failure["failure_text"]
    assert "private-setup-marker" not in stdout + stderr
    assert saved[-1]["event"] == "finish" and saved[-1]["pytest_exit_status"] == 1
    assert saved[-1]["release_acceptance"] == "unverified"
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_no_explicit_path_has_no_journal_effect_or_limit_validation(tmp_path):
    (tmp_path / "test_fixture.py").write_text("def test_pass(): pass\n", encoding="utf-8")
    code, _, _ = run(tmp_path, "--case-journal-max-bytes", "-1")
    assert code == 0 and not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize(
    "kind", ["file", "directory", "missing-parent", "symlink", "parent-symlink"]
)
def test_output_path_guards_preserve_existing_objects(tmp_path, kind):
    (tmp_path / "test_fixture.py").write_text("def test_pass(): pass\n", encoding="utf-8")
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_bytes(b"keep original bytes")
    selected = tmp_path / "private.jsonl"
    if kind == "file":
        selected = sentinel
    elif kind == "directory":
        selected.mkdir()
    elif kind == "missing-parent":
        selected = tmp_path / "missing" / "private.jsonl"
    else:
        target = sentinel if kind == "symlink" else tmp_path / "physical"
        if kind == "parent-symlink":
            target.mkdir()
        try:
            selected.symlink_to(target, target_is_directory=kind == "parent-symlink")
        except (OSError, NotImplementedError):
            pytest.skip("Local symlink creation unavailable")
        if kind == "parent-symlink":
            selected = selected / "private.jsonl"
    code, stdout, stderr = run(tmp_path, "--case-journal", str(selected))
    assert code == 4
    assert "Cannot create private case journal" in stdout + stderr
    assert sentinel.read_bytes() == b"keep original bytes"
    if kind in {"missing-parent", "parent-symlink"}:
        assert not selected.exists()


@pytest.mark.parametrize(
    "option,value", [("max", "2047"), ("max", "1048577"), ("report", "63"), ("report", "16385")]
)
def test_invalid_limits_do_not_create_output(tmp_path, option, value):
    selected = tmp_path / "private.jsonl"
    name = "--case-journal-max-bytes" if option == "max" else "--case-journal-report-bytes"
    code, stdout, stderr = run(tmp_path, "--case-journal", str(selected), name, value)
    assert code == 4 and not selected.exists()
    assert "outside supported bounds" in stdout + stderr


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Local FIFO creation unavailable")
def test_existing_fifo_is_rejected_without_opening_or_replacing_it(tmp_path):
    selected = tmp_path / "private.fifo"
    os.mkfifo(selected)
    before = selected.lstat()
    code, _, _ = run(tmp_path, "--case-journal", str(selected))
    after = selected.lstat()
    assert code == 4 and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)


def test_failure_text_cap_is_explicit_and_total_cap_freezes_incomplete(tmp_path):
    (tmp_path / "test_fixture.py").write_text(
        "import pytest\n@pytest.mark.parametrize('i',range(30))\n"
        "def test_large_failure(i): assert False, '秘密'*5000\n",
        encoding="utf-8",
    )
    text_path = tmp_path / "text-private.jsonl"
    code, _, _ = run(
        tmp_path, "--case-journal", str(text_path), "--case-journal-report-bytes", "64", "--tb=no"
    )
    assert code == 1
    saved = records(text_path)
    failures = [row for row in saved if row.get("phase_outcome") == "failed"]
    assert len(failures) == 30
    assert all(row["failure_text_truncated"] for row in failures)
    assert all(len(row["failure_text"].encode()) <= 64 for row in failures)
    assert saved[-1]["status"] == "complete_with_truncation"
    total_path = tmp_path / "limit-private.jsonl"
    code, stdout, stderr = run(
        tmp_path, "--case-journal", str(total_path), "--case-journal-max-bytes", "2048", "--tb=no"
    )
    assert code == 3
    assert total_path.stat().st_size <= 2048
    limited = records(total_path)
    assert limited[-1]["event"] == "journal_limit"
    assert limited[-1]["status"] == "incomplete"
    assert not any(row["event"] == "finish" for row in limited)
    assert "秘密" not in stdout + stderr


def test_owned_descriptor_failure_reports_static_error_and_stops_run(tmp_path):
    journal = tmp_path / "private.jsonl"
    # A controlled local OS fault closes only the selected fixture journal's FD.
    # This uses public OS APIs; it does not replace pytest/plugin internals.
    (tmp_path / "test_fixture.py").write_text(
        "import os\nfrom pathlib import Path\ndef test_descriptor_fault():\n"
        f" identity=Path({str(journal)!r}).stat()\n"
        " for fd in range(3,256):\n"
        "  try: current=os.fstat(fd)\n"
        "  except OSError: continue\n"
        "  if (current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino): os.close(fd)\n",
        encoding="utf-8",
    )
    code, stdout, stderr = run(tmp_path, "--case-journal", str(journal), "--tb=no")
    assert code == 3
    assert "Private case journal write failed; evidence is incomplete." in stdout + stderr
    assert records(journal)[0]["event"] == "start"
    assert not any(row["event"] == "finish" for row in records(journal))

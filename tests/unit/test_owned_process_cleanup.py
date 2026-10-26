"""Known Python helper processes; actual owned handles, no real Agent client."""

import subprocess
import sys

import pytest
from conftest import run_owned_processes

REAL_POPEN = subprocess.Popen


def helper(source):
    return [sys.executable, "-I", "-u", "-c", source]


def record_processes(monkeypatch):
    processes = []

    def start(*args, **kwargs):
        process = REAL_POPEN(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    return processes


def dispose(processes):
    # This regression's own fallback prevents leaking children on the RED run.
    for process in processes:
        if process.poll() is None:
            REAL_POPEN.kill(process)
        process.communicate(timeout=2)


def assert_reaped(processes):
    for process in processes:
        assert process.returncode is not None
        assert process.wait(timeout=0) == process.returncode
        assert process.stdout.closed and process.stderr.closed


def test_timeout_preserves_original_failure_and_reaps_every_started_child(monkeypatch):
    processes = record_processes(monkeypatch)
    commands = [helper("import time; time.sleep(10)") for _ in range(2)]
    try:
        with pytest.raises(subprocess.TimeoutExpired) as error:
            run_owned_processes(commands, timeout=0.1)
        assert error.value.cmd == commands[0] and error.value.timeout == 0.1
        assert len(processes) == 2
        assert_reaped(processes)
    finally:
        dispose(processes)


def test_partial_spawn_preserves_missing_executable_and_reaps_prior_child(tmp_path, monkeypatch):
    processes = record_processes(monkeypatch)
    missing = str(tmp_path / "missing-owned-test-helper.exe")
    try:
        with pytest.raises(FileNotFoundError):
            run_owned_processes([helper("import time; time.sleep(10)"), [missing]])
        assert len(processes) == 1
        assert_reaped(processes)
    finally:
        dispose(processes)


def test_cleanup_error_keeps_original_timeout_and_still_reaps_owned_child(monkeypatch):
    processes = []
    cleanup_error = OSError("Synthetic owned cleanup error after actual termination request")

    def start(*args, **kwargs):
        process = REAL_POPEN(*args, **kwargs)
        processes.append(process)

        def kill_then_fail():
            REAL_POPEN.kill(process)
            raise cleanup_error

        monkeypatch.setattr(process, "kill", kill_then_fail)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    try:
        with pytest.raises(BaseExceptionGroup) as error:
            run_owned_processes([helper("import time; time.sleep(10)")], timeout=0.1)
        assert len(error.value.exceptions) == 2
        assert isinstance(error.value.exceptions[0], subprocess.TimeoutExpired)
        assert error.value.exceptions[1] is cleanup_error
        assert len(processes) == 1
        assert_reaped(processes)
    finally:
        dispose(processes)


def test_completed_outputs_and_nonzero_status_are_preserved(monkeypatch):
    processes = record_processes(monkeypatch)
    try:
        results = run_owned_processes(
            [
                helper("print('first fixture')"),
                helper("print('second fixture'); raise SystemExit(3)"),
            ]
        )
        assert results == [(("first fixture\n", ""), 0), (("second fixture\n", ""), 3)]
        assert_reaped(processes)
    finally:
        dispose(processes)

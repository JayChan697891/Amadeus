"""Opt-in private local pytest phase evidence, never release acceptance.

Load from trusted repo code with ``python -m pytest -p tools.pytest_case_journal
--case-journal D:/explicit/new-private.jsonl``. No output is created without the
explicit path. The journal includes private node IDs/failure text; do not upload
it automatically. Normal pytest's own console reporting remains unchanged.

Each JSONL record is flushed to the OS and fsynced. Missing finish means incomplete
execution; setup/teardown passes never imply a test passed. This is one-process
developer tooling, not an xdist collector, sandbox or formal acceptance verifier.
Parent checks reject known symlink/reparse paths, not concurrent path replacement.
A finish records pytest's return, not execution of every collected test (for
example --maxfail can stop early). A hard kill during a write may leave a partial
last line; preserve prior complete lines and mark the evidence incomplete.
"""

import json
import os
import stat
from pathlib import Path

import pytest

_MAX_BYTES = 1024 * 1024
_REPORT_BYTES = 16384
_RESERVE = 512


def pytest_addoption(parser):
    group = parser.getgroup("local case journal")
    group.addoption("--case-journal", default=None, help="Explicit NEW private local JSONL file.")
    group.addoption("--case-journal-max-bytes", type=int, default=_MAX_BYTES)
    group.addoption("--case-journal-report-bytes", type=int, default=_REPORT_BYTES)


def _create(path):
    selected = Path(path).absolute()
    try:
        for parent in selected.parents:
            info = parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400
            ):
                raise OSError
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0)
        )
        descriptor = os.open(selected, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError
        except OSError:
            os.close(descriptor)
            raise
        return descriptor
    except (OSError, ValueError):
        raise pytest.UsageError(
            "Cannot create private case journal; select a new file in an existing physical directory."
        ) from None


def pytest_configure(config):
    selected = config.getoption("case_journal")
    if selected is None:
        return
    maximum = config.getoption("case_journal_max_bytes")
    report_limit = config.getoption("case_journal_report_bytes")
    if not 2048 <= maximum <= _MAX_BYTES or not 64 <= report_limit <= _REPORT_BYTES:
        raise pytest.UsageError("Case journal byte limits are outside supported bounds.")
    if config.pluginmanager.hasplugin("xdist"):
        raise pytest.UsageError("Case journal supports one pytest process only.")
    journal = _Journal(_create(selected), maximum, report_limit)
    config.pluginmanager.register(journal, "agentsync-private-case-journal")
    journal.write(
        {
            "event": "start",
            "schema": "agentsync.pytest-case-journal.v1",
            "status": "incomplete",
            "scope": "local_pytest_phase_observation",
            "release_acceptance": "unverified",
        }
    )


def _bounded(text, limit):
    encoded = text[:limit].encode("utf-8", errors="replace")
    truncated = len(text) > limit or len(encoded) > limit
    return encoded[:limit].decode("utf-8", errors="ignore"), truncated


class _Journal:
    def __init__(self, descriptor, maximum, report_limit):
        self.descriptor = descriptor
        self.maximum = maximum
        self.report_limit = report_limit
        self.used = 0
        self.limited = False
        self.text_truncated = False
        self.phases = 0

    def close(self):
        if self.descriptor is not None:
            descriptor = self.descriptor
            self.descriptor = None
            try:
                os.close(descriptor)
            except OSError:
                pass  # Write failure can mean the owned descriptor is already closed.

    def write(self, record, *, final=False):
        if self.descriptor is None:
            return
        data = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        allowance = self.maximum - self.used - (0 if final else _RESERVE)
        if len(data) > allowance:
            self.limited = True
            self.write(
                {"event": "journal_limit", "status": "incomplete", "saved_phases": self.phases},
                final=True,
            )
            self.close()
            return
        try:
            remaining = memoryview(data)
            while remaining:
                written = os.write(self.descriptor, remaining)
                if written <= 0:
                    raise OSError
                remaining = remaining[written:]
            os.fsync(self.descriptor)
            self.used += len(data)
        except OSError:
            # Best effort restores the last complete JSONL boundary. Disk or
            # filesystem failure can still leave damaged/incomplete evidence.
            try:
                os.ftruncate(self.descriptor, self.used)
            except OSError:
                pass
            self.close()
            pytest.exit("Private case journal write failed; evidence is incomplete.", returncode=3)

    def pytest_runtest_logreport(self, report):
        if self.descriptor is None:
            return
        nodeid, node_truncated = _bounded(report.nodeid, 2048)
        failure, text_truncated = _bounded(
            report.longreprtext if report.failed else "", self.report_limit
        )
        self.text_truncated |= text_truncated or node_truncated
        self.write(
            {
                "event": "phase",
                "nodeid": nodeid,
                "nodeid_truncated": node_truncated,
                "phase": report.when,
                "phase_outcome": report.outcome,
                "expected_failure": hasattr(report, "wasxfail"),
                "failure_text": failure,
                "failure_text_truncated": text_truncated,
            }
        )
        if not self.limited:
            self.phases += 1

    def pytest_sessionfinish(self, session, exitstatus):
        if self.limited:
            session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
            return
        status = "complete_with_truncation" if self.text_truncated else "complete"
        if int(exitstatus) not in {0, 1}:
            status = "incomplete"
        self.write(
            {
                "event": "finish",
                "status": status,
                "pytest_exit_status": int(exitstatus),
                "tests_collected": session.testscollected,
                "tests_failed": session.testsfailed,
                "saved_phases": self.phases,
                "release_acceptance": "unverified",
            },
            final=True,
        )
        self.close()

    def pytest_unconfigure(self, config):
        self.close()

"""Summarize explicit local acceptance reports for one frozen source revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

_REPORT_LIMIT = 8 * 1024 * 1024
_SYSTEMS = {"windows": "Windows", "linux": "Linux", "macos": "macOS", "darwin": "macOS"}
_REQUIRED_SYSTEMS = {"Windows", "Linux", "macOS"}
_SUITES = {"pytest", "wheel_pytest", "sdist_pytest"}
_REQUIRED_CHECKS = _SUITES | {
    "ruff", "format", "mypy", "build", "pip_check", "wheel_install", "sdist_install"
}
_IDENTITY_FIELDS = ("version", "commit_sha", "tree_sha", "source_snapshot_sha256")


def _read_report(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ValueError("A report file is required.")
    with path.open("rb") as report:
        data = report.read(_REPORT_LIMIT + 1)
    if len(data) > _REPORT_LIMIT:
        raise ValueError("Report exceeds the size limit.")
    content = json.loads(data.decode("utf-8"))
    if type(content) is not dict or type(content.get("schema_version")) is not int:
        raise ValueError("Unsupported report schema.")
    if content["schema_version"] != 1:
        raise ValueError("Unsupported report schema.")
    return content, hashlib.sha256(data).hexdigest()


def _observation(report: dict[str, Any], digest: str) -> dict[str, Any]:
    if (
        report.get("working_tree_status") != ""
        or report.get("source_changed_during_execution") is not False
    ):
        raise ValueError("The report does not describe unchanged, clean source.")
    system = _SYSTEMS[report["platform"].split("-", 1)[0].lower()]
    python = report["python"]
    if type(python) is not str or not python or len(python) > 512:
        raise ValueError("Missing Python version.")
    rows = report["checks"]
    if type(rows) is not list or not 1 <= len(rows) <= 100:
        raise ValueError("Invalid report checks.")
    checks: dict[str, str] = {}
    suites: dict[str, dict[str, int]] = {}
    for row in rows:
        name, status = row["id"], row["status"]
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
            raise ValueError("Invalid check ID.")
        if name in checks or status not in ("pass", "fail", "blocked", "not_run"):
            raise ValueError("Invalid or repeated check.")
        checks[name] = status
        if name in _SUITES and "junit" in row:
            counts = row["junit"]
            fields = ("tests", "failures", "errors", "skipped")
            if any(type(counts[field]) is not int or counts[field] < 0 for field in fields):
                raise ValueError("Invalid reported JUnit counts.")
            suites[name] = {field: counts[field] for field in fields}
        if name in _SUITES and status == "pass":
            observed = suites.get(name)
            if (
                observed is None
                or observed["failures"]
                or observed["errors"]
                or observed["tests"] <= observed["skipped"]
            ):
                raise ValueError("Reported suite pass conflicts with JUnit counts.")
    return {
        "system": system,
        "python": python,
        "report_sha256": digest,
        "checks": checks,
        "junit": suites,
    }


def summarize(paths: list[Path], expected_commit: str) -> dict[str, Any]:
    if not 1 <= len(paths) <= 12 or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Supply a frozen Git SHA and one to twelve reports.")
    observations = []
    identities = set()
    report_digests = set()
    for path in paths:
        report, digest = _read_report(path)
        identity = tuple(report[field] for field in _IDENTITY_FIELDS)
        version, commit, tree, snapshot = identity
        if (
            type(version) is not str
            or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}", version)
            or commit != expected_commit
            or not re.fullmatch(r"[0-9a-f]{40}", tree)
            or not re.fullmatch(r"[0-9a-f]{64}", snapshot)
        ):
            raise ValueError("Invalid frozen source identity.")
        if digest in report_digests:
            raise ValueError("Duplicate report.")
        identities.add(identity)
        report_digests.add(digest)
        observations.append(_observation(report, digest))
    if len(identities) != 1:
        raise ValueError("Reports describe different frozen sources.")
    frozen = dict(zip(_IDENTITY_FIELDS, identities.pop(), strict=True))
    complete = {
        observation["system"]
        for observation in observations
        if all(observation["checks"].get(name) == "pass" for name in _REQUIRED_CHECKS)
    }
    failed = any("fail" in observation["checks"].values() for observation in observations)
    missing = sorted(_REQUIRED_SYSTEMS - complete)
    return {
        "schema_version": 1,
        "scope": "saved_local_report_observations",
        "frozen": frozen,
        "observations": observations,
        "systems_without_full_reported_checks": missing,
        "local_matrix": "failed" if failed else "incomplete" if missing else "reported_pass",
        "artifact_bytes_verified": False,
        "formal_release_acceptance": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("report", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        matrix = summarize(args.report, args.commit)
    except (AttributeError, KeyError, OSError, RecursionError, TypeError, ValueError):
        parser.exit(2, "Invalid local acceptance reports or mismatched frozen source.\n")
    print(json.dumps(matrix, indent=2))
    return 1 if matrix["local_matrix"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Summarize explicit local acceptance reports for one frozen source revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
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
RELEASE_PYTHON_MINORS = ("3.11", "3.12", "3.14")


def matrix_digest(matrix: dict[str, Any]) -> str:
    observations = sorted(matrix["observations"], key=lambda row: row["report_sha256"])
    document = matrix | {"observations": observations}
    canonical = json.dumps(
        document, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _read_report(
    path: Path, *, decoder: Callable[[bytes], Any] | None = None
) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise ValueError("A report file is required.")
    if decoder is not None and (
        path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("Verified report evidence requires an ordinary report file.")
    with path.open("rb") as report:
        data = report.read(_REPORT_LIMIT + 1)
    if len(data) > _REPORT_LIMIT:
        raise ValueError("Report exceeds the size limit.")
    content = json.loads(data.decode("utf-8")) if decoder is None else decoder(data)
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
        if name in checks or status not in ("pass", "fail", "blocked", "not_run", "restricted", "unverified"):
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


def _complete_observation(
    observation: dict[str, Any], *, verify_artifacts: bool, require_license_inventory: bool,
) -> bool:
    required = _REQUIRED_CHECKS
    if verify_artifacts:
        required = required | {"wheel_origin_sdk", "sdist_origin_sdk", "wheel_pip_check", "sdist_pip_check"}
    if require_license_inventory:
        required = required | {"wheel_license_inventory", "sdist_license_inventory"}
    return all(observation["checks"].get(name) == "pass" for name in required) and (
        not verify_artifacts or observation["artifact_audit"]["junit_case_sets_match"] is True
    )


def _platform_gaps(
    observations: list[dict[str, Any]], python_minors: tuple[str, ...],
) -> tuple[list[str], list[dict[str, str]]]:
    missing_systems = sorted(_REQUIRED_SYSTEMS - {row["system"] for row in observations})
    observed_matrix = set()
    for row in observations:
        match = re.match(r"^(3\.[0-9]{1,2})\.[0-9]+(?:\D|$)", row["python"])
        if match:
            observed_matrix.add((row["system"], match.group(1)))
    combinations = [
        {"system": system, "python_minor": minor}
        for system, minor in sorted((system, minor) for system in _REQUIRED_SYSTEMS for minor in python_minors)
        if (system, minor) not in observed_matrix
    ]
    return missing_systems, combinations


def summarize(
    paths: list[Path], expected_commit: str, *, verify_artifacts: bool = False,
    require_license_inventory: bool = False, python_minors: tuple[str, ...] = (),
    source_repo: Path | None = None,
) -> dict[str, Any]:
    if not 1 <= len(paths) <= 12 or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Supply a frozen Git SHA and one to twelve reports.")
    if require_license_inventory and not verify_artifacts:
        raise ValueError("Required license inventories need artifact verification.")
    if source_repo is not None and not verify_artifacts:
        raise ValueError("Git source binding needs artifact verification.")
    if (
        type(python_minors) is not tuple or len(python_minors) > 4
        or any(type(value) is not str or not re.fullmatch(r"3\.(?:1[1-9]|[2-9][0-9])", value) for value in python_minors)
        or len(set(python_minors)) != len(python_minors)
    ):
        raise ValueError("Supply distinct supported Python minor versions.")
    decoder = None
    verifier = None
    if verify_artifacts:
        if __package__:
            from .acceptance_evidence import read_json, verify_report_evidence
        else:
            from acceptance_evidence import read_json, verify_report_evidence

        decoder = read_json
        verifier = verify_report_evidence
    observations = []
    identities = set()
    report_digests = set()
    source_audit = None
    for path in paths:
        report, digest = _read_report(path, decoder=decoder)
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
        observation = _observation(report, digest)
        if verifier is not None:
            audit = verifier(path, report, source_repo=source_repo if source_audit is None else None)
            git_source = audit.pop("git_source_audit")
            if git_source is not None:
                source_audit = git_source
            observation["artifact_audit"] = audit
        observations.append(observation)
    if len(identities) != 1:
        raise ValueError("Reports describe different frozen sources.")
    frozen = dict(zip(_IDENTITY_FIELDS, identities.pop(), strict=True))
    complete = [
        observation
        for observation in observations
        if _complete_observation(
            observation, verify_artifacts=verify_artifacts, require_license_inventory=require_license_inventory,
        )
    ]
    failed = any(
        "fail" in observation["checks"].values()
        or (verify_artifacts and observation["artifact_audit"]["junit_case_sets_match"] is False)
        for observation in observations
    )
    missing, missing_python = _platform_gaps(complete, python_minors)
    return {
        "schema_version": 1,
        "scope": "saved_local_report_observations",
        "frozen": frozen,
        "observations": observations,
        "systems_without_full_reported_checks": missing,
        "missing_os_python_combinations": missing_python,
        "local_matrix": (
            "failed" if failed else "incomplete" if missing or missing_python
            else "artifact_verified_pass" if verify_artifacts else "reported_pass"
        ),
        "artifact_bytes_verified": verify_artifacts,
        "git_source_audit": source_audit,
        "formal_release_acceptance": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--verify-artifacts", action="store_true")
    parser.add_argument("--require-license-inventory", action="store_true")
    parser.add_argument("--require-python", action="append", default=[])
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("report", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        matrix = summarize(
            args.report, args.commit, verify_artifacts=args.verify_artifacts,
            require_license_inventory=args.require_license_inventory,
            python_minors=tuple(args.require_python),
            source_repo=args.source_repo,
        )
    except (AttributeError, KeyError, OSError, RecursionError, TypeError, ValueError):
        parser.exit(2, "Invalid local acceptance reports or mismatched frozen source.\n")
    print(json.dumps(matrix, indent=2))
    if matrix["local_matrix"] == "failed":
        return 1
    if (args.require_license_inventory or args.require_python) and matrix["local_matrix"] == "incomplete":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

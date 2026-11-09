"""Emit a candidate manifest from verified local release evidence."""

from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

if __package__:
    from .acceptance_evidence import _Evidence, _member_parts, _physical, read_json
    from .acceptance_git_source import _output
    from .acceptance_matrix import _read_report, summarize
    from .release_review import _matrix_digest
else:
    from acceptance_evidence import _Evidence, _member_parts, _physical, read_json
    from acceptance_git_source import _output
    from acceptance_matrix import _read_report, summarize
    from release_review import _matrix_digest

_PYTHON_MINORS = ("3.11", "3.12", "3.14")
_KINDS = ("wheel", "sdist")
_BUILD_CHECKS = {"build", "wheel_install", "sdist_install", "wheel_origin_sdk", "sdist_origin_sdk"}


def build_manifest(
    evidence_root: Path,
    artifact_report: str,
    other_reports: list[Path],
    commit: str,
    *,
    source_repo: Path,
    python_minors: tuple[str, ...] = _PYTHON_MINORS,
) -> dict[str, Any]:
    """Bind the candidate archives to one designated host and a frozen Git revision."""
    from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename
    from packaging.version import Version

    root = evidence_root.resolve(strict=True)
    parts = _member_parts(artifact_report)
    selected, _ = _physical(root, parts)
    matrix = summarize(
        [selected, *other_reports], commit, verify_artifacts=True,
        require_license_inventory=True, python_minors=python_minors, source_repo=source_repo,
    )
    observation = matrix["observations"][0]
    if matrix["local_matrix"] == "failed" or any(
        observation["checks"].get(check) != "pass" for check in _BUILD_CHECKS
    ):
        raise ValueError("Candidate artifacts require passing build and installed-origin evidence.")

    selected, _ = _physical(root, parts)
    report, digest = _read_report(selected, decoder=read_json)
    if digest != observation["report_sha256"]:
        raise ValueError("The designated report changed after verification.")

    pyproject = _output(source_repo, "cat-file", "blob", f"{commit}:pyproject.toml", maximum=1024 * 1024)
    project = tomllib.loads(pyproject.decode("utf-8"))["project"]
    frozen = matrix["frozen"]
    if type(project["name"]) is not str or not project["name"] or project["version"] != frozen["version"]:
        raise ValueError("The distribution identity differs from the frozen Git source.")
    distribution = canonicalize_name(project["name"], validate=True)
    version = Version(project["version"])

    directory = PurePosixPath(*parts[:-1])
    installed = observation["artifact_audit"]["installed_artifact_sha256"]
    installations = {row["kind"]: row["artifact"] for row in report["distribution_installations"]}
    pins = []
    artifacts = []
    for kind in _KINDS:
        artifact = installations[kind]
        relative = PurePosixPath(artifact["path"])
        if kind == "wheel":
            artifact_distribution, artifact_version, _, _ = parse_wheel_filename(relative.name)
        else:
            artifact_distribution, artifact_version = parse_sdist_filename(relative.name)
        if (artifact_distribution, artifact_version) != (distribution, version):
            raise ValueError("The archive filename differs from the frozen distribution identity.")
        if installed.get(kind) != artifact["sha256"] or artifact["size"] <= 0:
            raise ValueError("The designated archive differs from its verified installation.")
        pin = {
            "path": (directory / relative).as_posix(),
            "sha256": artifact["sha256"],
            "size": artifact["size"],
        }
        pins.append(pin)
        artifacts.append({"kind": kind, "filename": relative.name, **pin})
    evidence = _Evidence(root, pins)
    for path in evidence.members:
        evidence.check(path)

    return {
        "schema_version": 1,
        "scope": "local_release_artifact_manifest",
        "distribution": project["name"],
        "frozen": frozen,
        "build_report": {"path": artifact_report, "sha256": digest, "system": observation["system"]},
        "artifacts": artifacts,
        "matrix_sha256": _matrix_digest(matrix),
        "local_matrix": matrix["local_matrix"],
        "producer_authenticated": False,
        "formal_release_acceptance": "blocked",
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--artifact-report", required=True, help="Build report path relative to the evidence root")
    parser.add_argument("--require-python", action="append")
    parser.add_argument("report", type=Path, nargs="*", help="Additional local reports for the release matrix")
    args = parser.parse_args()
    try:
        manifest = build_manifest(
            args.evidence_root, args.artifact_report, args.report, args.commit,
            source_repo=args.source_repo, python_minors=tuple(args.require_python or _PYTHON_MINORS),
        )
    except (AttributeError, IndexError, KeyError, OSError, RecursionError, TypeError, ValueError):
        parser.exit(2, "Invalid or inconsistent release artifact evidence.\n")
    print(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Emit a candidate manifest or verify saved candidate archives offline."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

if __package__:
    from .acceptance_evidence import _SHA256, _Evidence, _member_parts, _physical, read_json
    from .acceptance_git_source import _output
    from .acceptance_matrix import _IDENTITY_FIELDS, _REQUIRED_SYSTEMS, _read_report, summarize
    from .release_review import _matrix_digest
else:
    from acceptance_evidence import _SHA256, _Evidence, _member_parts, _physical, read_json
    from acceptance_git_source import _output
    from acceptance_matrix import _IDENTITY_FIELDS, _REQUIRED_SYSTEMS, _read_report, summarize
    from release_review import _matrix_digest

if TYPE_CHECKING:
    from packaging.version import Version

_PYTHON_MINORS = ("3.11", "3.12", "3.14")
_KINDS = ("wheel", "sdist")
_BUILD_CHECKS = {"build", "wheel_install", "sdist_install", "wheel_origin_sdk", "sdist_origin_sdk"}
_SCOPE = "local_release_artifact_manifest"
_MANIFEST_FIELDS = {
    "schema_version", "scope", "distribution", "frozen", "build_report", "artifacts",
    "matrix_sha256", "local_matrix", "producer_authenticated", "formal_release_acceptance",
    "publication_authorized",
}


def _check_archive_filename(kind: str, filename: str, distribution: str, version: Version) -> None:
    from packaging.utils import parse_sdist_filename, parse_wheel_filename

    if kind == "wheel":
        archive_distribution, archive_version, _, _ = parse_wheel_filename(filename)
    else:
        if not filename.endswith(".tar.gz"):
            raise ValueError("The source archive must be a .tar.gz file.")
        archive_distribution, archive_version = parse_sdist_filename(filename)
    if (archive_distribution, archive_version) != (distribution, version):
        raise ValueError("The archive filename differs from the frozen distribution identity.")


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
    from packaging.utils import canonicalize_name
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
        _check_archive_filename(kind, relative.name, distribution, version)
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
        "scope": _SCOPE,
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


def _is_sha256(value: Any) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def verify_manifest(
    manifest_path: Path, evidence_root: Path, *, manifest_sha256: str,
) -> dict[str, Any]:
    """Check the candidate archives using an independently trusted manifest digest."""
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    if type(manifest_sha256) is not str or not _SHA256.fullmatch(manifest_sha256.lower()):
        raise ValueError("A trusted manifest SHA-256 is required.")
    manifest_sha256 = manifest_sha256.lower()
    manifest_root = manifest_path.parent.resolve(strict=True)
    manifest_name = manifest_path.name
    _, info = _physical(manifest_root, _member_parts(manifest_name))
    manifest_file = _Evidence(manifest_root, [
        {"path": manifest_name, "sha256": manifest_sha256, "size": info.st_size},
    ])
    manifest = read_json(manifest_file.check(manifest_name, retain=True))
    if (
        type(manifest) is not dict or set(manifest) != _MANIFEST_FIELDS
        or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
        or manifest["scope"] != _SCOPE
        or manifest["local_matrix"] not in ("incomplete", "artifact_verified_pass")
        or not _is_sha256(manifest["matrix_sha256"])
        or manifest["producer_authenticated"] is not False
        or manifest["formal_release_acceptance"] != "blocked"
        or manifest["publication_authorized"] is not False
    ):
        raise ValueError("Invalid candidate manifest schema.")

    frozen = manifest["frozen"]
    if (
        type(frozen) is not dict or set(frozen) != set(_IDENTITY_FIELDS)
        or any(type(frozen[field]) is not str for field in _IDENTITY_FIELDS)
        or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,63}", frozen["version"])
        or not re.fullmatch(r"[0-9a-f]{40}", frozen["commit_sha"])
        or not re.fullmatch(r"[0-9a-f]{40}", frozen["tree_sha"])
        or not _is_sha256(frozen["source_snapshot_sha256"])
        or type(manifest["distribution"]) is not str
    ):
        raise ValueError("Invalid frozen distribution identity.")
    distribution = canonicalize_name(manifest["distribution"], validate=True)
    version = Version(frozen["version"])

    build_report = manifest["build_report"]
    if (
        type(build_report) is not dict or set(build_report) != {"path", "sha256", "system"}
        or not _is_sha256(build_report["sha256"])
        or type(build_report["system"]) is not str or build_report["system"] not in _REQUIRED_SYSTEMS
    ):
        raise ValueError("Invalid build report reference.")
    report_parts = _member_parts(build_report["path"])

    artifacts = manifest["artifacts"]
    if type(artifacts) is not list or len(artifacts) != len(_KINDS):
        raise ValueError("The candidate manifest must pin one wheel and one source archive.")
    pins = []
    seen = set()
    for artifact in artifacts:
        if type(artifact) is not dict or set(artifact) != {"kind", "filename", "path", "sha256", "size"}:
            raise ValueError("Invalid candidate archive record.")
        kind, filename, size = artifact["kind"], artifact["filename"], artifact["size"]
        if (
            kind not in _KINDS or kind in seen or type(size) is not int or size <= 0
            or _member_parts(artifact["path"]) != (*report_parts[:-1], "artifacts", filename)
        ):
            raise ValueError("Invalid or repeated candidate archive.")
        _check_archive_filename(kind, filename, distribution, version)
        seen.add(kind)
        pins.append({field: artifact[field] for field in ("path", "sha256", "size")})
    evidence = _Evidence(evidence_root, pins)
    for path in evidence.members:
        evidence.check(path)

    return {
        "schema_version": 1,
        "scope": "local_release_artifact_manifest_verification",
        "manifest_sha256": manifest_sha256,
        "frozen": frozen,
        "checked_artifacts": sorted(pins, key=lambda pin: pin["path"]),
        "artifact_bytes_verified": True,
        "build_report_bytes_verified": False,
        "producer_authenticated": False,
        "formal_release_acceptance": "blocked",
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit")
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--artifact-report", help="Build report path relative to the evidence root")
    parser.add_argument("--require-python", action="append")
    parser.add_argument("--verify-manifest", type=Path, help="Check a saved manifest and its copied archives")
    parser.add_argument("--manifest-sha256", help="Independently trusted SHA-256 of the original manifest bytes")
    parser.add_argument("report", type=Path, nargs="*", help="Additional local reports for the release matrix")
    args = parser.parse_args()
    if args.verify_manifest is not None:
        if args.manifest_sha256 is None:
            parser.error("--verify-manifest requires --manifest-sha256")
        generation_options = (args.commit, args.source_repo, args.artifact_report, args.require_python)
        if any(value is not None for value in generation_options) or args.report:
            parser.error("--verify-manifest cannot be combined with generation inputs")
    else:
        if args.manifest_sha256 is not None:
            parser.error("--manifest-sha256 requires --verify-manifest")
        if None in (args.commit, args.source_repo, args.artifact_report):
            parser.error("generation requires --commit, --source-repo and --artifact-report")
    try:
        if args.verify_manifest is not None:
            manifest = verify_manifest(
                args.verify_manifest, args.evidence_root, manifest_sha256=args.manifest_sha256,
            )
        else:
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

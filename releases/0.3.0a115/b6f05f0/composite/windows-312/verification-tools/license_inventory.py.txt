"""Inventory license metadata for an installed distribution and its runtime dependencies.

Run in the selected package environment with the pinned packaging tooling.
The report records declarations and installed file hashes for human review.
It does not resolve licenses, install dependencies or authorize distribution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

_FILE_LIMIT = 1024 * 1024
_LICENSE_NAMES = ("license", "licence", "copying", "notice", "copyright")


def _license_files(distribution: metadata.Distribution) -> list[dict[str, Any]]:
    root = Path(distribution.locate_file("")).resolve(strict=True)
    result = []
    files = distribution.files
    if files is None:
        return result
    for member in files:
        relative = PurePosixPath(member.as_posix())
        parts = relative.parts
        if (
            relative.is_absolute()
            or len(parts) < 2
            or not parts[0].endswith((".dist-info", ".egg-info"))
            or any(part in (".", "..") or "\\" in part or ":" in part for part in parts)
        ):
            continue
        if parts[1] != "licenses" and not parts[-1].casefold().startswith(_LICENSE_NAMES):
            continue
        if len(result) >= 128:
            raise ValueError("Distribution has too many license files.")
        entry: dict[str, Any] = {"member": relative.as_posix(), "status": "unavailable"}
        expected = root.joinpath(*parts)
        try:
            actual = Path(distribution.locate_file(member)).resolve(strict=True)
            if actual == expected and actual.is_file():
                with actual.open("rb") as stream:
                    content = stream.read(_FILE_LIMIT + 1)
                if len(content) <= _FILE_LIMIT:
                    entry.update(
                        status="recorded",
                        bytes=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                else:
                    entry["status"] = "size_limit"
        except OSError:
            pass
        result.append(entry)
    return sorted(result, key=lambda item: item["member"])


def _declaration(distribution: metadata.Distribution) -> dict[str, Any]:
    fields = distribution.metadata
    expression = fields.get("License-Expression")
    legacy = fields.get("License")
    return {
        "version": distribution.version,
        "license_expression": expression if expression and len(expression) <= 512 else None,
        "legacy_license": legacy.strip() if legacy and len(legacy) <= 512 else None,
        "license_classifiers": sorted(
            {
                value
                for value in fields.get_all("Classifier", [])
                if value.startswith("License ::") and len(value) <= 256
            }
        ),
        "declared_license_files": sorted(
            {
                value
                for value in fields.get_all("License-File", [])
                if 0 < len(value) <= 512
                and not PurePosixPath(value).is_absolute()
                and ".." not in PurePosixPath(value).parts
                and "\\" not in value
                and ":" not in value
            }
        ),
        "license_files": _license_files(distribution),
    }


def inventory(root: str) -> dict[str, Any]:
    name = canonicalize_name(root, validate=True)
    pending = deque([(name, frozenset())])
    visited: dict[str, frozenset[str]] = {}
    distributions: dict[str, metadata.Distribution] = {}
    declarations: dict[str, dict[str, Any]] = {}
    issues: set[tuple[str, str]] = set()
    edges: set[tuple[str, str]] = set()
    expansions = 0
    while pending:
        current, extra = pending.popleft()
        if current in visited and extra <= visited[current]:
            continue
        visited[current] = visited.get(current, frozenset()) | extra
        expansions += 1
        if len(visited) > 256 or expansions > 1024:
            raise ValueError("Dependency graph exceeds the inventory bound.")
        try:
            if current not in distributions:
                distributions[current] = metadata.distribution(current)
            installed = distributions[current]
        except metadata.PackageNotFoundError:
            issues.add((current, "missing_distribution"))
            continue
        if current not in declarations:
            declarations[current] = _declaration(installed)
        required = installed.requires or []
        if len(required) > 512:
            raise ValueError("Distribution has too many dependency declarations.")
        for declared in required:
            try:
                dependency = Requirement(declared)
            except InvalidRequirement:
                issues.add((current, "invalid_dependency_metadata"))
                continue
            if dependency.marker is not None and not any(
                dependency.marker.evaluate({"extra": context})
                for context in ("", *sorted(visited[current]))
            ):
                continue
            child = canonicalize_name(dependency.name)
            edges.add((current, child))
            if len(edges) > 4096:
                raise ValueError("Dependency graph exceeds the edge bound.")
            if dependency.url is not None:
                issues.add((child, "direct_url_dependency"))
            try:
                if child not in distributions:
                    distributions[child] = metadata.distribution(child)
                if not dependency.specifier.contains(
                    Version(distributions[child].version), prereleases=True
                ):
                    issues.add((child, "dependency_version_mismatch"))
            except metadata.PackageNotFoundError:
                issues.add((child, "missing_distribution"))
            except InvalidVersion:
                issues.add((child, "invalid_installed_version"))
            pending.append(
                (child, frozenset(canonicalize_name(item) for item in dependency.extras))
            )
            if len(pending) > 8192:
                raise ValueError("Dependency graph exceeds the pending item bound.")
    for dependency, declaration in declarations.items():
        if not any(
            declaration[key]
            for key in ("license_expression", "legacy_license", "license_classifiers")
        ):
            issues.add((dependency, "no_license_declaration"))
        recorded = {
            entry["member"].split("/", 1)[1]
            for entry in declaration["license_files"]
            if entry["status"] == "recorded"
        }
        if not recorded:
            issues.add((dependency, "no_recorded_license_file"))
        if any(
            name not in recorded and f"licenses/{name}" not in recorded
            for name in declaration["declared_license_files"]
        ):
            issues.add((dependency, "declared_license_file_missing"))
    return {
        "schema_version": 1,
        "root": name,
        "scope": "installed_runtime_dependency_metadata",
        "distributions": declarations,
        "edges": sorted(edges),
        "review_items": [{"distribution": item, "code": issue} for item, issue in sorted(issues)],
        "license_review": "pending",
        "publication_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", default="agentsync-local")
    args = parser.parse_args()
    try:
        report = inventory(args.distribution)
    except (OSError, RecursionError, ValueError):
        parser.exit(2, "Could not inventory the selected package environment.\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["review_items"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

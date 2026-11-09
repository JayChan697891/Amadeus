"""Assemble independent review declarations and checked local release evidence.

The declared reviewer and evidence classifications require human verification.
This tool checks identities, coverage and bytes, then prepares a review packet.
It does not authenticate the reviewer or approve a release.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from .acceptance_evidence import _Evidence, _member_parts, _physical, read_json
    from .acceptance_git_source import _output
    from .acceptance_matrix import (
        RELEASE_PYTHON_MINORS, _complete_observation, _platform_gaps, _read_report, matrix_digest, summarize,
    )
    from .release_manifest import verify_manifest
else:
    from acceptance_evidence import _Evidence, _member_parts, _physical, read_json
    from acceptance_git_source import _output
    from acceptance_matrix import (
        RELEASE_PYTHON_MINORS, _complete_observation, _platform_gaps, _read_report, matrix_digest, summarize,
    )
    from release_manifest import verify_manifest

_LIMIT = 4 * 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_STATUSES = ("passed", "failed", "not_run", "blocked", "restricted", "unverified")
_COUNTS = (5, 5, 5, 4, 5, 5, 5, 4, 2, 2)
_REQUIREMENTS = {f"M{milestone}-{index:02d}" for milestone, count in enumerate(_COUNTS) for index in range(1, count + 1)}
_SCENARIOS = {f"T{index:02d}" for index in range(1, 17)}
_REGISTER_PATH = "docs/acceptance/requirements.json"
_EVIDENCE_KINDS = {
    "component", "security", "package", "license", "mcp_host", "codex", "claude_code",
    "cursor", "real_relay", "conflict", "cross_platform", "independent_review",
}
_REQUIRED_KINDS = {
    "M2-05": {"mcp_host"},
    "M4-04": {"conflict"},
    "M5-04": {"independent_review"},
    "M5-05": {"security"},
    "M6-03": {"codex"},
    "M6-04": {"claude_code"},
    "M6-05": {"cursor"},
    "M7-02": {"real_relay"},
    "M9-01": {"cross_platform"},
    "M9-02": {"package", "license"},
    "T07": {"security"},
    "T09": {"conflict"},
    "T10": {"independent_review"},
    "T11": {"security"},
    "T12": {"security"},
    "T13": {"codex", "claude_code", "cursor", "independent_review"},
    "T16": {"package"},
}


def _read(path: Path) -> tuple[dict[str, Any], str]:
    if (
        not path.is_file() or path.is_symlink()
        or getattr(path.lstat(), "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("A regular review input file is required.")
    with path.open("rb") as stream:
        raw = stream.read(_LIMIT + 1)
    if len(raw) > _LIMIT:
        raise ValueError("Review input exceeds its size limit.")
    data = read_json(raw)
    if type(data) is not dict or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported review input schema.")
    return data, hashlib.sha256(raw).hexdigest()


def _traceability(manifest: dict[str, Any]) -> dict[str, str]:
    if type(manifest.get("requirement_count")) is not int or manifest["requirement_count"] != len(_REQUIREMENTS):
        raise ValueError("Invalid formal requirement count.")
    labels: dict[str, str] = {}
    for key, expected in (("requirements", _REQUIREMENTS), ("scenarios", _SCENARIOS)):
        rows = manifest[key]
        if type(rows) is not list or len(rows) != len(expected):
            raise ValueError("Incomplete release traceability register.")
        seen = set()
        for row in rows:
            identity, title = row["id"], row["title"]
            if identity not in expected or identity in seen or type(title) is not str or not title:
                raise ValueError("Invalid release traceability record.")
            seen.add(identity)
            labels[identity] = title
    return labels


def _checked_members(root: Path, records: Any) -> dict[str, dict[str, Any]]:
    if type(records) is not list or len(records) > 512:
        raise ValueError("Invalid independent evidence list.")
    members = {}
    rows: dict[str, dict[str, Any]] = {}
    client_by_hash: dict[str, str] = {}
    for record in records:
        if type(record) is not dict or set(record) != {"id", "kind", "path", "sha256", "size"}:
            raise ValueError("Invalid independent evidence record.")
        key = record["id"]
        if type(key) is not str or not _IDENTIFIER.fullmatch(key) or key in members:
            raise ValueError("Invalid or repeated independent evidence ID.")
        if type(record["kind"]) is not str or record["kind"] not in _EVIDENCE_KINDS:
            raise ValueError("Unknown independent evidence classification.")
        path = record["path"]
        if type(path) is not str:
            raise ValueError("Invalid independent evidence path.")
        member = {field: record[field] for field in ("path", "sha256", "size")}
        if path in rows and rows[path] != member:
            raise ValueError("Conflicting pins for one independent evidence file.")
        kind, checksum = record["kind"], record["sha256"]
        if kind in {"codex", "claude_code", "cursor"} and type(checksum) is str:
            if client_by_hash.setdefault(checksum.lower(), kind) != kind:
                raise ValueError("Real-client evidence must be recorded separately for each client.")
        members[key] = record
        rows[path] = member
    if rows:
        checked = _Evidence(root, list(rows.values()))
        for path in checked.members:
            checked.check(path)
    return members


def _inputs(
    manifest_path: Path, local_reports: list[Path], commit: str,
    python_minors: tuple[str, ...], source_repo: Path | None,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    matrix = summarize(
        local_reports, commit, verify_artifacts=True,
        require_license_inventory=True, python_minors=python_minors, source_repo=source_repo,
    )
    manifest, manifest_sha = _read(manifest_path)
    if source_repo is not None:
        frozen_register = _output(
            source_repo, "cat-file", "blob", f"{commit}:{_REGISTER_PATH}", maximum=_LIMIT,
        )
        if hashlib.sha256(frozen_register).hexdigest() != manifest_sha:
            raise ValueError("The requirements register differs from the frozen Git revision.")
    return matrix, manifest_sha, _traceability(manifest)


def prepare(
    manifest_path: Path, local_reports: list[Path], commit: str, reviewer_id: str,
    *, python_minors: tuple[str, ...] = RELEASE_PYTHON_MINORS,
    source_repo: Path | None = None,
) -> dict[str, Any]:
    """Return a blank review form bound to the supplied evidence and coverage."""
    if not _IDENTIFIER.fullmatch(reviewer_id):
        raise ValueError("Invalid declared reviewer ID.")
    matrix, manifest_sha, labels = _inputs(manifest_path, local_reports, commit, python_minors, source_repo)
    return {
        "schema_version": 1,
        "commit_sha": commit,
        "version": matrix["frozen"]["version"],
        "requirements_sha256": manifest_sha,
        "matrix_sha256": matrix_digest(matrix),
        "reviewer_id": reviewer_id,
        "independence_declared": False,
        "evidence": [],
        "decisions": [
            {"id": identity, "status": "not_run", "evidence_ids": [], "reason": "Pending review."}
            for identity in labels
        ],
    }


def _bind_candidate(
    matrix: dict[str, Any], digest: str, evidence_root: Path, path: Path, manifest_sha256: str,
    python_minors: tuple[str, ...],
) -> dict[str, Any]:
    candidate = verify_manifest(path, evidence_root, manifest_sha256=manifest_sha256)
    if (
        matrix["git_source_audit"] is None or candidate["frozen"] != matrix["frozen"]
        or candidate["matrix_sha256"] != digest or candidate["local_matrix"] != matrix["local_matrix"]
    ):
        raise ValueError("Release candidate describes a different frozen matrix.")
    build = candidate["build_report"]
    build_path, _ = _physical(evidence_root.resolve(strict=True), _member_parts(build["path"]))
    _, build_sha256 = _read_report(build_path, decoder=read_json)
    if build_sha256 != build["sha256"]:
        raise ValueError("The candidate build report differs from its manifest reference.")
    observation = next(
        (row for row in matrix["observations"] if row["report_sha256"] == build["sha256"]), None
    )
    pins = {item["kind"]: item["sha256"] for item in candidate["checked_artifacts"]}
    if (
        observation is None or observation["system"] != build["system"]
        or observation["checks"].get("build") != "pass"
        or observation["artifact_audit"]["installed_artifact_sha256"] != pins
        or any(observation["checks"].get(kind + "_origin_sdk") != "pass" for kind in pins)
    ):
        raise ValueError("Release candidate archives differ from the reviewed build.")
    matching = [
        row for row in matrix["observations"]
        if row["artifact_audit"]["installed_artifact_sha256"] == pins
        and _complete_observation(row, verify_artifacts=True, require_license_inventory=True)
        and all(row["checks"].get(kind + "_console_smoke") == "pass" for kind in pins)
    ]
    release_minors = tuple(sorted(set(python_minors) | set(RELEASE_PYTHON_MINORS)))
    systems, combinations = _platform_gaps(matching, release_minors)
    return candidate | {
        "build_report_verified_in_matrix": True,
        "build_report_bytes_verified": True,
        "matching_install_report_sha256": sorted(row["report_sha256"] for row in matching),
        "systems_without_exact_candidate_checks": systems,
        "missing_exact_candidate_os_python_combinations": combinations,
    }


def assemble(
    manifest_path: Path,
    review_path: Path,
    evidence_root: Path,
    local_reports: list[Path],
    commit: str,
    *,
    python_minors: tuple[str, ...] = RELEASE_PYTHON_MINORS,
    source_repo: Path | None = None,
    candidate_manifest: Path | None = None,
    candidate_sha256: str | None = None,
) -> dict[str, Any]:
    if (candidate_manifest is None) != (candidate_sha256 is None):
        raise ValueError("Candidate manifest and its trusted SHA-256 are required together.")
    matrix, manifest_sha, labels = _inputs(manifest_path, local_reports, commit, python_minors, source_repo)
    digest = matrix_digest(matrix)
    review, review_sha = _read(review_path)
    if set(review) != {
        "schema_version", "commit_sha", "version", "requirements_sha256", "matrix_sha256",
        "reviewer_id", "independence_declared", "evidence", "decisions",
    }:
        raise ValueError("Invalid independent review envelope.")
    if (
        type(review["schema_version"]) is not int or review["schema_version"] != 1
        or review["commit_sha"] != commit or review["version"] != matrix["frozen"]["version"]
        or review["requirements_sha256"] != manifest_sha or review["matrix_sha256"] != digest
        or type(review["reviewer_id"]) is not str or not _IDENTIFIER.fullmatch(review["reviewer_id"])
        or type(review["independence_declared"]) is not bool
    ):
        raise ValueError("Independent review describes a different release input.")
    members = _checked_members(evidence_root, review["evidence"])
    rows = review["decisions"]
    if type(rows) is not list or len(rows) > len(labels):
        raise ValueError("Invalid independent review decisions.")
    decisions = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"id", "status", "evidence_ids", "reason"}:
            raise ValueError("Invalid independent review decision.")
        identity, status, refs = row["id"], row["status"], row["evidence_ids"]
        reason = row["reason"]
        if (
            type(identity) is not str or identity not in labels or identity in decisions
            or type(status) is not str or status not in _STATUSES
            or type(refs) is not list or len(refs) > 32
            or any(type(ref) is not str or ref not in members for ref in refs)
            or len(set(refs)) != len(refs)
            or type(reason) is not str or len(reason) > 1000 or "\0" in reason
            or (status != "passed" and not reason.strip())
        ):
            raise ValueError("Invalid, unknown or repeated review decision.")
        kinds = {members[ref]["kind"] for ref in refs}
        if status == "passed" and (
            not review["independence_declared"] or not refs or not _REQUIRED_KINDS.get(identity, set()) <= kinds
        ):
            raise ValueError("A declared pass lacks its required independent evidence classes.")
        decisions[identity] = (status, refs, reason)
    cases = []
    for identity, title in labels.items():
        status, refs, reason = decisions.get(identity, ("not_run", [], "No independent review recorded."))
        cases.append({
            "id": identity, "title": title, "declared_status": status,
            "evidence_ids": refs, "reason": reason,
        })
    counts = Counter(case["declared_status"] for case in cases)
    candidate = (
        _bind_candidate(matrix, digest, evidence_root, candidate_manifest, candidate_sha256, python_minors)
        if candidate_manifest is not None and candidate_sha256 is not None else None
    )
    blockers = []
    if counts["passed"] != len(cases):
        blockers.append("review_decisions_incomplete")
    if matrix["local_matrix"] != "artifact_verified_pass":
        blockers.append("local_matrix_incomplete")
    if matrix["git_source_audit"] is None:
        blockers.append("git_source_not_audited")
    if candidate is None:
        blockers.append("release_candidate_not_bound")
    elif candidate["systems_without_exact_candidate_checks"] or candidate["missing_exact_candidate_os_python_combinations"]:
        blockers.append("exact_candidate_platform_matrix_incomplete")
    packet = {
        "schema_version": 1,
        "scope": "evidence_packet_for_independent_release_decision",
        "frozen": matrix["frozen"],
        "requirements_sha256": manifest_sha,
        "review_sha256": review_sha,
        "requirements_git_bound": source_repo is not None,
        "reviewer_declared": review["reviewer_id"],
        "reviewer_authenticated": False,
        "matrix_sha256": digest,
        "local_matrix": matrix["local_matrix"],
        "git_source_audit": matrix["git_source_audit"],
        "missing_os_python_combinations": matrix["missing_os_python_combinations"],
        "declared_status_counts": {status: counts[status] for status in _STATUSES},
        "cases": cases,
        "evidence": members,
        "packet_state": "incomplete" if blockers else "complete_for_independent_decision",
        "packet_blockers": blockers,
        "formal_release_acceptance": "blocked",
        "publication_authorized": False,
    }
    if candidate is not None:
        packet["release_candidate"] = candidate
    return packet


def _cell(value: str) -> str:
    plain = " ".join(value.split())
    return re.sub(r"[&<>\[\]|\\`*_!~:]", lambda match: f"&#{ord(match[0])};", plain)


def render_markdown(packet: dict[str, Any]) -> str:
    """Render the checked packet without converting reviewer declarations to approvals."""
    frozen = packet["frozen"]
    source_check = "verified against local Git objects" if packet["git_source_audit"] else "not run"
    lines = [
        "# Release Acceptance Report",
        "",
        f"Formal release acceptance is **{_cell(packet['formal_release_acceptance'].upper())}**.",
        "Publication requires separate authorization. Reviewer identity and evidence classifications",
        "are declarations that require independent confirmation.",
        "",
        f"- Version `{frozen['version']}`",
        f"- Git commit `{frozen['commit_sha']}`",
        f"- Requirements SHA-256 `{packet['requirements_sha256']}`",
        "- Requirements source: " + (
            "matched to the frozen Git revision" if packet["requirements_git_bound"] else "not checked against Git"
        ),
        f"- Review SHA-256 `{packet['review_sha256']}`",
        f"- Matrix SHA-256 `{packet['matrix_sha256']}`",
        f"- Declared reviewer `{packet['reviewer_declared']}`",
        f"- Local matrix `{packet['local_matrix']}`",
        f"- Frozen source check {source_check}",
        f"- Packet state `{packet['packet_state']}`",
        "- Packet blockers: " + (", ".join(f"`{item}`" for item in packet["packet_blockers"]) or "none"),
        "",
        "## Declared results",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{status}` | {packet['declared_status_counts'][status]} |" for status in _STATUSES)
    candidate = packet.get("release_candidate")
    if candidate is not None:
        lines.extend([
            "", "## Bound release archives", "",
            f"Manifest SHA-256 `{candidate['manifest_sha256']}`", "",
            "| Kind | Relative path | Bytes | SHA-256 |", "| --- | --- | ---: | --- |",
        ])
        for artifact in candidate["checked_artifacts"]:
            lines.append(
                f"| `{artifact['kind']}` | {_cell(artifact['path'])} | "
                f"{artifact['size']} | `{artifact['sha256']}` |"
            )
        systems = candidate["systems_without_exact_candidate_checks"]
        combinations = candidate["missing_exact_candidate_os_python_combinations"]
        lines.extend([
            "", "Platforms missing full checks against these exact archives: "
            + (", ".join(_cell(system) for system in systems) or "none"),
            "", "Missing platform/Python combinations for these exact archives: "
            + (", ".join(f"{_cell(row['system'])} {row['python_minor']}" for row in combinations) or "none"),
        ])
    missing = packet["missing_os_python_combinations"]
    if missing:
        lines.extend(["", "## OS and Python combinations without complete evidence", ""])
        lines.extend(f"- {_cell(row['system'])} / Python {_cell(row['python_minor'])}" for row in missing)
    lines.extend([
        "", "## Requirements and scenarios", "",
        "| ID | Case | Declared status | Evidence IDs | Reason |",
        "| --- | --- | --- | --- | --- |",
    ])
    for case in packet["cases"]:
        refs = ", ".join(f"`{ref}`" for ref in case["evidence_ids"]) or "—"
        lines.append(
            f"| `{case['id']}` | {_cell(case['title'])} | `{case['declared_status']}` | "
            f"{refs} | {_cell(case['reason'])} |"
        )
    lines.extend([
        "", "## Checked evidence files", "",
        "| ID | Declared kind | Relative path | Bytes | SHA-256 |",
        "| --- | --- | --- | ---: | --- |",
    ])
    for identity, item in sorted(packet["evidence"].items()):
        lines.append(
            f"| `{identity}` | `{item['kind']}` | {_cell(item['path'])} | "
            f"{item['size']} | `{item['sha256']}` |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--review", type=Path)
    mode.add_argument("--prepare", metavar="REVIEWER_ID")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--candidate-sha256", help="Independently trusted manifest SHA-256")
    parser.add_argument("--require-python", action="append")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("report", type=Path, nargs="+")
    args = parser.parse_args()
    if args.review is not None and args.evidence_root is None:
        parser.error("--review requires --evidence-root")
    if args.prepare is not None and args.format != "json":
        parser.error("--prepare emits the JSON decision template")
    if (args.candidate_manifest is None) != (args.candidate_sha256 is None):
        parser.error("--candidate-manifest and --candidate-sha256 are required together")
    if args.candidate_manifest is not None and (args.review is None or args.source_repo is None):
        parser.error("candidate binding requires --review and --source-repo")
    minors = tuple(args.require_python or RELEASE_PYTHON_MINORS)
    try:
        if args.prepare is not None:
            packet = prepare(
                args.requirements, args.report, args.commit, args.prepare,
                python_minors=minors, source_repo=args.source_repo,
            )
        else:
            packet = assemble(
                args.requirements, args.review, args.evidence_root, args.report, args.commit,
                python_minors=minors, source_repo=args.source_repo,
                candidate_manifest=args.candidate_manifest, candidate_sha256=args.candidate_sha256,
            )
    except (AttributeError, IndexError, KeyError, OSError, RecursionError, TypeError, ValueError):
        parser.exit(2, "Invalid or inconsistent release review inputs.\n")
    if args.format == "markdown":
        sys.stdout.buffer.write(render_markdown(packet).encode("utf-8", errors="backslashreplace"))
    else:
        print(json.dumps(packet, ensure_ascii=True, indent=2))
    if args.prepare is not None:
        return 0
    return 0 if packet["packet_state"] == "complete_for_independent_decision" else 1


if __name__ == "__main__":
    raise SystemExit(main())

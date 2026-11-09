"""Check bytes and cross-references in one saved local acceptance report.

Hashes and consistent records are evidence integrity checks. They do not
authenticate the producer, prove real-client behavior or authorize a release.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_MEMBER = 1024 * 1024 * 1024
_MAX_TOTAL = 4 * _MAX_MEMBER
_MAX_STRUCTURED = 16 * 1024 * 1024
_SUITES = {"pytest": "junit.xml", "wheel_pytest": "wheel-junit.xml", "sdist_pytest": "sdist-junit.xml"}
_COUNT_FIELDS = ("tests", "failures", "errors", "skipped")
_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", re.IGNORECASE)
_PROCESS_FIELDS = (
    "id", "command", "cwd", "exit_code", "started_at", "finished_at", "log", "log_sha256",
    "credential_redactions", "log_truncated", "provenance", "timeout_seconds",
)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate evidence JSON field.")
        result[key] = value
    return result


def _invalid_constant(_: str) -> Any:
    raise ValueError("Invalid evidence JSON number.")


def _finite(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Invalid evidence JSON number.")
    return value


def read_json(data: bytes) -> Any:
    return json.loads(
        data.decode("utf-8"), object_pairs_hook=_unique,
        parse_constant=_invalid_constant, parse_float=_finite,
    )


def _member_parts(name: Any) -> tuple[str, ...]:
    if type(name) is not str or not 1 <= len(name) <= 1024:
        raise ValueError("Invalid evidence member path.")
    if any(ord(char) < 32 or char in '\\:*?"<>|' for char in name):
        raise ValueError("Invalid evidence member path.")
    relative = PurePosixPath(name)
    if not relative.parts or relative.is_absolute() or relative.as_posix() != name or any(
        part in (".", "..") or part.endswith((".", " ")) or _DEVICE.match(part)
        for part in relative.parts
    ):
        raise ValueError("Invalid evidence member path.")
    return relative.parts


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _physical(root: Path, parts: tuple[str, ...]) -> tuple[Path, os.stat_result]:
    path = root
    for index, part in enumerate(parts):
        path = path / part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Evidence links and reparse points are unsupported.")
        predicate = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
        if not predicate(info.st_mode):
            raise ValueError("Evidence member is not an ordinary file.")
    return path, info


@dataclass(frozen=True, slots=True)
class _Member:
    sha256: str
    size: int


class _Evidence:
    def __init__(self, root: Path, rows: Any) -> None:
        if type(rows) is not list or not 1 <= len(rows) <= 4096:
            raise ValueError("Invalid evidence artifact manifest.")
        self.root = root.resolve(strict=True)
        self.members: dict[str, _Member] = {}
        names: set[str] = set()
        total = 0
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "sha256", "size"}:
                raise ValueError("Invalid evidence artifact record.")
            name, digest, size = row["path"], row["sha256"], row["size"]
            _member_parts(name)
            portable = unicodedata.normalize("NFC", name).casefold()
            if (
                portable in names or type(digest) is not str or not _SHA256.fullmatch(digest)
                or type(size) is not int or not 0 <= size <= _MAX_MEMBER
            ):
                raise ValueError("Invalid or repeated evidence artifact.")
            names.add(portable)
            total += size
            if total > _MAX_TOTAL:
                raise ValueError("Evidence exceeds the total byte limit.")
            self.members[name] = _Member(digest, size)

    def check(self, name: str, *, retain: bool = False) -> bytes:
        item = self.members[name]
        if retain and item.size > _MAX_STRUCTURED:
            raise ValueError("Structured evidence exceeds the byte limit.")
        parts = _member_parts(name)
        path, info = _physical(self.root, parts)
        if info.st_size != item.size:
            raise ValueError("Evidence file size differs from its manifest.")
        digest = hashlib.sha256()
        retained = bytearray()
        read = 0
        flags = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with open(path, "rb", opener=lambda name, mode: os.open(name, mode | flags)) as stream:
            if _identity(os.fstat(stream.fileno())) != _identity(info):
                raise ValueError("Evidence file changed before reading.")
            while chunk := stream.read(min(1024 * 1024, item.size + 1 - read)):
                read += len(chunk)
                if read > item.size:
                    raise ValueError("Evidence file grew while reading.")
                digest.update(chunk)
                if retain:
                    retained.extend(chunk)
            if _identity(os.fstat(stream.fileno())) != _identity(info):
                raise ValueError("Evidence file changed while reading.")
        if (
            read != item.size or digest.hexdigest() != item.sha256
            or _identity(_physical(self.root, parts)[1]) != _identity(info)
        ):
            raise ValueError("Evidence file bytes do not match the manifest.")
        return bytes(retained)

    def require_digest(self, name: str, digest: Any) -> None:
        if name not in self.members or self.members[name].sha256 != digest:
            raise ValueError("Evidence cross-reference does not match its manifest.")


def _junit(data: bytes) -> tuple[dict[str, int], str]:
    text = data.decode("utf-8")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise ValueError("JUnit declarations are unsupported.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("Malformed JUnit evidence.") from exc
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("Unsupported JUnit evidence.")
    counts = dict.fromkeys(_COUNT_FIELDS, 0)
    identities: set[tuple[str, str]] = set()
    for case in root.iter("testcase"):
        classname, name = case.get("classname", ""), case.get("name", "")
        identity = (classname, name)
        if not classname or not name or identity in identities or len(identities) >= 50000:
            raise ValueError("Invalid or repeated JUnit case identity.")
        identities.add(identity)
        statuses = [element.tag for element in case if element.tag in ("failure", "error", "skipped")]
        if len(statuses) > 1:
            raise ValueError("JUnit case has conflicting outcomes.")
        counts["tests"] += 1
        if statuses:
            counts[{"failure": "failures", "error": "errors", "skipped": "skipped"}[statuses[0]]] += 1
    case_hash = hashlib.sha256(json.dumps(sorted(identities), ensure_ascii=True).encode("ascii")).hexdigest()
    return counts, case_hash


def _bound_installations(report: dict[str, Any], evidence: _Evidence) -> dict[str, str]:
    rows = report.get("distribution_installations")
    if type(rows) is not list or len(rows) > 2:
        raise ValueError("Invalid installation records.")
    results: dict[str, str] = {}
    checks = {row["id"]: row for row in report["checks"]}
    seen: set[str] = set()
    for row in rows:
        kind = row["kind"]
        if kind not in ("wheel", "sdist") or kind in seen:
            raise ValueError("Invalid installation kind.")
        seen.add(kind)
        install = checks.get(kind + "_install")
        if install is None or install["status"] != row["status"]:
            raise ValueError("Installation check and summary disagree.")
        if row["status"] != "pass":
            continue
        artifact = row["artifact"]
        name = artifact["path"]
        suffix = ".whl" if kind == "wheel" else ".tar.gz"
        parts = _member_parts(name)
        if (
            len(parts) != 2 or parts[0] != "artifacts" or not parts[1].endswith(suffix)
            or artifact["kind"] != kind or install.get("artifact") != artifact
            or install.get("log") != row.get("evidence_log")
        ):
            raise ValueError("Installed distribution is not tied to its build artifact.")
        evidence.require_digest(name, artifact["sha256"])
        if type(artifact["size"]) is not int or evidence.members[name].size != artifact["size"]:
            raise ValueError("Installed artifact size does not match.")
        _verify_install_operand(report, kind, checks, artifact, parts)
        results[kind] = artifact["sha256"]
    for kind in ("wheel", "sdist"):
        if checks.get(kind + "_install", {}).get("status") == "pass" and kind not in results:
            raise ValueError("Passing install lacks a distribution record.")
    return results


def _verify_install_operand(
    report: dict[str, Any], kind: str, checks: dict[str, dict[str, Any]],
    artifact: dict[str, Any], parts: tuple[str, ...],
) -> None:
    path_type = PureWindowsPath if report["platform"].startswith("Windows") else PurePosixPath
    base = path_type(report["evidence_directory"])
    if not base.is_absolute():
        raise ValueError("Invalid original evidence location.")
    expected = base.joinpath(*parts)
    command = checks[kind + "_install"]["command"]
    if (
        type(command) is not list or len(command) < 6
        or command[1:4] != ["-I", "-m", "pip"]
        or (command[4] != "install" and command[4:6] != ["--disable-pip-version-check", "install"])
        or path_type(command[-1].removesuffix("[dev]")).as_posix() != expected.as_posix()
    ):
        raise ValueError("Install process operand does not match its recorded artifact.")
    for name, check in checks.items():
        if name.startswith(kind + "_") and "artifact" in check and check["artifact"] != artifact:
            raise ValueError("Package check refers to a different artifact.")
    origin = checks.get(kind + "_origin_sdk", {})
    if origin.get("status") == "pass":
        probe = origin["command"]
        if (
            type(probe) is not list or len(probe) != 4 or probe[1:3] != ["-I", "-c"]
            or repr(expected.as_uri()) not in probe[3] or repr(artifact["sha256"]) not in probe[3]
            or "direct_url.json" not in probe[3]
        ):
            raise ValueError("Installed origin process lacks the exact archive pins.")


def _bound_licenses(
    report: dict[str, Any], evidence: _Evidence, installed: dict[str, str]
) -> dict[str, dict[str, Any]]:
    checks = {row["id"]: row for row in report["checks"]}
    result: dict[str, dict[str, Any]] = {}
    for kind in ("wheel", "sdist"):
        row = checks.get(kind + "_license_inventory")
        if row is None or (row["status"] in ("fail", "blocked", "not_run") and "inventory" not in row):
            continue
        info = row["inventory"]
        name = f"{kind}-license-inventory.json"
        origin = kind + "_origin_sdk"
        install = checks.get(kind + "_install", {})
        if (
            kind not in installed or checks.get(origin, {}).get("status") != "pass"
            or info["path"] != name or info["installed_origin_check"] != origin
            or row.get("artifact") != install.get("artifact")
            or info["scope"] != "installed_runtime_dependency_metadata"
            or info["license_review"] != "pending" or info["publication_authorized"] is not False
        ):
            raise ValueError("License inventory is not tied to the installed package.")
        evidence.require_digest(name, info["sha256"])
        if type(info["size"]) is not int or evidence.members[name].size != info["size"]:
            raise ValueError("License inventory size does not match.")
        content = read_json(evidence.check(name, retain=True))
        items = content["review_items"]
        if (
            type(content["schema_version"]) is not int or content["schema_version"] != 1
            or content["root"] != "agentsync-local"
            or content["scope"] != info["scope"] or content["license_review"] != "pending"
            or content["publication_authorized"] is not False
            or content["distributions"]["agentsync-local"]["version"] != report["version"]
            or type(items) is not list or type(info["review_item_count"]) is not int
            or len(items) != info["review_item_count"]
            or row["status"] != ("unverified" if items else "pass")
            or row["exit_code"] != (1 if items else 0)
        ):
            raise ValueError("License inventory and its check record disagree.")
        result[kind] = {"sha256": info["sha256"], "review_item_count": len(items), "review": "pending"}
    return result


def _offline_resolution(report: dict[str, Any], evidence: _Evidence) -> dict[str, Any] | None:
    scope = report.get("package_resolution")
    if scope is None:
        return None
    if type(scope) is not dict or scope.get("mode") != "offline_wheelhouse":
        raise ValueError("Unknown package resolution policy.")
    checks = {row["id"]: row for row in report["checks"]}
    member = scope.get("wheelhouse_manifest")
    if member is None:
        if checks.get("offline_wheelhouse", {}).get("status") != "fail":
            raise ValueError("Missing offline package manifest.")
        return {"state": "preflight_failed"}
    if member != "offline-wheelhouse.json":
        raise ValueError("Unexpected offline package manifest name.")
    inputs = read_json(evidence.check(member, retain=True))
    if type(inputs) is not list or not 1 <= len(inputs) <= 4096:
        raise ValueError("Invalid offline package manifest.")
    names = set()
    for row in inputs:
        if type(row) is not dict or set(row) != {"filename", "sha256", "size"}:
            raise ValueError("Invalid offline package record.")
        name = row["filename"]
        if (
            len(_member_parts(name)) != 1 or not name.endswith(".whl") or name.casefold() in names
            or type(row["size"]) is not int or row["size"] <= 0
            or type(row["sha256"]) is not str or not _SHA256.fullmatch(row["sha256"])
        ):
            raise ValueError("Invalid or repeated offline package record.")
        names.add(name.casefold())
    build = checks.get("build", {})
    if build.get("status") == "pass" and (
        "--no-isolation" not in build["command"]
        or any(checks.get(name, {}).get("status") != "pass" for name in ("offline_build_venv", "offline_build_tools"))
    ):
        raise ValueError("Offline build is missing the preloaded toolchain checks.")
    ids = {
        "offline_build_tools", "wheel_offline_dependencies", "sdist_offline_dependencies",
        "wheel_install", "sdist_install",
    }
    for check_id in ids:
        row = checks.get(check_id, {})
        command = row.get("command")
        if command is None:
            continue
        if "--no-index" not in command or command.count("--find-links") != 1:
            raise ValueError("Package command does not record offline dependency resolution.")
        position = command.index("--find-links") + 1
        if position >= len(command):
            raise ValueError("Missing offline wheel directory operand.")
        links = urlsplit(command[position])
        if links.scheme != "file" or links.netloc or not links.path.startswith("/"):
            raise ValueError("Offline package links must identify a local directory.")
        required = {"--no-deps"} if check_id.endswith("_install") else {"--only-binary=:all:"}
        if check_id == "sdist_install":
            required.add("--no-build-isolation")
        if not required <= set(command):
            raise ValueError("Offline package command is missing its install controls.")
    return {
        "state": "manifest_and_commands_checked",
        "manifest_sha256": evidence.members[member].sha256,
        "recorded_wheels": len(inputs),
        "staged_wheel_bytes_verified": False,
    }


def _snapshot_entries(rows: Any) -> int:
    if type(rows) is not list or not 1 <= len(rows) <= 20000:
        raise ValueError("Missing or oversized frozen source snapshot.")
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "sha256", "size"}:
            raise ValueError("Invalid frozen source entry.")
        name, digest, size = row["path"], row["sha256"], row["size"]
        _member_parts(name)
        if (
            name in seen or type(digest) is not str or not _SHA256.fullmatch(digest)
            or type(size) is not int or size < 0
        ):
            raise ValueError("Invalid or repeated frozen source entry.")
        seen.add(name)
    return len(seen)


def _verify_process(evidence: _Evidence, row: dict[str, Any], log: str) -> None:
    process_name = PurePosixPath(log).with_suffix(".process.json").as_posix()
    attempt = read_json(evidence.check(process_name, retain=True))
    if (
        type(attempt) is not dict or attempt.get("schema") != "agentsync.local-process-attempt.v1"
        or attempt.get("phase") != "finished" or attempt.get("check_id") != row["id"]
        or attempt.get("formal_acceptance") is not False or attempt.get("junit_validated") is not False
        or attempt.get("outcome") not in ("exited", "timed_out", "runner_error")
    ):
        raise ValueError("Process receipt is incomplete or belongs to another check.")
    original = attempt.get("result")
    request = attempt.get("request")
    if (
        type(original) is not dict or type(request) is not dict
        or any(original.get(field) != row.get(field) for field in _PROCESS_FIELDS)
        or any(request.get(field) != row.get(field) for field in ("command", "cwd", "started_at"))
        or request.get("timeout_seconds") != row.get("timeout_seconds", 900)
        or (attempt["outcome"] == "exited") != (type(row.get("exit_code")) is int)
        or (row["status"] == "pass" and original.get("status") != "pass")
    ):
        raise ValueError("Process receipt and check disagree.")


def verify_report_evidence(
    path: Path, report: dict[str, Any], *, source_repo: Path | None = None
) -> dict[str, Any]:
    evidence = _Evidence(path.parent, report.get("artifacts"))
    for name in evidence.members:
        evidence.check(name)
    evidence.require_digest("source-snapshot.json", report["source_snapshot_sha256"])
    evidence.require_digest("working-tree.patch", report["working_tree_patch_sha256"])
    source = read_json(evidence.check("source-snapshot.json", retain=True))
    snapshot = _snapshot_entries(source)
    register = report.get("requirements_register_sha256")
    if register is not None:
        evidence.require_digest("requirements.json", register)
        if not any(
            row["path"] == "docs/acceptance/requirements.json" and row["sha256"] == register
            for row in source
        ):
            raise ValueError("The saved requirements register differs from the source snapshot.")
    git_source = None
    if source_repo is not None:
        if __package__:
            from .acceptance_git_source import verify_git_source
        else:
            from acceptance_git_source import verify_git_source

        git_source = verify_git_source(source_repo, report["commit_sha"], report["tree_sha"], source)
    logs = set()
    cases: dict[str, str] = {}
    for row in report["checks"]:
        name, status = row["id"], row["status"]
        log = row.get("log")
        if log is not None:
            parts = _member_parts(log)
            if len(parts) != 2 or parts[0] != "logs" or log in logs:
                raise ValueError("Invalid or repeated process log reference.")
            logs.add(log)
            evidence.require_digest(log, row["log_sha256"])
            _verify_process(evidence, row, log)
        if status == "pass" and (
            log is None or row.get("provenance") != "local_process"
            or type(row.get("exit_code")) is not int or row["exit_code"] != 0
        ):
            raise ValueError("Passing check lacks a matching successful process observation.")
        junit_name = _SUITES.get(name)
        if junit_name is not None and "junit" in row:
            counts, case_hash = _junit(evidence.check(junit_name, retain=True))
            if counts != row["junit"]:
                raise ValueError("JUnit file and reported counts disagree.")
            cases[name] = case_hash
        if junit_name is not None and status == "pass" and name not in cases:
            raise ValueError("Passing suite lacks verified JUnit bytes.")
    installed = _bound_installations(report, evidence)
    if "candidate_input" in report:
        intake = report["candidate_input"]
        if (
            type(intake) is not dict or set(intake) != {"manifest_sha256", "artifact_sha256"}
            or type(intake["manifest_sha256"]) is not str
            or _SHA256.fullmatch(intake["manifest_sha256"]) is None
            or type(intake["artifact_sha256"]) is not dict
            or set(intake["artifact_sha256"]) != {"wheel", "sdist"}
        ):
            raise ValueError("Invalid copied candidate input.")
        pins = intake["artifact_sha256"]
        for kind, suffix in (("wheel", ".whl"), ("sdist", ".tar.gz")):
            names = [
                name for name in evidence.members
                if name.startswith("artifacts/") and name.count("/") == 1 and name.endswith(suffix)
            ]
            if len(names) != 1 or (kind in installed and installed[kind] != pins[kind]):
                raise ValueError("Installed archives differ from the copied candidate input.")
            evidence.require_digest(names[0], pins[kind])
    return {
        "manifest_members": len(evidence.members),
        "process_logs": len(logs),
        "source_snapshot_entries": snapshot,
        "git_source_audit": git_source,
        "installed_artifact_sha256": installed,
        "installed_license_inventories": _bound_licenses(report, evidence, installed),
        "offline_resolution": _offline_resolution(report, evidence),
        "junit_case_set_sha256": cases,
        "junit_case_sets_match": len(set(cases.values())) == 1 if len(cases) == 3 else None,
        "producer_authenticated": False,
    }

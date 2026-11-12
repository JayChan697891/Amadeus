"""Collect reproducible local evidence without declaring unverified release acceptance.

Run from any directory: python tools/release_acceptance.py --output F:/syuc/evidence
Add --run to execute checks, --package-install for a separate wheel environment,
and --sdist-install for a separate source-distribution build and installation.
Add --offline-wheelhouse to resolve packages from local wheels and --license-inventory
to capture runtime license metadata from each verified installed distribution.
No client credentials, model calls, workspace cleanup or Git mutations are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import uuid
import xml.etree.ElementTree as ET
import zipfile
from contextlib import nullcontext
from datetime import UTC, datetime
from email.parser import BytesHeaderParser
from itertools import islice
from pathlib import Path
from typing import NamedTuple

STATUSES = {"pass", "fail", "not_run", "restricted", "unverified"}
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_WHEELHOUSE_WHEELS = 512
MAX_WHEELHOUSE_BYTES = 4 * 1024**3
PYTEST_CHECKS = frozenset({"pytest", "wheel_pytest", "sdist_pytest"})
REDACTED = "[REDACTED]"
_CREDENTIAL_VALUE = re.compile(
    r"""(?P<prefix>(?<![\w])(?P<keyquote>['"]?)(?:session_token|admin_token|lease_token|access_token|refresh_token|api_key|openai_api_key|anthropic_api_key|agentsync_http_token|password|authorization)(?P=keyquote)\s*[:=]\s*)(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|[^\s,;}\]\)]+)""",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(\bBearer[ \t]+)[A-Za-z0-9._~+/-]+=*")
_API_KEY = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})\b")
RELEASE_BLOCKERS = {
    "remaining_milestones": "M4-05 approved application and M5-M9 implementation and acceptance remain incomplete.",
    "real_codex_adapter": "Actual Codex client adapter has not been independently verified.",
    "real_claude_adapter": "Actual Claude Code client adapter has not been independently verified.",
    "real_other_adapters": "Other planned clients, including Cursor, lack actual-client evidence.",
    "autonomous_relay": "Real autonomous dual-agent relay, independent review and conflict handling are unverified.",
    "cross_platform": "A local run does not establish the complete supported OS/Python matrix.",
    "m9_acceptance": "Full M9 release acceptance has not been performed.",
}


class OfflinePackages(NamedTuple):
    wheelhouse: Path
    backend: tuple[str, ...]
    frontend: str
    application: tuple[str, ...]


def _prepare_offline_packages(
    project: dict, wheelhouse: Path, scratch: Path, run: Path
) -> OfflinePackages:
    # Offline execution uses the same PEP 508 syntax as pip. Keep metadata-only
    # reports and the default online path usable without importing packaging.
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name, parse_wheel_filename

    if not wheelhouse.is_dir():
        raise ValueError("Offline wheelhouse must be a local directory")
    metadata = project["project"]
    if {"dependencies", "optional-dependencies"}.intersection(metadata.get("dynamic", ())):
        raise ValueError("Offline builds require static runtime and optional dependencies")
    backend = tuple(project["build-system"]["requires"])

    def local_requirement(value: str) -> Requirement:
        try:
            requirement = Requirement(value)
        except InvalidRequirement:
            raise ValueError(
                "Offline dependency metadata contains an invalid requirement"
            ) from None
        if requirement.url is not None:
            raise ValueError("Offline dependency metadata contains a direct URL requirement")
        return requirement

    for value in backend:
        local_requirement(value)

    def active_requirements(declarations: list[str], extras: tuple[str, ...]) -> list[Requirement]:
        active = []
        for value in declarations:
            requirement = local_requirement(value)
            if requirement.marker is None or any(
                requirement.marker.evaluate({"extra": extra}) for extra in extras
            ):
                requirement.marker = None  # Already evaluated for the selected artifact extras.
                active.append(requirement)
        return active

    runtime = active_requirements(metadata.get("dependencies", []), ("", "dev"))
    dev = active_requirements(metadata.get("optional-dependencies", {}).get("dev", []), ("dev",))
    frontends = [
        str(requirement) for requirement in dev if canonicalize_name(requirement.name) == "build"
    ]
    if len(frontends) != 1:
        raise ValueError("Offline source build requires one declared build frontend")

    # Use a private snapshot of validated wheels. A live find-links directory
    # could change after validation or expose other package/link formats.
    sources = sorted(islice(wheelhouse.glob("*.whl"), MAX_WHEELHOUSE_WHEELS + 1))
    if not sources:
        raise ValueError("Offline wheelhouse contains no wheels")
    if len(sources) > MAX_WHEELHOUSE_WHEELS:
        raise ValueError("Offline wheelhouse exceeds the wheel count limit")
    sizes = []
    for source in sources:
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Offline wheelhouse wheels must be regular local files")
        sizes.append(info.st_size)
    if sum(sizes) > MAX_WHEELHOUSE_BYTES:
        raise ValueError("Offline wheelhouse exceeds the total size limit")

    staged = scratch / "offline-wheels"
    staged.mkdir()
    inputs = []
    for source, size in zip(sources, sizes, strict=True):
        parse_wheel_filename(source.name)
        target = staged / source.name
        shutil.copyfile(source, target)
        if target.stat().st_size != size:
            raise ValueError("Offline wheelhouse wheel size changed during staging")
        with zipfile.ZipFile(target) as archive:
            members = [
                member
                for member in archive.infolist()
                if member.filename.count("/") == 1
                and member.filename.endswith(".dist-info/METADATA")
            ]
            if len(members) != 1 or members[0].file_size > MAX_LOG_BYTES:
                raise ValueError("Each offline wheel must contain one bounded METADATA member")
            headers = BytesHeaderParser().parsebytes(archive.read(members[0]))
            if headers.defects:
                raise ValueError("Offline wheel has malformed metadata headers")
            for value in headers.get_all("Requires-Dist", []):
                local_requirement(value)
        with target.open("rb") as stream:
            inputs.append(
                {
                    "filename": target.name,
                    "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                    "size": size,
                }
            )
    (run / "offline-wheelhouse.json").write_text(
        json.dumps(inputs, indent=2) + "\n", encoding="utf-8"
    )
    return OfflinePackages(staged, backend, frontends[0], tuple(map(str, (*runtime, *dev))))


def _offline_install(python: str, wheelhouse: Path, *args: str) -> list[str]:
    return [
        python,
        "-I",
        "-m",
        "pip",
        "--disable-pip-version-check",
        "install",
        "--no-index",
        "--find-links",
        wheelhouse.as_uri(),
        "--no-cache-dir",
        *args,
    ]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def redact_credentials(text: str) -> tuple[str, int]:
    """Best-effort bounded-pattern redaction, not a general secret-discovery claim."""
    text, bearer_count = _BEARER.subn(lambda match: match[1] + REDACTED, text)
    text, value_count = _CREDENTIAL_VALUE.subn(lambda match: match["prefix"] + REDACTED, text)
    text, key_count = _API_KEY.subn(REDACTED, text)
    return text, bearer_count + value_count + key_count


def persist_junit(source: Path, target: Path) -> int:
    """Persist parsed, redacted XML rather than raw failure tracebacks containing fixture auth."""
    if source.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("JUnit evidence exceeds the bounded processing limit")
    document = ET.parse(source)
    count = 0
    for node in document.iter():
        for attribute, value in list(node.attrib.items()):
            node.attrib[attribute], changes = redact_credentials(value)
            count += changes
        for field in ("text", "tail"):
            value = getattr(node, field)
            if value is not None:
                clean, changes = redact_credentials(value)
                setattr(node, field, clean)
                count += changes
    document.write(target, encoding="utf-8", xml_declaration=True)
    return count


def git_value(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (
        result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else None
    )


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    return {
        "tests": len(cases),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }


def source_snapshot(repo: Path) -> list[dict]:
    """Hash Git-visible source, including untracked code; never copy secret contents."""
    paths = git_value(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    result = []
    for name in sorted(set((paths or "").split("\0"))):
        path = repo / name
        # Git exclusions are honored; additionally omit likely credential file names.
        if (
            not name
            or path.is_symlink()
            or not path.is_file()
            or path.name.startswith(".env")
            or path.suffix.lower() in {".pem", ".key"}
            or path.name.lower() in {"auth.json", "credentials.json", "secrets.json"}
        ):
            continue
        result.append({"path": name, "sha256": sha256(path), "size": path.stat().st_size})
    return result


def requirement_results(manifest: dict | None, run: Path) -> list[dict]:
    """Attach component observations without promoting a requirement to accepted."""
    documents = {}
    for name in ("junit.xml", "wheel-junit.xml", "sdist-junit.xml"):
        path = run / name
        if path.is_file():
            try:
                documents[name] = list(ET.parse(path).getroot().iter("testcase"))
            except (OSError, ET.ParseError):
                continue
    rows = []
    for requirement in (manifest or {}).get("requirements", []):
        component = []
        for selector in requirement.get("existing_tests", []):
            parts = selector.split("::")
            module = parts[0].removesuffix(".py").replace("/", ".").replace("\\", ".")
            classname = ".".join([module, *parts[1:-1]]) if len(parts) > 2 else module
            observations = []
            for name, cases in documents.items():
                matched = []
                for case in cases:
                    actual_class = case.get("classname", "")
                    if len(parts) == 1:
                        match = actual_class == module or actual_class.startswith(module + ".")
                    else:
                        actual_name = case.get("name", "")
                        expected_name = parts[-1]
                        name_match = actual_name == expected_name or (
                            "[" not in expected_name and actual_name.startswith(expected_name + "[")
                        )
                        match = actual_class == classname and name_match
                    if match:
                        matched.append(case)
                counts = {
                    "tests": len(matched),
                    "failures": sum(c.find("failure") is not None for c in matched),
                    "errors": sum(c.find("error") is not None for c in matched),
                    "skipped": sum(c.find("skipped") is not None for c in matched),
                }
                counts["passed"] = (
                    counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
                )
                observations.append({"junit": name, "counts": counts})
            component.append({"selector": selector, "observations": observations})
        requirement_id = requirement["id"]
        rows.append(
            {
                "id": requirement_id,
                "milestone": requirement.get("milestone"),
                "title": requirement.get("title", ""),
                "coverage": requirement.get("coverage", "missing"),
                "execution_status": "not_run",
                "declared_execution_status": requirement.get("execution_status", "not_run"),
                "acceptance_evidence_status": "unverified"
                if requirement_id in {"M2-05", "M6-03", "M6-04", "M6-05", "M7-02"}
                else "not_run",
                "component_evidence": component,
                "component_evidence_scope": "Exact-selector local protocol/unit observations only; no whole-requirement or actual-client acceptance inferred.",
                "planned_evidence": requirement.get("evidence"),
                "release_gate": requirement.get("release_gate"),
            }
        )
    return rows


def scenario_results(manifest: dict | None, requirements: list[dict]) -> list[dict]:
    """Index original scenarios without reusing component observations as scenario evidence."""
    observed_requirements = {
        row["id"]
        for row in requirements
        if any(
            observed["counts"]["tests"] > 0
            for component in row["component_evidence"]
            for observed in component["observations"]
        )
    }
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "expected": row["expected"],
            "requirements": row["requirements"],
            "planned_evidence": row["evidence"],
            "execution_status": "not_run",
            "scenario_evidence": [],
            "requirements_with_component_observations": [
                identity for identity in row["requirements"] if identity in observed_requirements
            ],
        }
        for row in (manifest or {}).get("scenarios", [])
    ]


def _validate_pytest_timeout(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 7200:
        raise ValueError("pytest controller timeout must be an integer from 1 to 7200 seconds")


def _persist_process_attempt(path: Path, record: dict) -> None:
    """Atomically replace only this run's command-attempt sidecar."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".attempt-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def execute(
    check_id: str,
    command: list[str],
    repo: Path,
    run: Path,
    scratch: Path | None = None,
    *,
    pytest_timeout: int = 900,
    offline_wheelhouse: Path | None = None,
    capture_stdout: Path | None = None,
) -> dict:
    _validate_pytest_timeout(pytest_timeout)
    if pytest_timeout != 900 and check_id not in PYTEST_CHECKS:
        raise ValueError("Custom pytest controller timeout is only valid for full-suite checks")
    log = run / "logs" / f"{check_id}.log"
    started = datetime.now(UTC)
    attempt_path = log.with_suffix(".process.json")
    attempt = {
        "schema": "agentsync.local-process-attempt.v1",
        "scope": "Command attempt only; JUnit and final acceptance remain separate.",
        "phase": "started",
        "outcome": "unknown",
        "check_id": check_id,
        "formal_acceptance": False,
        "junit_validated": False,
        "request": {
            "command": [redact_credentials(argument)[0] for argument in command],
            "cwd": str(repo),
            "started_at": started.isoformat(),
            "timeout_seconds": pytest_timeout,
        },
    }
    _persist_process_attempt(attempt_path, attempt)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if check_id == "pytest":
        # Source tests launch CLI and process fixtures with the same interpreter.
        # Pin their imports to the frozen checkout too. Installed suites stay isolated.
        env["PYTHONPATH"] = str(repo.resolve() / "src")
    if check_id in {"pytest", "wheel_pytest", "sdist_pytest"}:
        # A user's pytest options can silently select a nonempty subset. These
        # runs attest the checked-in suite, with its declared plugin setup.
        for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DISABLE_PLUGIN_AUTOLOAD"):
            env.pop(name, None)
    if offline_wheelhouse is not None:
        env = {name: value for name, value in env.items() if not name.upper().startswith("PIP_")}
        env.update(
            PIP_CONFIG_FILE=os.devnull,
            PIP_DISABLE_PIP_VERSION_CHECK="1",
            PIP_NO_INDEX="1",
            PIP_FIND_LINKS=offline_wheelhouse.as_uri(),
            PIP_NO_CACHE_DIR="1",
        )
    elif check_id == "build" or check_id.startswith(("sdist_", "wheel_")):
        # Preserve network/proxy settings, but don't inherit pip options that can
        # bypass build isolation or redirect writes outside this fresh venv.
        for name in (
            "PIP_NO_BUILD_ISOLATION",
            "PIP_NO_USE_PEP517",
            "PIP_USE_PEP517",
            "PIP_TARGET",
            "PIP_PREFIX",
            "PIP_ROOT",
            "PIP_USER",
            "PIP_NO_DEPS",
            "PIP_PYTHON",
            "PIP_LOG",
            "PIP_REPORT",
            "PIP_SRC",
            "PIP_BUILD_TRACKER",
        ):
            env.pop(name, None)
        env["PIP_CONFIG_FILE"] = os.devnull
        env["PIP_CACHE_DIR"] = str((scratch if scratch is not None else run / "tmp") / "pip-cache")
    temporary = scratch if scratch is not None else run / "tmp"
    if scratch is None:
        temporary.mkdir(exist_ok=True)
    env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
    exit_code = None
    outcome = "unknown"
    error_type = None
    # Raw process output exists only in a self-deleting scratch file. It is never
    # placed in the durable/uploadable log directory, even for failed commands.
    with (
        tempfile.TemporaryFile(mode="w+b", dir=temporary) as stream,
        capture_stdout.open("wb") if capture_stdout is not None else nullcontext(stream) as stdout,
    ):
        try:
            result = subprocess.run(
                command,
                cwd=repo,
                env=env,
                stdout=stdout,
                stderr=subprocess.STDOUT if capture_stdout is None else stream,
                timeout=pytest_timeout,
                check=False,
            )
            exit_code = result.returncode
            outcome = "exited"
        except (OSError, subprocess.TimeoutExpired) as exc:
            outcome = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "runner_error"
            error_type = type(exc).__name__
            stream.write(f"\nRunner error: {type(exc).__name__}: {exc}\n".encode())
        stream.seek(0)
        raw = stream.read(MAX_LOG_BYTES + 1)
    truncated = len(raw) > MAX_LOG_BYTES
    clean, redactions = redact_credentials(raw[:MAX_LOG_BYTES].decode("utf-8", errors="replace"))
    if truncated:
        clean += "\n[OUTPUT TRUNCATED: evidence processing limit reached]\n"
    log.write_text(clean, encoding="utf-8")
    result_metadata = {
        "id": check_id,
        "status": "pass" if exit_code == 0 else "fail",
        "command": [redact_credentials(argument)[0] for argument in command],
        "cwd": str(repo),
        "exit_code": exit_code,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "log": log.relative_to(run).as_posix(),
        "log_sha256": sha256(log),
        "credential_redactions": redactions,
        "log_truncated": truncated,
        "provenance": "local_process",
    }
    if pytest_timeout != 900:
        result_metadata["timeout_seconds"] = pytest_timeout
    attempt.update(phase="finished", outcome=outcome, error_type=error_type, result=result_metadata)
    _persist_process_attempt(attempt_path, attempt)
    return result_metadata


def _execute_check(
    check_id: str, command: list[str], repo: Path, run: Path, scratch: Path, pytest_timeout: int
) -> dict:
    # Preserve the existing execute seam for default settings and ordinary checks.
    if check_id in PYTEST_CHECKS and pytest_timeout != 900:
        return execute(check_id, command, repo, run, scratch, pytest_timeout=pytest_timeout)
    return execute(check_id, command, repo, run, scratch)


def _offline_build_command(
    repo: Path,
    run: Path,
    scratch: Path,
    packages: OfflinePackages,
    checks: list[dict],
    *,
    artifact_output: Path | None = None,
) -> list[str] | None:
    environment = scratch / "offline-build"
    created = execute(
        "offline_build_venv", [sys.executable, "-m", "venv", str(environment)], repo, run, scratch
    )
    checks.append(created)
    if created["status"] != "pass":
        return None
    python = str(environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    tools = execute(
        "offline_build_tools",
        _offline_install(
            python, packages.wheelhouse, "--only-binary=:all:", packages.frontend, *packages.backend
        ),
        run,
        run,
        scratch,
        offline_wheelhouse=packages.wheelhouse,
    )
    checks.append(tools)
    if tools["status"] != "pass":
        return None
    return [
        python,
        "-I",
        "-m",
        "build",
        "--no-isolation",
        "--outdir",
        str(artifact_output if artifact_output is not None else run / "artifacts"),
    ]


_CONSOLE_PROBE = r"""
import json, os, subprocess, sys
from pathlib import Path

def check():
    scripts = Path(sys.executable).parent
    scratch = Path(sys.argv[1])
    suffix = ".exe" if os.name == "nt" else ""
    env = {name: value for name, value in os.environ.items()
           if not name.upper().startswith(("AGENTSYNC_", "PYTHON"))}
    env.update(PYTHONSAFEPATH="1", PYTHONNOUSERSITE="1")
    legacy = subprocess.run([str(scripts / ("agentsync" + suffix)), "--help"], cwd=scratch,
                            env=env, timeout=30, capture_output=True, check=False)
    if legacy.returncode != 0 or not legacy.stdout.startswith(b"usage: agentsync "):
        return False
    result = subprocess.run([str(scripts / ("amadeus" + suffix)), "demo", "--data-dir", str(scratch / "data")],
                            cwd=scratch, env=env, timeout=30, capture_output=True, check=False)
    if result.returncode != 0 or len(result.stdout) > 16384:
        return False
    document = json.loads(result.stdout)
    data = document.get("data", {})
    return (document.get("ok") is True and data.get("status") == "completed"
            and data.get("agents") == 2 and data.get("duplicate_claim_rejected") is True
            and data.get("persistence_verified") is True
            and data.get("scope") == "local mock workflow; no desktop host compatibility verified")

try:
    passed = check()
except (AttributeError, OSError, ValueError, subprocess.SubprocessError):
    passed = False
print("Installed console scripts and disposable Mock demo: " + ("pass" if passed else "failed"))
raise SystemExit(0 if passed else 1)
"""


def _installed_console_smoke(
    kind: str, python: str, run: Path, scratch: Path, artifact: dict
) -> dict:
    directory = scratch / f"{kind}-console-probe"
    directory.mkdir()
    result = execute(
        f"{kind}_console_smoke",
        [python, "-I", "-c", _CONSOLE_PROBE, str(directory)],
        directory,
        run,
        scratch,
    )
    result["artifact"] = artifact.copy()
    return result


def _installed_license_inventory(
    kind: str,
    python: str,
    repo: Path,
    run: Path,
    scratch: Path,
    version: str,
    artifact: dict,
    origin: dict,
) -> dict:
    check_id = kind + "_license_inventory"
    stdout = scratch / f"{kind}-license-inventory.json"
    result = execute(
        check_id,
        [
            python,
            "-I",
            str(repo / "tools" / "license_inventory.py"),
            "--distribution",
            "agentsync-local",
        ],
        run,
        run,
        scratch,
        capture_stdout=stdout,
    )
    result["artifact"] = artifact.copy()
    archive = run / artifact["path"]
    try:
        if result.get("exit_code") not in {0, 1}:
            raise ValueError("Inventory process did not emit a completed report")
        if not archive.is_file() or sha256(archive) != artifact["sha256"]:
            raise ValueError("Installed archive changed before license evidence was recorded")
        with stdout.open("rb") as stream:
            raw = stream.read(MAX_LOG_BYTES + 1)
        if len(raw) > MAX_LOG_BYTES:
            raise ValueError("License inventory exceeds the bounded evidence limit")
        decoded = raw.decode("utf-8")
        if redact_credentials(decoded)[1]:
            raise ValueError("Raw license inventory contains a recognized credential pattern")
        inventory = json.loads(decoded)
        if (
            not isinstance(inventory, dict)
            or type(inventory.get("schema_version")) is not int
            or inventory["schema_version"] != 1
            or inventory.get("root") != "agentsync-local"
            or inventory.get("scope") != "installed_runtime_dependency_metadata"
            or inventory.get("license_review") != "pending"
            or inventory.get("publication_authorized") is not False
            or not isinstance(inventory.get("distributions"), dict)
            or not isinstance(inventory["distributions"].get("agentsync-local"), dict)
            or inventory["distributions"]["agentsync-local"].get("version") != version
            or not isinstance(inventory.get("edges"), list)
            or not isinstance(inventory.get("review_items"), list)
            or bool(inventory["review_items"]) != (result["exit_code"] == 1)
        ):
            raise ValueError(
                "License inventory does not match the installed distribution or expected schema"
            )
        json.dumps(inventory, allow_nan=False)
        target = run / stdout.name
        target.write_bytes(raw)
    except (OSError, ValueError, RecursionError) as exc:
        result.update(status="fail", reason=redact_credentials(str(exc))[0])
    else:
        result.update(
            status="unverified" if inventory["review_items"] else "pass",
            inventory={
                "path": target.relative_to(run).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                "scope": inventory["scope"],
                "review_item_count": len(inventory["review_items"]),
                "license_review": "pending",
                "publication_authorized": False,
                "installed_origin_check": origin["id"],
            },
        )
    return result


def release_gate(checks: list[dict], run: Path) -> dict:
    """Fail closed; local checks and mock clients can never prove formal release readiness."""
    invalid = []
    for check in checks:
        if check.get("status") != "pass":
            invalid.append(check.get("id", "unknown"))
            continue
        relative = Path(check.get("log", ""))
        target = (run / relative).resolve()
        if (
            relative.is_absolute()
            or not target.is_relative_to(run.resolve())
            or not target.is_file()
            or check.get("provenance") != "local_process"
            or sha256(target) != check.get("log_sha256")
            or check.get("exit_code") != 0
        ):
            invalid.append(check.get("id", "unknown"))
    return {
        "status": "blocked",
        "formal_acceptance": False,
        "local_checks_passed": bool(checks) and not invalid,
        "invalid_or_incomplete_checks": invalid,
        "blockers": RELEASE_BLOCKERS,
        "policy": "No mock, protocol-only, missing, restricted or unverified evidence can count as actual-client acceptance.",
    }


def check_plan(python: str, run: Path, scratch: Path) -> list[tuple[str, list[str]]]:
    return [
        (
            "pytest",
            [
                python,
                "-m",
                "pytest",
                "--junitxml",
                str(scratch / "junit.xml"),
                "--basetemp",
                str(scratch / "pytest"),
            ],
        ),
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("format", [python, "-m", "ruff", "format", "--check", "."]),
        ("mypy", [python, "-m", "mypy"]),
        ("build", [python, "-m", "build", "--outdir", str(run / "artifacts")]),
        ("pip_check", [python, "-m", "pip", "check"]),
    ]


def sdist_checks(
    repo: Path,
    run: Path,
    scratch: Path,
    version: str,
    build_passed: bool,
    *,
    pytest_timeout: int = 900,
    offline_packages: OfflinePackages | None = None,
    license_inventory: bool = False,
) -> list[dict]:
    """Install only the selected sdist in a fresh environment; never fall back to source."""
    _validate_pytest_timeout(pytest_timeout)
    archives = sorted((run / "artifacts").glob("*.tar.gz"))
    if not build_passed or len(archives) != 1:
        return [
            {
                "id": "sdist_install",
                "status": "fail",
                "reason": "Requested sdist install requires a successful build with exactly one tar.gz archive",
            }
        ]
    archive = archives[0]
    artifact = {
        "path": archive.relative_to(run).as_posix(),
        "sha256": sha256(archive),
        "size": archive.stat().st_size,
        "kind": "sdist",
    }
    environment = Path(tempfile.mkdtemp(prefix="sdist-", dir=scratch))
    checks = []

    def invoke(name: str, command: list[str], *, offline: bool = False) -> dict:
        check_id = "sdist_" + name
        if offline and offline_packages is not None:
            result = execute(
                check_id, command, run, run, scratch, offline_wheelhouse=offline_packages.wheelhouse
            )
        else:
            result = _execute_check(check_id, command, run, run, scratch, pytest_timeout)
        result["artifact"] = artifact.copy()
        checks.append(result)
        return result

    def skipped(names: list[str], reason: str) -> None:
        checks.extend(
            {
                "id": "sdist_" + name,
                "status": "not_run",
                "reason": reason,
                "artifact": artifact.copy(),
            }
            for name in names
        )

    created = invoke("venv", [sys.executable, "-m", "venv", str(environment)])
    if created["status"] != "pass":
        skipped(
            ["install", "pip_check", "cli", "origin_sdk", "pytest"],
            "Fresh sdist environment creation failed",
        )
        return checks
    python = str(environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    if offline_packages is not None:
        wheelhouse = offline_packages.wheelhouse
        dependencies = invoke(
            "offline_dependencies",
            _offline_install(
                python,
                wheelhouse,
                "--only-binary=:all:",
                *offline_packages.backend,
                *offline_packages.application,
            ),
            offline=True,
        )
        if dependencies["status"] != "pass":
            skipped(
                ["install", "pip_check", "cli", "origin_sdk", "pytest"],
                "Offline sdist dependency preparation failed",
            )
            return checks
        install_command = _offline_install(
            python,
            wheelhouse,
            "--no-build-isolation",
            "--no-deps",
            "--force-reinstall",
            "--",
            str(archive),
        )
    else:
        install_command = [
            python,
            "-I",
            "-m",
            "pip",
            "install",
            "--use-pep517",
            "--no-cache-dir",
            str(archive) + "[dev]",
        ]
    installed = invoke("install", install_command, offline=offline_packages is not None)
    if installed["status"] != "pass":
        skipped(
            ["pip_check", "cli", "origin_sdk", "pytest"],
            "Sdist installation failed; no fallback attempted",
        )
        return checks
    invoke("pip_check", [python, "-I", "-m", "pip", "check"], offline=True)
    invoke("cli", [python, "-I", "-m", "agentsync", "--help"])
    probe = (
        "import agentsync, importlib.metadata, json, pathlib, tempfile; "
        "from agentsync.sdk import AgentSyncClient; "
        "origin = pathlib.Path(agentsync.__file__).resolve(); "
        f"assert origin.is_relative_to(pathlib.Path({str(environment)!r}).resolve()); "
        f"assert not origin.is_relative_to(pathlib.Path({str(repo)!r}).resolve()); "
        f"assert importlib.metadata.version('agentsync-local') == {version!r}; "
        "direct = json.loads(importlib.metadata.distribution('agentsync-local').read_text('direct_url.json')); "
        f"assert direct['url'] == {archive.resolve().as_uri()!r}; "
        f"assert (direct['archive_info'].get('hashes', {{}}).get('sha256') or direct['archive_info'].get('hash', '').removeprefix('sha256=')) == {artifact['sha256']!r}; "
        "assert not direct.get('dir_info', {}).get('editable', False); "
        "print('installed sdist origin:', origin); "
        "temporary = tempfile.TemporaryDirectory(); root = pathlib.Path(temporary.name) / 'project'; root.mkdir(); "
        "client = AgentSyncClient(pathlib.Path(temporary.name) / 'data'); "
        "result = client.call('create_project', name='isolated sdist smoke', root_path=str(root)); "
        "assert result['ok'], result; print('sdist SDK smoke: pass'); temporary.cleanup()"
    )
    origin = invoke("origin_sdk", [python, "-I", "-c", probe])
    if origin["status"] != "pass":
        skipped(
            ["pytest"],
            "Installed sdist origin/version/SDK check failed; test results would be untrusted",
        )
    else:
        checks.append(_installed_console_smoke("sdist", python, run, scratch, artifact))
        if license_inventory:
            checks.append(
                _installed_license_inventory(
                    "sdist", python, repo, run, scratch, version, artifact, origin
                )
            )
        tested = invoke(
            "pytest",
            [
                python,
                "-I",
                "-m",
                "pytest",
                str(repo / "tests"),
                "--junitxml",
                str(scratch / "sdist-junit.xml"),
                "--basetemp",
                str(scratch / "sdist-pytest"),
            ],
        )
        try:
            tested["junit_credential_redactions"] = persist_junit(
                scratch / "sdist-junit.xml", run / "sdist-junit.xml"
            )
            tested["junit"] = junit_counts(run / "sdist-junit.xml")
            if (
                not tested["junit"]["tests"]
                or tested["junit"]["failures"]
                or tested["junit"]["errors"]
            ):
                tested["status"] = "fail"
        except (OSError, ValueError, ET.ParseError):
            tested["status"] = "fail"
            tested["error"] = "Installed-sdist JUnit missing or invalid"
    if not archive.is_file() or sha256(archive) != artifact["sha256"]:
        checks.append(
            {
                "id": "sdist_artifact_stability",
                "status": "fail",
                "reason": "Sdist archive changed during installation or testing",
                "artifact": artifact,
            }
        )
    return checks


def _stage_candidate(
    repo: Path,
    run: Path,
    version: str,
    candidate: tuple[Path, Path, str],
) -> dict:
    if __package__:
        from .acceptance_evidence import _member_parts, _physical
        from .release_manifest import verify_manifest
    else:
        from acceptance_evidence import _member_parts, _physical
        from release_manifest import verify_manifest

    manifest_path, evidence_root, checksum = candidate
    if any(path.resolve(strict=True).drive.startswith("\\\\") for path in candidate[:2]):
        raise ValueError("Candidate installation requires local evidence files.")
    verified = verify_manifest(
        manifest_path, evidence_root, manifest_sha256=checksum, source_repo=repo
    )
    frozen = {
        "version": version,
        "commit_sha": git_value(repo, "rev-parse", "HEAD"),
        "tree_sha": git_value(repo, "rev-parse", "HEAD^{tree}"),
        "source_snapshot_sha256": sha256(run / "source-snapshot.json"),
    }
    if verified["frozen"] != frozen or git_value(repo, "status", "--porcelain") != "":
        raise ValueError("Candidate archives require their matching clean frozen source.")

    checked_root = evidence_root.resolve(strict=True)
    pins = {}
    with tempfile.TemporaryDirectory(prefix=".candidate-", dir=run) as temporary:
        archives = Path(temporary) / "artifacts"
        archives.mkdir()
        for artifact in verified["checked_artifacts"]:
            source, info = _physical(checked_root, _member_parts(artifact["path"]))
            dest = archives / artifact["filename"]
            remaining = artifact["size"]
            digest = hashlib.sha256()
            if info.st_size != remaining:
                raise ValueError("Candidate archive changed before staging.")
            with source.open("rb") as incoming, dest.open("xb") as staged:
                while remaining:
                    chunk = incoming.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("Candidate archive ended during staging.")
                    digest.update(chunk)
                    staged.write(chunk)
                    remaining -= len(chunk)
                if incoming.read(1) or digest.hexdigest() != artifact["sha256"]:
                    raise ValueError("Candidate archive changed during staging.")
            pins[artifact["kind"]] = artifact["sha256"]
        archives.rename(run / "artifacts")
    return {"manifest_sha256": verified["manifest_sha256"], "artifact_sha256": pins}


def collect(
    repo: Path,
    output: Path,
    *,
    run_checks: bool,
    package_install: bool,
    sdist_install: bool = False,
    scratch_root: Path | None = None,
    pytest_timeout: int = 900,
    offline_wheelhouse: Path | None = None,
    license_inventory: bool = False,
    candidate: tuple[Path, Path, str] | None = None,
) -> Path:
    _validate_pytest_timeout(pytest_timeout)
    if sdist_install and not run_checks:
        raise ValueError("--sdist-install requires --run")
    if offline_wheelhouse is not None and not run_checks:
        raise ValueError("--offline-wheelhouse requires --run")
    if license_inventory and not (run_checks and (package_install or sdist_install)):
        raise ValueError("--license-inventory requires --run and a requested distribution install")
    if candidate is not None and not (
        run_checks and package_install and sdist_install and offline_wheelhouse is not None
    ):
        raise ValueError(
            "Candidate installs require --run, both installs and --offline-wheelhouse."
        )
    if offline_wheelhouse is not None and any(
        path is not None and path.drive.startswith("\\\\") for path in (repo, output, scratch_root)
    ):
        raise ValueError("Offline mode requires local source, output and scratch paths")
    output = output.resolve()
    if output.is_relative_to(repo.resolve()):
        raise ValueError("Evidence output must be outside the source repository")
    temporary_parent = output if scratch_root is None else scratch_root.resolve()
    if scratch_root is not None and temporary_parent.is_relative_to(repo.resolve()):
        raise ValueError("Scratch root must be outside the source repository")
    if offline_wheelhouse is not None and any(
        path.drive.startswith("\\\\") for path in (repo.resolve(), output, temporary_parent)
    ):
        raise ValueError("Offline mode requires local source, output and scratch paths")
    output.mkdir(parents=True, exist_ok=True)
    if scratch_root is not None:
        temporary_parent.mkdir(parents=True, exist_ok=True)
    # Test DBs/auth files and wheel environments are never durable report artifacts.
    # TemporaryDirectory cleans only this freshly created directory, even on failure.
    options = {}
    if offline_wheelhouse is not None:
        options["offline_wheelhouse"] = offline_wheelhouse
    if license_inventory:
        options["license_inventory"] = True
    if candidate is not None:
        options["candidate"] = candidate
    with tempfile.TemporaryDirectory(prefix=".scratch-", dir=temporary_parent) as temporary:
        return _collect(
            repo.resolve(),
            output,
            Path(temporary),
            run_checks,
            package_install,
            sdist_install,
            pytest_timeout=pytest_timeout,
            **options,
        )


def _collect(
    repo: Path,
    output: Path,
    scratch: Path,
    run_checks: bool,
    package_install: bool,
    sdist_install: bool = False,
    *,
    pytest_timeout: int = 900,
    offline_wheelhouse: Path | None = None,
    license_inventory: bool = False,
    candidate: tuple[Path, Path, str] | None = None,
) -> Path:
    run = output / (
        "release-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    )
    run.mkdir()
    (run / "logs").mkdir()
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    diff = git_value(repo, "diff", "HEAD", "--binary")
    original_patch_sha = hashlib.sha256((diff or "").encode("utf-8")).hexdigest()
    safe_patch, patch_redactions = redact_credentials(diff or "")
    (run / "working-tree.patch").write_text(safe_patch, encoding="utf-8")
    source = source_snapshot(repo)
    (run / "source-snapshot.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
    checks = []
    candidate_input = None
    candidate_rejected = False
    if candidate is not None:
        try:
            candidate_input = _stage_candidate(repo, run, project["project"]["version"], candidate)
        except (
            AttributeError,
            ImportError,
            IndexError,
            KeyError,
            OSError,
            RecursionError,
            TypeError,
            ValueError,
        ):
            candidate_rejected = True
            checks.append(
                {
                    "id": "candidate_preflight",
                    "status": "fail",
                    "reason": "Could not verify and stage the exact candidate from its original build and frozen source",
                }
            )
    if candidate_input is None:
        (run / "artifacts").mkdir(exist_ok=True)
    plan = check_plan(sys.executable, run, scratch)
    offline_packages = None
    if candidate_rejected:
        checks.append(
            {
                "id": "offline_wheelhouse",
                "status": "not_run",
                "reason": "Candidate preflight failed",
            }
        )
    elif offline_wheelhouse is not None:
        try:
            if offline_wheelhouse.drive.startswith("\\\\"):
                raise ValueError("Offline wheelhouse must use a local filesystem path")
            wheelhouse = offline_wheelhouse.resolve()
            if wheelhouse.drive.startswith("\\\\"):
                raise ValueError("Offline wheelhouse must use a local filesystem path")
            offline_packages = _prepare_offline_packages(project, wheelhouse, scratch, run)
        except (
            ImportError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            zipfile.BadZipFile,
        ) as exc:
            checks.append(
                {
                    "id": "offline_wheelhouse",
                    "status": "fail",
                    "reason": redact_credentials(str(exc))[0],
                }
            )
    for check_id, command in plan:
        if candidate_rejected:
            item = {
                "id": check_id,
                "command": command,
                "status": "not_run",
                "reason": "Candidate preflight failed",
            }
        elif check_id == "build" and offline_wheelhouse is not None:
            build = (
                None
                if offline_packages is None
                else _offline_build_command(
                    repo,
                    run,
                    scratch,
                    offline_packages,
                    checks,
                    **({"artifact_output": scratch / "local-rebuild"} if candidate_input else {}),
                )
            )
            if build is None or offline_packages is None:
                item = {
                    "id": "build",
                    "status": "not_run",
                    "reason": "Offline build prerequisites failed",
                }
            else:
                item = execute(
                    "build",
                    build,
                    repo,
                    run,
                    scratch,
                    offline_wheelhouse=offline_packages.wheelhouse,
                )
        elif check_id == "pip_check" and offline_wheelhouse is not None:
            item = execute(
                check_id, command, repo, run, scratch, offline_wheelhouse=scratch / "offline-wheels"
            )
        elif run_checks:
            item = _execute_check(check_id, command, repo, run, scratch, pytest_timeout)
            if check_id == "pytest" and (scratch / "junit.xml").exists():
                try:
                    item["junit_credential_redactions"] = persist_junit(
                        scratch / "junit.xml", run / "junit.xml"
                    )
                    item["junit"] = junit_counts(run / "junit.xml")
                    if (
                        not item["junit"]["tests"]
                        or item["junit"]["errors"]
                        or item["junit"]["failures"]
                    ):
                        item["status"] = "fail"
                except (OSError, ValueError, ET.ParseError):
                    item["status"] = "fail"
                    item["error"] = "Invalid JUnit XML"
            elif check_id == "pytest":
                item["status"] = "fail"
                item["error"] = "Required JUnit XML missing"
        else:
            item = {"id": check_id, "command": command, "status": "not_run"}
            if check_id in PYTEST_CHECKS and pytest_timeout != 900:
                item["timeout_seconds"] = pytest_timeout
        checks.append(item)
    build_passed = next(c for c in checks if c["id"] == "build")["status"] == "pass"
    if package_install and run_checks:
        wheels = list((run / "artifacts").glob("*.whl"))
        if len(wheels) == 1 and build_passed:
            wheel_artifact = {
                "path": wheels[0].relative_to(run).as_posix(),
                "sha256": sha256(wheels[0]),
                "size": wheels[0].stat().st_size,
                "kind": "wheel",
            }
            # mkdtemp guarantees no existing environment or user files are reused/deleted.
            environment = Path(tempfile.mkdtemp(prefix="wheel-", dir=scratch))
            checks.append(
                execute(
                    "wheel_venv",
                    [sys.executable, "-m", "venv", str(environment)],
                    repo,
                    run,
                    scratch,
                )
            )
            python = str(environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
            if checks[-1]["status"] == "pass":
                options = {}
                if offline_packages is None:
                    install_command = [
                        python,
                        "-I",
                        "-m",
                        "pip",
                        "install",
                        str(wheels[0]) + "[dev]",
                    ]
                else:
                    wheelhouse = offline_packages.wheelhouse
                    options["offline_wheelhouse"] = wheelhouse
                    dependencies = execute(
                        "wheel_offline_dependencies",
                        _offline_install(
                            python, wheelhouse, "--only-binary=:all:", *offline_packages.application
                        ),
                        run,
                        run,
                        scratch,
                        **options,
                    )
                    checks.append(dependencies)
                    install_command = _offline_install(
                        python, wheelhouse, "--no-deps", "--force-reinstall", "--", str(wheels[0])
                    )
                if checks[-1]["status"] == "pass":
                    checks.append(
                        execute("wheel_install", install_command, run, run, scratch, **options)
                    )
                    checks[-1]["artifact"] = wheel_artifact
            if checks[-1]["id"] != "wheel_install" and offline_packages is not None:
                checks.append(
                    {
                        "id": "wheel_install",
                        "status": "not_run",
                        "artifact": wheel_artifact,
                        "reason": "Offline wheel environment or dependency preparation failed",
                    }
                )
            if checks[-1]["id"] == "wheel_install" and (
                offline_packages is None or checks[-1]["status"] == "pass"
            ):
                checks.append(
                    execute(
                        "wheel_pip_check",
                        [python, "-I", "-m", "pip", "check"],
                        run,
                        run,
                        scratch,
                        **options,
                    )
                )
                checks.append(
                    execute(
                        "wheel_cli", [python, "-I", "-m", "agentsync", "--help"], run, run, scratch
                    )
                )
                probe = (
                    "import agentsync, importlib.metadata, json, pathlib, tempfile; "
                    "from agentsync.sdk import AgentSyncClient; "
                    f"assert pathlib.Path(agentsync.__file__).resolve().is_relative_to(pathlib.Path({str(environment)!r}).resolve()); "
                    f"assert not pathlib.Path(agentsync.__file__).resolve().is_relative_to(pathlib.Path({str(repo)!r})); "
                    f"assert importlib.metadata.version('agentsync-local') == {project['project']['version']!r}; "
                    "direct = json.loads(importlib.metadata.distribution('agentsync-local').read_text('direct_url.json')); "
                    f"assert direct['url'] == {wheels[0].resolve().as_uri()!r}; "
                    f"assert (direct['archive_info'].get('hashes', {{}}).get('sha256') or direct['archive_info'].get('hash', '').removeprefix('sha256=')) == {wheel_artifact['sha256']!r}; "
                    "assert not direct.get('dir_info', {}).get('editable', False); "
                    "print('installed origin:', agentsync.__file__); "
                    "tmp = tempfile.TemporaryDirectory(); root = pathlib.Path(tmp.name) / 'project'; root.mkdir(); "
                    "client = AgentSyncClient(pathlib.Path(tmp.name) / 'data'); "
                    "result = client.call('create_project', name='isolated wheel smoke', root_path=str(root)); "
                    "assert result['ok'], result; print('SDK smoke: pass'); tmp.cleanup()"
                )
                origin = execute("wheel_origin_sdk", [python, "-I", "-c", probe], run, run, scratch)
                if license_inventory:
                    origin["artifact"] = wheel_artifact.copy()
                checks.append(origin)
                if next(c for c in checks if c["id"] == "wheel_install")["status"] == "pass":
                    if origin["status"] == "pass":
                        checks.append(
                            _installed_console_smoke("wheel", python, run, scratch, wheel_artifact)
                        )
                    if license_inventory and origin["status"] == "pass":
                        checks.append(
                            _installed_license_inventory(
                                "wheel",
                                python,
                                repo,
                                run,
                                scratch,
                                project["project"]["version"],
                                wheel_artifact,
                                origin,
                            )
                        )
                    installed = _execute_check(
                        "wheel_pytest",
                        [
                            python,
                            "-I",
                            "-m",
                            "pytest",
                            str(repo / "tests"),
                            "--junitxml",
                            str(scratch / "wheel-junit.xml"),
                            "--basetemp",
                            str(scratch / "wheel-pytest"),
                        ],
                        run,
                        run,
                        scratch,
                        pytest_timeout,
                    )
                    try:
                        installed["junit_credential_redactions"] = persist_junit(
                            scratch / "wheel-junit.xml", run / "wheel-junit.xml"
                        )
                        installed["junit"] = junit_counts(run / "wheel-junit.xml")
                        if (
                            not installed["junit"]["tests"]
                            or installed["junit"]["failures"]
                            or installed["junit"]["errors"]
                        ):
                            installed["status"] = "fail"
                    except (OSError, ValueError, ET.ParseError):
                        installed["status"] = "fail"
                        installed["error"] = "Installed-wheel JUnit missing or invalid"
                    checks.append(installed)
            if not wheels[0].is_file() or sha256(wheels[0]) != wheel_artifact["sha256"]:
                checks.append(
                    {
                        "id": "wheel_artifact_stability",
                        "status": "fail",
                        "reason": "Wheel archive changed during installation or testing",
                        "artifact": wheel_artifact,
                    }
                )
        else:
            build_blocked = offline_wheelhouse is not None and not build_passed
            checks.append(
                {
                    "id": "wheel_install",
                    "status": "not_run" if build_blocked else "fail",
                    "reason": "Source build did not succeed"
                    if build_blocked
                    else "Build produced no unique successful wheel",
                }
            )
    else:
        checks.append(
            {
                "id": "wheel_install",
                "status": "not_run",
                "reason": "Requires --run --package-install",
            }
        )
    if sdist_install:
        if offline_wheelhouse is not None and not build_passed:
            checks.append(
                {
                    "id": "sdist_install",
                    "status": "not_run",
                    "reason": "Source build did not succeed",
                }
            )
        else:
            options = {}
            if offline_packages is not None:
                options["offline_packages"] = offline_packages
            if license_inventory:
                options["license_inventory"] = True
            checks.extend(
                sdist_checks(
                    repo,
                    run,
                    scratch,
                    project["project"]["version"],
                    build_passed,
                    pytest_timeout=pytest_timeout,
                    **options,
                )
            )
    else:
        checks.append(
            {"id": "sdist_install", "status": "not_run", "reason": "Requires --run --sdist-install"}
        )
    if license_inventory:
        for kind, requested in (("wheel", package_install), ("sdist", sdist_install)):
            check_id = kind + "_license_inventory"
            if requested and not any(c["id"] == check_id for c in checks):
                checks.append(
                    {
                        "id": check_id,
                        "status": "not_run",
                        "reason": "Installed artifact origin was not verified",
                    }
                )
    manifest_path = repo / "docs" / "acceptance" / "requirements.json"
    manifest = None
    manifest_error = None
    manifest_digest = None
    if manifest_path.is_file():
        # Snapshot exact design input, without interpreting documentation as test results.
        try:
            with manifest_path.open("rb") as stream:
                manifest_bytes = stream.read(4 * 1024 * 1024 + 1)
            if len(manifest_bytes) > 4 * 1024 * 1024:
                raise ValueError("Requirements manifest exceeds its size limit")
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            if not isinstance(manifest, dict) or not isinstance(manifest.get("requirements"), list):
                raise ValueError("requirements must be an array")
            if any(
                not isinstance(r, dict)
                or not isinstance(r.get("id"), str)
                or not isinstance(r.get("existing_tests", []), list)
                or any(not isinstance(s, str) for s in r.get("existing_tests", []))
                for r in manifest["requirements"]
            ):
                raise ValueError("Each requirement needs a string id and string test selectors")
            ids = [r["id"] for r in manifest["requirements"]]
            if len(ids) != len(set(ids)):
                raise ValueError("Requirement IDs must be unique")
            if "requirement_count" in manifest and manifest["requirement_count"] != len(ids):
                raise ValueError("requirement_count does not match requirement rows")
            scenarios = manifest.get("scenarios", [])
            if (
                type(scenarios) is not list
                or any(
                    type(row) is not dict
                    or any(
                        type(row.get(key)) is not str
                        for key in ("id", "title", "expected", "evidence")
                    )
                    or re.fullmatch(r"T(?:0[1-9]|1[0-6])", row["id"]) is None
                    or type(row.get("requirements")) is not list
                    or not row["requirements"]
                    or any(
                        type(identity) is not str or identity not in ids
                        for identity in row["requirements"]
                    )
                    for row in scenarios
                )
                or len({row["id"] for row in scenarios}) != len(scenarios)
            ):
                raise ValueError("Invalid original acceptance scenarios")
            (run / "requirements.json").write_bytes(manifest_bytes)
            manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
        except (ValueError, OSError) as exc:
            manifest = None
            manifest_error = str(exc)
            checks.append(
                {"id": "requirements_manifest", "status": "fail", "reason": manifest_error}
            )
    source_changed = source != source_snapshot(repo)
    if source_changed:
        checks.append(
            {
                "id": "source_stability",
                "status": "fail",
                "reason": "Git-visible source changed during execution; rerun against a stable source snapshot",
            }
        )
    selected_checks = [
        c
        for c in checks
        if (c["id"] != "wheel_install" or package_install)
        and (c["id"] != "sdist_install" or sdist_install)
    ]
    sdist_isolation = (
        "PEP 517 with preloaded build requirements in the fresh install environment; no cached wheel or editable fallback"
        if offline_wheelhouse is not None
        else "PEP 517 default isolation; no cached wheel or editable fallback"
    )
    requirements = requirement_results(manifest, run)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "version": project["project"]["version"],
        "commit_sha": git_value(repo, "rev-parse", "HEAD"),
        "tree_sha": git_value(repo, "rev-parse", "HEAD^{tree}"),
        "working_tree_status": git_value(repo, "status", "--porcelain"),
        "working_tree_patch_sha256": sha256(run / "working-tree.patch"),
        "original_working_tree_patch_sha256": original_patch_sha,
        "working_tree_patch_redactions": patch_redactions,
        "source_snapshot_sha256": sha256(run / "source-snapshot.json"),
        "source_changed_during_execution": source_changed,
        "platform": platform.platform(),
        "python": sys.version,
        "executable": sys.executable,
        "repo": str(repo),
        "evidence_directory": str(run),
        "checks": checks,
        "distribution_installations": [
            {
                "kind": "sdist" if check["id"] == "sdist_install" else "wheel",
                "artifact": check.get("artifact"),
                "status": check["status"],
                "evidence_log": check.get("log"),
                "build_isolation": sdist_isolation
                if check["id"] == "sdist_install"
                else "Wheel installation; no sdist rebuild asserted",
            }
            for check in checks
            if check["id"] in {"sdist_install", "wheel_install"}
        ],
        "requirements_manifest_error": manifest_error,
        "requirements_register_sha256": manifest_digest,
        "requirements": requirements,
        "scenarios": scenario_results(manifest, requirements),
        "release_gate": release_gate(selected_checks, run),
        "coverage": {
            "actual_clients": "unverified",
            "real_autonomous_dual_agent_relay": "unverified",
            "cross_platform_matrix": "not_run",
            "paid_provider_calls": "restricted",
            "requirements_manifest": "present" if manifest is not None else "not_run",
        },
        "limitations": [
            "Current-source protocol tests are not actual model-client tests.",
            "Dirty tree and untracked paths are recorded; commit SHA alone does not describe dirty source.",
            "Hashes detect accidental evidence modification; they are not signatures or independent attestation.",
            "The saved working-tree patch is redacted; its hash differs from the original collected diff text when redactions occur. Original diff text hash and exact source-file hashes are recorded without storing unredacted diff contents.",
            "Logs and JUnit redact known keyed credentials, Bearer values and recognized API-key prefixes; this is best-effort filtering, not proof that arbitrary secrets are absent.",
        ],
    }
    if offline_wheelhouse is not None:
        report["package_resolution"] = {
            "mode": "offline_wheelhouse",
            "wheelhouse_manifest": "offline-wheelhouse.json"
            if offline_packages is not None
            else None,
            "source_build": "Fresh environment with build tools preloaded from the staged wheels",
            "artifact_install": "Fresh environment with declared runtime and dev requirements preloaded from the staged wheels, then exact local artifact installation without dependency resolution",
            "network_scope": "Pip package resolution only. Trusted build, package and test code is not isolated from the operating system network.",
        }
    if candidate_input is not None:
        report["candidate_input"] = candidate_input
    report["artifacts"] = [
        {"path": p.relative_to(run).as_posix(), "sha256": sha256(p), "size": p.stat().st_size}
        for p in sorted(run.rglob("*"))
        if p.is_file()
    ]
    (run / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = [
        "# Release Acceptance Report",
        "",
        f"Version: {report['version']}",
        f"Commit: {report['commit_sha']}",
        f"Platform: {report['platform']}",
        "",
        "Formal release acceptance: **BLOCKED**",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    rows.extend(
        f"| {c['id']} | {c['status']} | {c.get('inventory', {}).get('path', c.get('log', c.get('reason', 'Not executed')))} |"
        for c in checks
    )
    rows.extend(
        [
            "",
            "## Distribution installations",
            "",
            "| Format | Install status | Exact artifact | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for installation in report["distribution_installations"]:
        artifact = installation["artifact"] or {}
        rows.append(
            f"| {installation['kind']} | {installation['status']} | {artifact.get('path', 'Not installed')} | {artifact.get('sha256', 'No installed artifact evidence')} |"
        )
    rows.extend(
        [
            "",
            "## Per-requirement acceptance",
            "",
            "Component test observations do not satisfy complete requirement acceptance. Planned evidence paths are targets, not existing files.",
            "",
            "| Requirement | Title | Execution | Acceptance evidence | Coverage | Component selectors |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for requirement in report["requirements"]:
        components = []
        for evidence in requirement["component_evidence"]:
            observations = (
                "; ".join(
                    f"{o['junit']}: {o['counts']['tests']} matched, {o['counts']['passed']} passed, {o['counts']['failures']} failures, {o['counts']['errors']} errors, {o['counts']['skipped']} skipped"
                    for o in evidence["observations"]
                )
                or "not executed"
            )
            components.append(f"{evidence['selector']} ({observations})")
        selectors = "; ".join(components) or "None implemented"
        title = requirement["title"].replace("|", "\\|")
        rows.append(
            f"| {requirement['id']} | {title} | {requirement['execution_status']} | {requirement['acceptance_evidence_status']} | {requirement['coverage']} | {selectors} |"
        )
    if not report["requirements"]:
        rows.append(
            "No valid requirements manifest was available; per-requirement acceptance remains not_run."
        )
    if report["scenarios"]:
        rows.extend(
            [
                "",
                "## Original acceptance scenarios",
                "",
                "Related component observations are references only. The collector does not execute the full original scenarios.",
                "",
                "| Scenario | Execution | Related requirements with component observations |",
                "| --- | --- | --- |",
            ]
        )
        for scenario in report["scenarios"]:
            related = ", ".join(scenario["requirements_with_component_observations"]) or "None"
            rows.append(f"| {scenario['id']} | {scenario['execution_status']} | {related} |")
    rows.extend(["", "## Required outstanding evidence", ""])
    rows.extend(f"- {key}: {value}" for key, value in RELEASE_BLOCKERS.items())
    rows.extend(
        [
            "",
            "## Scope and reproduction",
            "",
            "Commands, exit codes, JUnit counts, version, SHA, platform and artifact hashes are in report.json.",
            "Run from the recorded source with the recorded commands. No actual-client or autonomous relay result is inferred from local tests.",
            "Skipped tests remain skipped in JUnit; they are not passes. No destructive user-workspace tests or paid calls are performed.",
        ]
    )
    if offline_wheelhouse is not None:
        rows.append(
            "Offline package resolution uses staged local wheels. Trusted build, package and test code retains operating system network access."
        )
    if license_inventory:
        rows.append("Installed license inventories record metadata for pending human review.")
    (run / "Release-Acceptance-Report.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-release",
        action="store_true",
        help="Exit 2 when the formal release gate remains blocked; default only fails executed local checks",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Evidence parent directory; a unique child is created",
    )
    parser.add_argument(
        "--scratch-root",
        type=Path,
        help="Optional short temporary parent outside the source; only a fresh child is cleaned",
    )
    parser.add_argument(
        "--pytest-timeout",
        type=int,
        default=900,
        help="Full-suite pytest controller timeout in seconds (1..7200; default 900); other checks stay at 900",
    )
    parser.add_argument(
        "--run", action="store_true", help="Execute existing local validation checks"
    )
    parser.add_argument(
        "--package-install",
        action="store_true",
        help="Also install built wheel in an isolated environment (may download dependencies)",
    )
    parser.add_argument(
        "--sdist-install",
        action="store_true",
        help="Build/install the sdist in another isolated environment and run its full suite (may download dependencies)",
    )
    parser.add_argument(
        "--offline-wheelhouse",
        type=Path,
        help="Resolve build and install requirements from a local directory of wheels (requires --run)",
    )
    parser.add_argument(
        "--license-inventory",
        action="store_true",
        help="Collect runtime license metadata after verifying each requested fresh install",
    )
    parser.add_argument(
        "--candidate-manifest", type=Path, help="Manifest for exact offline archives to install"
    )
    parser.add_argument(
        "--candidate-evidence-root", type=Path, help="Local root of the manifest's archives"
    )
    parser.add_argument("--candidate-sha256", help="Independently trusted manifest digest")
    args = parser.parse_args()
    try:
        _validate_pytest_timeout(args.pytest_timeout)
    except ValueError as exc:
        parser.error(str(exc))
    if args.package_install and not args.run:
        parser.error("--package-install requires --run")
    if args.sdist_install and not args.run:
        parser.error("--sdist-install requires --run")
    if args.offline_wheelhouse is not None and not args.run:
        parser.error("--offline-wheelhouse requires --run")
    if args.license_inventory and not (args.run and (args.package_install or args.sdist_install)):
        parser.error("--license-inventory requires --run and a requested distribution install")
    collect_options = {} if args.scratch_root is None else {"scratch_root": args.scratch_root}
    if args.pytest_timeout != 900:
        collect_options["pytest_timeout"] = args.pytest_timeout
    if args.offline_wheelhouse is not None:
        collect_options["offline_wheelhouse"] = args.offline_wheelhouse
    if args.license_inventory:
        collect_options["license_inventory"] = True
    candidate = (args.candidate_manifest, args.candidate_evidence_root, args.candidate_sha256)
    if any(value is not None for value in candidate):
        if any(value is None for value in candidate):
            parser.error(
                "Candidate installs require the manifest, evidence root and trusted SHA-256."
            )
        if not (
            args.run and args.package_install and args.sdist_install and args.offline_wheelhouse
        ):
            parser.error(
                "Candidate installs require --run, both installs and --offline-wheelhouse."
            )
        collect_options["candidate"] = candidate
    run = collect(
        Path(__file__).resolve().parents[1],
        args.output.resolve(),
        run_checks=args.run,
        package_install=args.package_install,
        sdist_install=args.sdist_install,
        **collect_options,
    )
    print(run / "Release-Acceptance-Report.md")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    if any(c["status"] == "fail" for c in report["checks"]):
        return 1
    return 2 if args.require_release and not report["release_gate"]["formal_acceptance"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

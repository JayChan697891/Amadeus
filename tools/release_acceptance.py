"""Collect reproducible local evidence without declaring unverified release acceptance.

Run from any directory: python tools/release_acceptance.py --output F:/syuc/evidence
Add --run to execute checks, --package-install for a separate wheel environment,
and --sdist-install for a separate source-distribution build and installation.
No client credentials, model calls, workspace cleanup or Git mutations are performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

STATUSES = {"pass", "fail", "not_run", "restricted", "unverified"}
MAX_LOG_BYTES = 16 * 1024 * 1024
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                if requirement_id in {"M2-05", "M6-03", "M6-04", "M6-05"}
                else "not_run",
                "component_evidence": component,
                "component_evidence_scope": "Exact-selector local protocol/unit observations only; no whole-requirement or actual-client acceptance inferred.",
                "planned_evidence": requirement.get("evidence"),
                "release_gate": requirement.get("release_gate"),
            }
        )
    return rows


def execute(
    check_id: str, command: list[str], repo: Path, run: Path, scratch: Path | None = None
) -> dict:
    log = run / "logs" / f"{check_id}.log"
    started = datetime.now(UTC)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if check_id == "build" or check_id.startswith(("sdist_", "wheel_")):
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
    env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
    exit_code = None
    # Raw process output exists only in a self-deleting scratch file. It is never
    # placed in the durable/uploadable log directory, even for failed commands.
    with tempfile.TemporaryFile(mode="w+b", dir=temporary) as stream:
        try:
            result = subprocess.run(
                command,
                cwd=repo,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
            exit_code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            stream.write(f"\nRunner error: {type(exc).__name__}: {exc}\n".encode())
        stream.seek(0)
        raw = stream.read(MAX_LOG_BYTES + 1)
    truncated = len(raw) > MAX_LOG_BYTES
    clean, redactions = redact_credentials(raw[:MAX_LOG_BYTES].decode("utf-8", errors="replace"))
    if truncated:
        clean += "\n[OUTPUT TRUNCATED: evidence processing limit reached]\n"
    log.write_text(clean, encoding="utf-8")
    return {
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
    repo: Path, run: Path, scratch: Path, version: str, build_passed: bool
) -> list[dict]:
    """Install only the selected sdist in a fresh environment; never fall back to source."""
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

    def invoke(name: str, command: list[str]) -> dict:
        result = execute("sdist_" + name, command, run, run, scratch)
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
    installed = invoke(
        "install",
        [
            python,
            "-I",
            "-m",
            "pip",
            "install",
            "--use-pep517",
            "--no-cache-dir",
            str(archive) + "[dev]",
        ],
    )
    if installed["status"] != "pass":
        skipped(
            ["pip_check", "cli", "origin_sdk", "pytest"],
            "Sdist installation failed; no fallback attempted",
        )
        return checks
    invoke("pip_check", [python, "-I", "-m", "pip", "check"])
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


def collect(
    repo: Path,
    output: Path,
    *,
    run_checks: bool,
    package_install: bool,
    sdist_install: bool = False,
) -> Path:
    if sdist_install and not run_checks:
        raise ValueError("--sdist-install requires --run")
    output = output.resolve()
    if output.is_relative_to(repo.resolve()):
        raise ValueError("Evidence output must be outside the source repository")
    output.mkdir(parents=True, exist_ok=True)
    # Test DBs/auth files and wheel environments are never durable report artifacts.
    # TemporaryDirectory cleans only this freshly created directory, even on failure.
    with tempfile.TemporaryDirectory(prefix=".scratch-", dir=output) as temporary:
        return _collect(
            repo.resolve(), output, Path(temporary), run_checks, package_install, sdist_install
        )


def _collect(
    repo: Path,
    output: Path,
    scratch: Path,
    run_checks: bool,
    package_install: bool,
    sdist_install: bool = False,
) -> Path:
    run = output / (
        "release-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    )
    run.mkdir()
    for child in ("logs", "artifacts"):
        (run / child).mkdir()
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))
    diff = git_value(repo, "diff", "HEAD", "--binary")
    original_patch_sha = hashlib.sha256((diff or "").encode("utf-8")).hexdigest()
    safe_patch, patch_redactions = redact_credentials(diff or "")
    (run / "working-tree.patch").write_text(safe_patch, encoding="utf-8")
    source = source_snapshot(repo)
    (run / "source-snapshot.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
    plan = check_plan(sys.executable, run, scratch)
    checks = []
    for check_id, command in plan:
        if run_checks:
            item = execute(check_id, command, repo, run, scratch)
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
        checks.append(item)
    if package_install and run_checks:
        wheels = list((run / "artifacts").glob("*.whl"))
        if len(wheels) == 1 and next(c for c in checks if c["id"] == "build")["status"] == "pass":
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
                checks.append(
                    execute(
                        "wheel_install",
                        [python, "-I", "-m", "pip", "install", str(wheels[0]) + "[dev]"],
                        run,
                        run,
                        scratch,
                    )
                )
                checks[-1]["artifact"] = wheel_artifact
                checks.append(
                    execute(
                        "wheel_pip_check", [python, "-I", "-m", "pip", "check"], run, run, scratch
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
                checks.append(
                    execute("wheel_origin_sdk", [python, "-I", "-c", probe], run, run, scratch)
                )
                if next(c for c in checks if c["id"] == "wheel_install")["status"] == "pass":
                    installed = execute(
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
        else:
            checks.append(
                {
                    "id": "wheel_install",
                    "status": "fail",
                    "reason": "Build produced no unique successful wheel",
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
        checks.extend(
            sdist_checks(
                repo,
                run,
                scratch,
                project["project"]["version"],
                next(c for c in checks if c["id"] == "build")["status"] == "pass",
            )
        )
    else:
        checks.append(
            {"id": "sdist_install", "status": "not_run", "reason": "Requires --run --sdist-install"}
        )
    manifest_path = repo / "docs" / "acceptance" / "requirements.json"
    manifest = None
    manifest_error = None
    if manifest_path.is_file():
        # Snapshot exact design input, without interpreting documentation as test results.
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
            (run / "requirements.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
                "build_isolation": "PEP 517 default isolation; no cached wheel or editable fallback"
                if check["id"] == "sdist_install"
                else "Wheel installation; no sdist rebuild asserted",
            }
            for check in checks
            if check["id"] in {"sdist_install", "wheel_install"}
        ],
        "requirements_manifest_error": manifest_error,
        "requirements": requirement_results(manifest, run),
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
        f"| {c['id']} | {c['status']} | {c.get('log', c.get('reason', 'Not executed'))} |"
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
    args = parser.parse_args()
    if args.package_install and not args.run:
        parser.error("--package-install requires --run")
    if args.sdist_install and not args.run:
        parser.error("--sdist-install requires --run")
    run = collect(
        Path(__file__).resolve().parents[1],
        args.output.resolve(),
        run_checks=args.run,
        package_install=args.package_install,
        sdist_install=args.sdist_install,
    )
    print(run / "Release-Acceptance-Report.md")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    if any(c["status"] == "fail" for c in report["checks"]):
        return 1
    return 2 if args.require_release and not report["release_gate"]["formal_acceptance"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

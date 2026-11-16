
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

BASE = Path("D:/agentsync-debug/continuation-verified-20261116")
INPUT = Path("D:/agentsync-debug/continuation-bridge-20261116")
OLD = Path("D:/agentsync-debug/m118p")
SOURCE = BASE / "frozen-src"
VENV = BASE / "source-env-r2"
RUN = BASE / "isolated-host-exit-r2"
BOOTSTRAP = OLD / "w/Scripts/python.exe"
OLD_SITE = OLD / "w/Lib/site-packages"
PYTHON = VENV / "Scripts/python.exe"
COMMIT = "207e9781c4b7d44a4301cabac4120ddcf6ec6ac1"
SOURCE_ZIP = "f36c58054e6e7cd6e4483e03af8d6158cb05ac3bfc5bef19deb5d3e6ee715a6a"
SOURCE_MANIFEST = "2c83d1aede91ecf11fbf4302c4c27157b67bc597e432d023b5f6ac569d799b46"
RUNTIME_MEMBERS = "f96b477564c0be1207de7d11433977bf96c24b6d0bf45438a07c3087713bf5bd"
TESTS = [
    "tests/integration/test_unfinished_continuation.py::test_host_exit_preserves_continuation_recovery[prepared]",
    "tests/integration/test_unfinished_continuation.py::test_host_exit_preserves_continuation_recovery[dispatch-intent]",
]

def stamp():
    return datetime.now(UTC).isoformat()

def sha(path):
    return sha256(path.read_bytes()).hexdigest()

def save(name, value):
    with (RUN / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")

def copy_snapshot():
    archive, manifest = INPUT / "source.zip", INPUT / "inputs.json"
    assert sha(archive) == SOURCE_ZIP and sha(manifest) == SOURCE_MANIFEST
    expected = json.loads(manifest.read_bytes())
    assert expected["commit"] == COMMIT and expected["archive_sha256"] == SOURCE_ZIP
    files = expected["files"]
    assert len(files) == 233
    assert SOURCE.resolve(strict=True) == SOURCE and SOURCE.is_dir()
    with ZipFile(archive) as zipfile:
        members = [member for member in zipfile.infolist() if not member.is_dir()]
        assert len(members) == 233 and {member.filename for member in members} == files.keys()
    return files

def verify_tree(root, expected, *, installed=False):
    actual = {}
    paths = (root / "agentsync" if installed else root).rglob("*")
    for path in paths:
        if installed and "__pycache__" in path.relative_to(root).parts:
            continue
        assert path.resolve(strict=True) == path
        if path.is_file():
            assert stat.S_ISREG(path.lstat().st_mode)
            actual[path.relative_to(root).as_posix()] = sha(path)
    assert actual == expected
    return len(actual)

assert Path(sys.executable) == BOOTSTRAP and sys.version_info[:3] == (3, 12, 16)
assert not any(path.exists() for path in (VENV, RUN))
RUN.mkdir()
for name in ("home", "tmp"):
    (RUN / name).mkdir()
env = {}
for name, value in os.environ.items():
    clean = name.upper()
    if not clean.startswith((
        "OPENAI_", "ANTHROPIC_", "CLAUDE_", "CURSOR_", "CODEX_", "GEMINI_", "GOOGLE_", "DEEPSEEK_",
        "GITHUB_", "AGENTSYNC_", "GIT_", "PYTHON", "PYTEST_", "PIP_", "UV_",
    )) and not clean.endswith(("API_KEY", "ACCESS_TOKEN", "REFRESH_TOKEN")):
        env[name] = value
overrides = dict(
    HOME=str(RUN / "home"), USERPROFILE=str(RUN / "home"), LOCALAPPDATA=str(RUN / "home"),
    TMP=str(RUN / "tmp"), TEMP=str(RUN / "tmp"), PYTHONDONTWRITEBYTECODE="1",
    GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
)
env.update(overrides)
manifest = OLD / "run/runtime-members.json"
assert sha(manifest) == RUNTIME_MEMBERS
old_members = json.loads(manifest.read_bytes())
assert len(old_members) == 97
old_before = verify_tree(OLD_SITE, old_members, installed=True)
files = None
checks = []

def execute(name, argv, cwd):
    command = list(map(str, argv))
    record = {
        "command": command, "cwd": str(cwd), "started_at": stamp(), "timeout_seconds": 120,
        "provenance": "local_process", "status": "running",
    }
    log = RUN / f"{name}.log"
    save(f"{name}-start.json", record)
    try:
        with log.open("xb") as stream:
            process = subprocess.run(
                command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stream,
                stderr=subprocess.STDOUT, timeout=120, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        record["exit_code"] = process.returncode
        record["status"] = "exited"
    except (OSError, subprocess.TimeoutExpired) as exc:
        record["status"] = "observer_error"
        record["error_type"] = type(exc).__name__
        raise
    finally:
        record["finished_at"] = stamp()
        if log.is_file():
            record["log_sha256"] = sha(log)
        save(f"{name}.process.json", record)
        checks.append({"id": name, **record})
    return process.returncode

start = {
    "started_at": stamp(), "commit": COMMIT, "source_zip_sha256": SOURCE_ZIP,
    "manifest_sha256": SOURCE_MANIFEST, "old_runtime_manifest_sha256": RUNTIME_MEMBERS,
    "old_installed_members_before": old_before,
    "explicit_environment": overrides, "pythonpath_inherited": False,
    "scope": "Only the two existing Windows host-exit cases using the frozen source",
    "no_model_calls": True, "docker": "NOT RUN", "automatic_retry": False,
}
save("start.json", start)
result = {**start, "status": "failed", "phase": "extract", "pytest_exit_code": None}
try:
    files = copy_snapshot()
    result["frozen_paths_before"] = verify_tree(SOURCE, files)
    result["phase"] = "venv"
    assert execute("venv", [BOOTSTRAP, "-I", "-B", "-m", "venv", "--without-pip", VENV], RUN) == 0
    pth = VENV / "Lib/site-packages/continuation-source.pth"
    with pth.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f"{(SOURCE / 'src').as_posix()}\n"
            f"import site, sys; sys.dont_write_bytecode = True; site.addsitedir({OLD_SITE.as_posix()!r})\n"
        )
    result["source_pth_sha256"] = sha(pth)
    result["phase"] = "origin"
    probe = (
        "from pathlib import Path; import sys, json, agentsync, agentsync.continuation, agentsync.controlled_relay, pytest, mcp, pywintypes;"
        "s,w,v=map(lambda x:Path(x).resolve(),sys.argv[1:4]); "
        "assert 'PYTHONPATH' not in __import__('os').environ; "
        "assert Path(sys.prefix).resolve()==v; "
        "assert all(Path(m.__file__).resolve().parent==s/'agentsync' "
        "for m in (agentsync,agentsync.continuation,agentsync.controlled_relay)); "
        "assert all(Path(m.__file__).resolve().is_relative_to(w) for m in (pytest,mcp,pywintypes)); "
        "assert sys.dont_write_bytecode; "
        "print(json.dumps(dict(origin=agentsync.__file__, pytest_origin=pytest.__file__, "
        "mcp_origin=mcp.__file__, pywintypes_origin=pywintypes.__file__, "
        "prefix=sys.prefix, python=sys.version.split()[0], isolated=bool(sys.flags.isolated))))"
    )
    origins = {}
    for name, flags in (("origin_parent", ["-s", "-B"]), ("origin_child_isolated", ["-I", "-B"])):
        assert execute(name, [PYTHON, *flags, "-c", probe, SOURCE / "src", OLD_SITE, VENV], RUN) == 0
        origins[name] = json.loads((RUN / f"{name}.log").read_bytes())
    assert origins["origin_parent"]["isolated"] is False
    assert origins["origin_child_isolated"]["isolated"] is True
    assert origins["origin_parent"]["origin"] == origins["origin_child_isolated"]["origin"]
    result["origins"] = origins
    result["phase"] = "pytest"
    xml = RUN / "host-exit.xml"
    command = [
        PYTHON, "-I", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
        "--basetemp", RUN / "p", f"--junitxml={xml}",
        *(str(SOURCE / selection) for selection in TESTS),
    ]
    exit_code = execute("host-exit", command, RUN)
    result["pytest_exit_code"] = exit_code
    with (RUN / "host-exit.exit").open("x", encoding="ascii") as stream:
        stream.write(f"{exit_code}\n")
    report = ET.parse(xml).getroot().find("testsuite")
    rows = list(report.iter("testcase"))
    assert {row.get("name") for row in rows} == {
        "test_host_exit_preserves_continuation_recovery[prepared]",
        "test_host_exit_preserves_continuation_recovery[dispatch-intent]",
    }
    result["junit"] = {
        "sha256": sha(xml),
        **{name: int(report.get(name)) for name in ("tests", "failures", "errors", "skipped")},
    }
    assert exit_code == 0 and len(rows) == 2 and all(
        result["junit"][name] == 0 for name in ("failures", "errors", "skipped")
    )
    result["status"] = "passed"
except (Exception, KeyboardInterrupt) as exc:
    result["error_type"] = type(exc).__name__
finally:
    result["finished_at"] = stamp()
    result["checks"] = checks
    try:
        result["old_installed_members_after"] = verify_tree(OLD_SITE, old_members, installed=True)
        if files is not None:
            result["frozen_paths_after"] = verify_tree(SOURCE, files)
        assert sha(INPUT / "source.zip") == SOURCE_ZIP and sha(INPUT / "inputs.json") == SOURCE_MANIFEST
        assert sha(manifest) == RUNTIME_MEMBERS
    except Exception as exc:
        result["status"] = "failed"
        result["postcheck_error_type"] = type(exc).__name__
    save("result.json", result)
print(json.dumps({
    "status": result["status"], "phase": result["phase"], "pytest_exit_code": result["pytest_exit_code"],
    "junit": result.get("junit"), "error_type": result.get("error_type"), "results": str(RUN),
}))
raise SystemExit(0 if result["status"] == "passed" else 1)

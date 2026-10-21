"""Fixed Docker black-box verifier. Policy mocks are not isolation evidence.

The host parses data and compares owner expectations; it never executes candidate
source. Only a local Linux daemon, a preloaded immutable image and this fixed
protocol are supported. Docker and the host kernel remain trusted infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
MAX_SOURCE = 128 * 1024
MAX_JSON = 64 * 1024
MAX_DEPTH = 32
MAX_INPUT = 1024 * 1024
MEMORY = 128 * 1024 * 1024
TMPFS = 8 * 1024 * 1024
PIDS = 32
NANO_CPUS = 1_000_000_000
SOCKET = Path("/var/run/docker.sock")
RUNTIME_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
LABEL = "org.agentsync.verifier.owner"
_ENVIRONMENT_GUARD = (
    "import os; "
    f"assert all(os.environ.get(k)==v for k,v in {RUNTIME_ENV!r}.items()); "
    f"assert set(os.environ)<=set({sorted(set(RUNTIME_ENV) | {'HOME', 'HOSTNAME'})!r}); "
)
BOOTSTRAP = (
    _ENVIRONMENT_GUARD + "import sys; n=sys.stdin.buffer.readline(); "
    "assert len(n)<16 and n.endswith(b'\\n'); size=int(n); "
    f"assert 0<size<={MAX_SOURCE}; "
    "source=sys.stdin.buffer.read(size); assert len(source)==size; "
    "exec(compile(source, '<candidate>', 'exec'), "
    "{'__name__':'__main__','__file__':'<candidate>'})"
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    raise ValueError("nonfinite JSON number")


def _depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("JSON nesting limit")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON keys must be strings")
            _depth(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _depth(item, depth + 1)
    elif type(value) not in {str, int, float, bool, type(None)}:
        raise ValueError("unsupported JSON value")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite JSON number")


def _canonical(value: Any) -> bytes:
    _depth(value)
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    encoded = data.encode("utf-8")
    if len(encoded) > MAX_JSON:
        raise ValueError("JSON value exceeds size limit")
    return encoded


def _json(data: bytes) -> Any:
    if len(data) > MAX_JSON:
        raise ValueError("JSON value exceeds size limit")
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    _depth(value)
    return value


def _equal(actual: Any, expected: Any) -> bool:
    # Integer and floating-point JSON numbers compare numerically; bool is a
    # separate JSON type and never compares equal to 0 or 1.
    numeric = {int, float}
    if type(actual) in numeric and type(expected) in numeric:
        return bool(actual == expected)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _equal(value, expected[key]) for key, value in actual.items()
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return bool(actual == expected)


@dataclass(frozen=True, init=False)
class JsonCase:
    input_json: bytes
    expected_json: bytes

    def __init__(self, input_value: Any, expected_value: Any):
        object.__setattr__(self, "input_json", _canonical(input_value))
        object.__setattr__(self, "expected_json", _canonical(expected_value))


@dataclass(frozen=True)
class DockerProfile:
    image_id: str
    cases: tuple[JsonCase, ...]
    timeout_seconds: float = 5
    output_bytes: int = 64 * 1024
    profile_id: str = "python-json-lines-v1"

    def __post_init__(self) -> None:
        if (
            self.profile_id != "python-json-lines-v1"
            or not isinstance(self.image_id, str)
            or not IMAGE_ID.fullmatch(self.image_id)
        ):
            raise ValueError("unsupported profile or nonimmutable image ID")
        if (
            type(self.cases) is not tuple
            or not 1 <= len(self.cases) <= 100
            or any(type(case) is not JsonCase for case in self.cases)
        ):
            raise ValueError("profile requires 1..100 immutable JSON cases")
        if (
            type(self.timeout_seconds) not in {int, float}
            or not math.isfinite(self.timeout_seconds)
            or not 0.1 <= self.timeout_seconds <= 10
            or type(self.output_bytes) is not int
            or not 128 <= self.output_bytes <= 64 * 1024
        ):
            raise ValueError("profile resource limit outside supported bounds")
        if sum(len(case.input_json) + 1 for case in self.cases) > MAX_INPUT:
            raise ValueError("profile input exceeds size limit")

    @property
    def sha256(self) -> str:
        return _digest(
            json.dumps(
                {
                    "profile_id": self.profile_id,
                    "image_id": self.image_id,
                    "cases": [
                        {"input": _json(case.input_json), "expected": _json(case.expected_json)}
                        for case in self.cases
                    ],
                    "timeout_seconds": self.timeout_seconds,
                    "output_bytes": self.output_bytes,
                    "memory_bytes": MEMORY,
                    "tmpfs_bytes": TMPFS,
                    "pids": PIDS,
                    "nano_cpus": NANO_CPUS,
                    "bootstrap_sha256": _digest(BOOTSTRAP.encode()),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )


@dataclass(frozen=True)
class VerificationResult:
    status: str
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        result = {"status": self.status, **json.loads(json.dumps(self.evidence))}
        result["error_code"] = result["errors"][0] if result["errors"] else None
        result["container_exit_code"] = result["candidate_exit_code"]
        result["image_id"] = result["image_sha256"]
        result["constraints_verified"] = "isolation" in result
        return result


class _Failure(Exception):
    def __init__(
        self,
        code: str,
        status: str = "error",
        *,
        isolation_checks: dict[str, bool] | None = None,
        isolation_summary: dict[str, Any] | None = None,
    ):
        self.code = code
        self.status = status
        self.isolation_checks = isolation_checks
        self.isolation_summary = isolation_summary


@dataclass
class _Process:
    returncode: int
    stdout: bytes
    stderr_bytes: int


def _run(
    command: list[str], env: dict[str, str], timeout: float, limit: int, payload: bytes = b""
) -> _Process:
    # File-backed stdin cannot deadlock on a candidate that never reads stdin.
    # Output is never copied into public evidence. Overflow is failure, not a
    # successful truncation; files are exclusively owned and self-deleting.
    with (
        tempfile.TemporaryFile() as incoming,
        tempfile.TemporaryFile() as outgoing,
        tempfile.TemporaryFile() as errors,
    ):
        incoming.write(payload)
        incoming.seek(0)
        try:
            process = subprocess.Popen(
                command, env=env, stdin=incoming, stdout=outgoing, stderr=errors, shell=False
            )
        except OSError:
            raise _Failure("docker_unavailable", "unsupported") from None
        deadline = time.monotonic() + timeout
        failure = None
        while True:
            if os.fstat(outgoing.fileno()).st_size > limit:
                failure = "stdout_limit"
            elif os.fstat(errors.fileno()).st_size > limit:
                failure = "stderr_limit"
            elif time.monotonic() >= deadline:
                failure = "timeout"
            if failure:
                process.kill()
                process.wait(timeout=5)
                raise _Failure(failure, "failed")
            if process.poll() is not None:
                # Recheck final sizes: a short-lived process can exit between polls.
                if os.fstat(outgoing.fileno()).st_size > limit:
                    raise _Failure("stdout_limit", "failed")
                if os.fstat(errors.fileno()).st_size > limit:
                    raise _Failure("stderr_limit", "failed")
                outgoing.seek(0)
                return _Process(
                    process.returncode, outgoing.read(limit + 1), os.fstat(errors.fileno()).st_size
                )
            time.sleep(0.01)


def _trusted_cli() -> str:
    if platform.system() != "Linux":
        raise _Failure("unsupported_platform", "unsupported")
    try:
        socket_info = SOCKET.stat()
        if not stat.S_ISSOCK(socket_info.st_mode) or socket_info.st_uid != 0:
            raise _Failure("untrusted_socket", "unsupported")
        if socket_info.st_mode & stat.S_IWOTH:
            raise _Failure("untrusted_socket", "unsupported")
        for location in ("/usr/bin/docker", "/usr/local/bin/docker"):
            try:
                path = Path(location).resolve(strict=True)
            except OSError:
                continue
            info = path.stat()
            if (
                stat.S_ISREG(info.st_mode)
                and info.st_uid == 0
                and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                and os.access(path, os.X_OK)
                and all(
                    ancestor.stat().st_uid == 0
                    and not ancestor.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                    for ancestor in path.parents
                )
            ):
                return str(path)
    except OSError:
        raise _Failure("docker_unavailable", "unsupported") from None
    raise _Failure("untrusted_docker_cli", "unsupported")


def _image_environment(config: dict[str, Any]) -> list[str]:
    if config.get("Volumes") or config.get("OnBuild"):
        raise _Failure("unsafe_image_config", "unsupported")
    patterns = {
        "PATH": r"(?:/usr/local/bin:)?/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin|/usr/local/bin:/usr/bin:/bin",
        "LANG": r"C\.UTF-8",
        "GPG_KEY": r"[A-F0-9]{40}",
        "PYTHON_VERSION": r"[0-9]+\.[0-9]+\.[0-9]+(?:[abrc]+[0-9]+)?",
        "PYTHON_SHA256": r"[a-f0-9]{64}",
        "PYTHONUNBUFFERED": r"1",
        "PYTHONDONTWRITEBYTECODE": r"1",
    }
    names = []
    for item in config.get("Env") or []:
        if not isinstance(item, str) or "=" not in item:
            raise _Failure("unsafe_image_environment", "unsupported")
        name, value = item.split("=", 1)
        if name in names or name not in patterns or not re.fullmatch(patterns[name], value):
            raise _Failure("unsafe_image_environment", "unsupported")
        names.append(name)
    return names


def _inspect_json(result: _Process) -> Any:
    if result.returncode:
        raise _Failure("docker_inspection_failed")
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise _Failure("docker_inspection_invalid") from None


def _isolation_summary(
    container: dict[str, Any], removed_environment_names: frozenset[str]
) -> dict[str, Any]:
    """Fixed-schema diagnostics, never raw daemon environment/command/config text."""
    host = container.get("HostConfig", {})
    config = container.get("Config", {})

    def enum(value: Any, allowed: set[str]) -> str:
        return value if isinstance(value, str) and value in allowed else "other"

    def digest(value: Any) -> str:
        return _digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())

    namespace_values = {"", "private", "host", "none", "default"}
    security_values = {
        "no-new-privileges",
        "no-new-privileges=true",
        "no-new-privileges:false",
        "seccomp=unconfined",
    }
    env = config.get("Env") or []
    tmpfs = host.get("Tmpfs") or {}
    options = tmpfs.get("/tmp", "")
    tokens = options.split(",") if isinstance(options, str) else []
    known_tokens = {
        "rw",
        "ro",
        "noexec",
        "exec",
        "nosuid",
        "suid",
        "nodev",
        "dev",
        "mode=1777",
        "size=8388608",
        "size=8m",
        "size=8M",
        "size=8192k",
        "size=8192K",
    }
    return {
        "user": enum(config.get("User"), {"65534:65534", "0", "0:0", "root"}),
        "environment_sha256": digest(env),
        "environment_count": len(env),
        "expected_runtime_environment_count": len(RUNTIME_ENV),
        "expected_removal_marker_count": sum(
            isinstance(item, str) and item in removed_environment_names for item in env
        ),
        "expected_environment_keys_present": {
            key: any(isinstance(item, str) and item.startswith(key + "=") for item in env)
            for key in RUNTIME_ENV
        },
        "expected_environment_values_match": {
            key: f"{key}={value}" in env for key, value in RUNTIME_ENV.items()
        },
        "entrypoint_sha256": digest(config.get("Entrypoint")),
        "command_sha256": digest(config.get("Cmd")),
        "security_options": [enum(item, security_values) for item in host.get("SecurityOpt") or []],
        "namespaces": {
            key: enum(host.get(key), namespace_values)
            for key in (
                "NetworkMode",
                "PidMode",
                "IpcMode",
                "CgroupnsMode",
                "UTSMode",
                "UsernsMode",
            )
        },
        "cap_drop": [enum(item, {"ALL", "all", "CAP_ALL"}) for item in host.get("CapDrop") or []],
        "mount_types": [
            enum(item.get("Type"), {"bind", "volume", "tmpfs", "image"})
            for item in container.get("Mounts") or []
            if isinstance(item, dict)
        ],
        "mounts_only_tmpfs_at_tmp": bool(container.get("Mounts"))
        and all(
            isinstance(item, dict)
            and item.get("Type") == "tmpfs"
            and item.get("Destination") == "/tmp"
            for item in container.get("Mounts") or []
        ),
        "resources": {
            key: value if type(value) is int and -1 <= value <= 2**63 - 1 else "other"
            for key in ("Memory", "MemorySwap", "NanoCpus", "PidsLimit")
            for value in [host.get(key)]
        },
        "tmpfs_paths_only_tmp": set(tmpfs) == {"/tmp"},
        "tmpfs_known_options": sorted(set(tokens) & known_tokens),
        "tmpfs_unknown_option_count": len([token for token in tokens if token not in known_tokens]),
        "tmpfs_options_sha256": digest(options),
    }


def _isolation(
    container: dict[str, Any],
    profile: DockerProfile,
    owner: str,
    removed_environment_names: frozenset[str],
) -> dict[str, Any]:
    host = container.get("HostConfig", {})
    config = container.get("Config", {})
    environment = sorted(f"{key}={value}" for key, value in RUNTIME_ENV.items())
    effective_env = config.get("Env") or []
    # Docker can retain bare NAME entries for --env NAME removals even though
    # those names are absent from the process environment. Accept only unique
    # removals derived from the previously validated immutable image config.
    environment_matches = (
        isinstance(effective_env, list)
        and all(isinstance(item, str) for item in effective_env)
        and len(effective_env) == len(set(effective_env))
        and sorted(item for item in effective_env if item not in removed_environment_names)
        == environment
    )
    expected_tmpfs = f"rw,noexec,nosuid,nodev,size={TMPFS},mode=1777"
    checks = {
        "owner": config.get("Labels", {}).get(LABEL) == owner,
        "image": container.get("Image") == profile.image_id,
        "user": config.get("User") == "65534:65534",
        "environment": environment_matches,
        "entrypoint": config.get("Entrypoint") == ["/usr/local/bin/python3"],
        "command": config.get("Cmd") == ["-I", "-u", "-c", BOOTSTRAP],
        "workdir": config.get("WorkingDir") == "/tmp",
        "healthcheck": config.get("Healthcheck", {}).get("Test") == ["NONE"],
        "network": host.get("NetworkMode") == "none" and not host.get("PortBindings"),
        "readonly": host.get("ReadonlyRootfs") is True,
        "privileged": host.get("Privileged") is False,
        "capabilities": set(host.get("CapDrop") or []) == {"ALL"} and not host.get("CapAdd"),
        "security": host.get("SecurityOpt") == ["no-new-privileges"],
        "namespaces": host.get("PidMode", "") == ""
        and host.get("IpcMode") == "private"
        and host.get("CgroupnsMode") == "private"
        and host.get("UTSMode", "") == ""
        and host.get("UsernsMode", "") == "",
        "mounts": not host.get("Binds")
        and not container.get("Mounts")
        and not host.get("VolumesFrom")
        and not host.get("Devices")
        and not host.get("DeviceRequests"),
        "resources": host.get("Memory") == MEMORY
        and host.get("MemorySwap") == MEMORY
        and host.get("NanoCpus") == NANO_CPUS
        and host.get("PidsLimit") == PIDS,
        "tmpfs": host.get("Tmpfs") == {"/tmp": expected_tmpfs},
        "groups": not host.get("GroupAdd"),
        "logs": host.get("LogConfig", {}).get("Type") == "none",
    }
    if not all(checks.values()):
        raise _Failure(
            "isolation_mismatch",
            "unsupported",
            isolation_checks=checks,
            isolation_summary=_isolation_summary(container, removed_environment_names),
        )
    return {
        "checks": checks,
        "memory_bytes": MEMORY,
        "swap_total_bytes": MEMORY,
        "nano_cpus": NANO_CPUS,
        "pids": PIDS,
        "tmpfs_bytes": TMPFS,
        "stdout_limit": profile.output_bytes,
        "stderr_limit": profile.output_bytes,
        "timeout_seconds": profile.timeout_seconds,
        "seccomp": "builtin",
        "expected_runtime_environment_count": len(RUNTIME_ENV),
        "expected_removal_marker_count": sum(
            item in removed_environment_names for item in effective_env
        ),
    }


def _cleanup_owned(
    base: list[str], env: dict[str, str], identity: str | None, owner: str, name: str
) -> bool:
    """Recover a lost create response by one exact generated name, delete only by ID."""
    try:
        owned = _inspect_json(
            _run([*base, "inspect", identity if identity is not None else name], env, 5, 256 * 1024)
        )
        if not isinstance(owned, list) or len(owned) != 1:
            return False
        actual = owned[0].get("Id")
        if (
            not isinstance(actual, str)
            or not CONTAINER_ID.fullmatch(actual)
            or (identity is not None and actual != identity)
            or owned[0].get("Name") != "/" + name
            or owned[0].get("Config", {}).get("Labels", {}).get(LABEL) != owner
        ):
            return False
        removed = _run([*base, "rm", "--force", actual], env, 5, 4096)
        return (
            removed.returncode == 0
            and removed.stdout.decode("ascii", errors="replace").strip() == actual
        )
    except (
        _Failure,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        subprocess.SubprocessError,
    ):
        return False


class _Lifecycle(Protocol):
    """Trusted in-process persistence/fencing hooks, never a request surface."""

    def before_create(self, owner: str, container_name: str) -> None: ...

    def created(self, container_id: str) -> None: ...

    def before_start(self) -> None: ...


def verify_python_json_lines(
    source: bytes,
    *,
    profile: DockerProfile,
    input_sha256: str,
    commit_sha: str,
    tree_sha: str,
    _lifecycle: _Lifecycle | None = None,
) -> VerificationResult:
    """Execute finite owner cases inside the inspected container, never on the host."""
    started = datetime.now(UTC)
    begin = time.monotonic()
    evidence: dict[str, Any] = {
        "provenance": "docker_black_box",
        "backend": "local-linux-docker",
        "verifier_version": 1,
        "verifier_source_sha256": _digest(Path(__file__).read_bytes()),
        "execution_started": False,
        "profile_id": profile.profile_id,
        "profile_sha256": profile.sha256,
        "cases_sha256": _digest(
            json.dumps(
                [
                    {"input": _json(case.input_json), "expected": _json(case.expected_json)}
                    for case in profile.cases
                ],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ),
        "image_sha256": profile.image_id,
        "input_sha256": input_sha256,
        "source_sha256": _digest(source),
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "platform": platform.system(),
        "kernel": platform.release(),
        "expected_case_count": len(profile.cases),
        "completed_case_count": 0,
        "checked_case_count": 0,
        "passed_case_count": 0,
        "candidate_exit_code": None,
        "cleanup_confirmed": True,
        "errors": [],
        "started_at": started.isoformat(),
    }
    status = "error"
    container_id = None
    owner = uuid.uuid4().hex
    container_name = "agentsync-verifier-" + owner
    base: list[str] = []
    env: dict[str, str] = {}
    try:
        if not source or len(source) > MAX_SOURCE:
            raise _Failure("source_limit", "failed")
        try:
            source.decode("utf-8")
        except UnicodeError:
            raise _Failure("source_encoding", "failed") from None
        if (
            not SHA256.fullmatch(input_sha256)
            or not OBJECT_ID.fullmatch(commit_sha)
            or not OBJECT_ID.fullmatch(tree_sha)
        ):
            raise _Failure("invalid_input_identity", "failed")
        cli = _trusted_cli()
        # No caller PATH/HOME/proxy/Docker context/auth/config environment reaches
        # the CLI. An owned empty config prevents loading the user's ~/.docker.
        with tempfile.TemporaryDirectory(prefix="agentsync-docker-config-") as config_dir:
            env = {"PATH": "/usr/bin:/bin", "HOME": config_dir, "LC_ALL": "C"}
            base = [cli, "--host", "unix:///var/run/docker.sock", "--config", config_dir]
            info = _inspect_json(
                _run([*base, "info", "--format", "{{json .}}"], env, 10, 256 * 1024)
            )
            if (
                info.get("OSType") != "linux"
                or info.get("CgroupVersion") != "2"
                or not any(
                    "name=seccomp,profile=builtin" == item
                    for item in info.get("SecurityOptions", [])
                )
                or any(
                    info.get(key) is not True
                    for key in ("MemoryLimit", "SwapLimit", "CpuCfsQuota", "PidsLimit")
                )
            ):
                raise _Failure("required_isolation_unavailable", "unsupported")
            evidence["docker_server_version"] = info.get("ServerVersion")
            evidence["cgroup_version"] = info.get("CgroupVersion")
            images = _inspect_json(
                _run([*base, "image", "inspect", profile.image_id], env, 10, 256 * 1024)
            )
            if (
                not isinstance(images, list)
                or len(images) != 1
                or images[0].get("Id") != profile.image_id
                or images[0].get("Os") != "linux"
            ):
                raise _Failure("image_identity_mismatch", "unsupported")
            inherited = _image_environment(images[0].get("Config", {}))
            removed_environment_names = frozenset(inherited) - RUNTIME_ENV.keys()
            command = [
                *base,
                "create",
                "--pull=never",
                "--interactive",
                "--network=none",
                "--user=65534:65534",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--ipc=private",
                "--cgroupns=private",
                f"--memory={MEMORY}",
                f"--memory-swap={MEMORY}",
                "--cpus=1",
                f"--pids-limit={PIDS}",
                f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={TMPFS},mode=1777",
                "--workdir=/tmp",
                "--no-healthcheck",
                "--log-driver=none",
                "--entrypoint=/usr/local/bin/python3",
                f"--label={LABEL}={owner}",
                f"--name={container_name}",
            ]
            for name in inherited:
                command.extend(["--env", name])
            for name, value in RUNTIME_ENV.items():
                command.extend(["--env", f"{name}={value}"])
            command.extend([profile.image_id, "-I", "-u", "-c", BOOTSTRAP])
            if _lifecycle is not None:
                try:
                    _lifecycle.before_create(owner, container_name)
                except Exception:
                    raise _Failure("lifecycle_error") from None
            # The daemon may create a container even if the CLI loses its reply.
            # From the moment create is sent, absence/cleanup is unconfirmed.
            evidence["cleanup_confirmed"] = False
            try:
                created = _run(command, env, 10, 4096)
            except (_Failure, OSError, subprocess.SubprocessError):
                evidence["cleanup_confirmed"] = _cleanup_owned(
                    base, env, None, owner, container_name
                )
                raise _Failure("container_create_failed") from None
            identity = created.stdout.decode("ascii", errors="replace").strip()
            if created.returncode or not CONTAINER_ID.fullmatch(identity):
                evidence["cleanup_confirmed"] = _cleanup_owned(
                    base, env, None, owner, container_name
                )
                raise _Failure("container_create_failed")
            container_id = identity
            evidence["container_id"] = container_id
            try:
                if _lifecycle is not None:
                    try:
                        _lifecycle.created(container_id)
                    except Exception:
                        raise _Failure("lifecycle_error") from None
                containers = _inspect_json(
                    _run([*base, "inspect", container_id], env, 10, 256 * 1024)
                )
                if (
                    not isinstance(containers, list)
                    or len(containers) != 1
                    or containers[0].get("Id") != container_id
                ):
                    raise _Failure("container_identity_mismatch")
                evidence["isolation"] = _isolation(
                    containers[0], profile, owner, removed_environment_names
                )
                payload = (
                    str(len(source)).encode()
                    + b"\n"
                    + source
                    + b"".join(case.input_json + b"\n" for case in profile.cases)
                )
                if _lifecycle is not None:
                    try:
                        _lifecycle.before_start()
                    except Exception:
                        raise _Failure("lifecycle_error") from None
                evidence["execution_started"] = True
                result = _run(
                    [*base, "start", "--attach", "--interactive", container_id],
                    env,
                    profile.timeout_seconds,
                    profile.output_bytes,
                    payload,
                )
                stopped = _inspect_json(_run([*base, "inspect", container_id], env, 5, 256 * 1024))
                if (
                    not isinstance(stopped, list)
                    or len(stopped) != 1
                    or stopped[0].get("Id") != container_id
                ):
                    raise _Failure("container_identity_mismatch")
                state = stopped[0].get("State", {})
                if (
                    state.get("Status") != "exited"
                    or state.get("Running") is not False
                    or state.get("Dead") is not False
                ):
                    raise _Failure("container_completion_unconfirmed")
                evidence["candidate_exit_code"] = state.get("ExitCode")
                evidence["container_state"] = {
                    "status": "exited",
                    "oom_killed": state.get("OOMKilled"),
                    "exit_code": state.get("ExitCode"),
                }
                evidence["stdout_sha256"] = _digest(result.stdout)
                evidence["stdout_bytes"] = len(result.stdout)
                evidence["stderr_bytes"] = result.stderr_bytes
                if state.get("OOMKilled") is not False:
                    raise _Failure("memory_limit", "failed")
                if result.returncode or state.get("ExitCode") != 0:
                    raise _Failure("candidate_exit", "failed")
                if not result.stdout.endswith(b"\n"):
                    raise _Failure("protocol_failure", "failed")
                lines = result.stdout.split(b"\n")[:-1]
                evidence["completed_case_count"] = len(lines)
                if len(lines) != len(profile.cases):
                    raise _Failure("protocol_failure", "failed")
                for line, case in zip(lines, profile.cases, strict=True):
                    try:
                        if not line.strip():
                            raise ValueError("blank line")
                        actual = _json(line)
                    except (ValueError, UnicodeError, RecursionError):
                        raise _Failure("protocol_failure", "failed") from None
                    evidence["checked_case_count"] += 1
                    if not _equal(actual, _json(case.expected_json)):
                        raise _Failure("case_mismatch", "failed")
                    evidence["passed_case_count"] += 1
                status = "passed"
            finally:
                # Inspect and bind both full ID and unguessable owner before
                # deleting. Never remove by broad label, name or caller input.
                evidence["cleanup_confirmed"] = _cleanup_owned(
                    base, env, container_id, owner, container_name
                )
                if not evidence["cleanup_confirmed"]:
                    evidence["errors"].append("cleanup_failed")
                    status = "error"
    except _Failure as exc:
        if exc.isolation_checks is not None:
            evidence["effective_isolation_checks"] = exc.isolation_checks
            evidence["effective_isolation_summary"] = exc.isolation_summary
        evidence["errors"].append(exc.code)
        status = "error" if "cleanup_failed" in evidence["errors"] else exc.status
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        evidence["errors"].append("infrastructure_error")
        status = "error"
    if not evidence["cleanup_confirmed"]:
        if "cleanup_failed" not in evidence["errors"]:
            evidence["errors"].append("cleanup_failed")
        status = "error"
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    evidence["elapsed_seconds"] = time.monotonic() - begin
    return VerificationResult(status, evidence)

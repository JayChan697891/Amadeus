"""Mocked policy tests only; these do not establish actual Docker isolation."""

import copy
import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

from agentsync.verification import docker

IMAGE = "sha256:" + "a" * 64
CID = "c" * 64
SOURCE = b"import sys; print(sys.stdin.readline())"
IDENTITY = {"input_sha256": "d" * 64, "commit_sha": "e" * 40, "tree_sha": "f" * 40}


def profile(**kwargs):
    return docker.DockerProfile(IMAGE, (docker.JsonCase({"x": 1}, {"y": 2}),), **kwargs)


@pytest.mark.parametrize(
    "image", ["python:3.12", "sha256:abc", "a" * 64, "sha256:" + "A" * 64, None]
)
def test_profile_rejects_nonimmutable_image(image):
    with pytest.raises(ValueError):
        docker.DockerProfile(image, (docker.JsonCase(1, 2),))


@pytest.mark.parametrize(
    "settings",
    [
        {"timeout_seconds": 11},
        {"timeout_seconds": True},
        {"timeout_seconds": float("nan")},
        {"output_bytes": 65_537},
        {"output_bytes": 0},
        {"profile_id": "candidate-script"},
    ],
)
def test_profile_limits_are_fixed_and_bounded(settings):
    with pytest.raises(ValueError):
        profile(**settings)


def test_cases_and_profile_are_frozen_and_digest_covers_owner_expectations():
    original = {"items": [1]}
    case = docker.JsonCase(original, [2])
    frozen = docker.DockerProfile(IMAGE, (case,))
    digest = frozen.sha256
    original["items"].append(2)
    assert case.input_json == b'{"items":[1]}'
    assert frozen.sha256 == digest
    assert docker.DockerProfile(IMAGE, (docker.JsonCase({"items": [1]}, [3]),)).sha256 != digest
    assert docker.DockerProfile(IMAGE, (case,), timeout_seconds=1).sha256 != digest
    with pytest.raises(FrozenInstanceError):
        frozen.image_id = "sha256:" + "b" * 64
    with pytest.raises(ValueError):
        docker.DockerProfile(IMAGE, [case])


@pytest.mark.parametrize(
    "raw",
    [b'{"a":1,"a":2}', b"NaN", b"Infinity", b"1e10000", b'"\xff"', b"[" * 34 + b"0" + b"]" * 34],
)
def test_strict_json_rejects_duplicate_nonfinite_encoding_and_depth(raw):
    with pytest.raises((ValueError, UnicodeError)):
        docker._json(raw)


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), {1: "nonstring"}, object(), "x" * 65536],
    ids=["nan", "infinity", "key", "object", "size"],
)
def test_owner_cases_have_same_strict_value_bounds(value):
    with pytest.raises((ValueError, TypeError)):
        docker.JsonCase(value, 1)


@pytest.mark.parametrize(
    ("left", "right", "equal"),
    [
        (True, 1, False),
        (False, 0.0, False),
        ([True], [1], False),
        ({"x": True}, {"x": 1}, False),
        (1, 1.0, True),
        ({"a": 1, "b": [2]}, {"b": [2.0], "a": 1}, True),
        ([1, 2], [2, 1], False),
    ],
)
def test_structural_comparison_is_typed_with_numeric_equivalence(left, right, equal):
    assert docker._equal(left, right) is equal


@pytest.fixture
def policy_daemon(monkeypatch):
    """Simulated daemon metadata. No candidate or Docker process is executed."""
    state = {
        "stdout": b'{"y":2}\n',
        "exit": 0,
        "calls": [],
        "mutate": None,
        "failure": None,
        "cleanup_owner": True,
        "rm_exit": 0,
        "create_failure": None,
        "create_stdout": CID.encode() + b"\n",
        "recover_identity": CID,
        "recover_name": True,
    }
    monkeypatch.setattr(docker, "_trusted_cli", lambda: "/usr/bin/docker")

    def run(command, env, timeout, limit, payload=b""):
        state["calls"].append((command.copy(), env.copy(), timeout, limit, payload))
        args = command[5:]
        operation = args[0]
        if operation == "info":
            value = {
                "OSType": "linux",
                "SecurityOptions": ["name=seccomp,profile=builtin"],
                "MemoryLimit": True,
                "SwapLimit": True,
                "CpuCfsQuota": True,
                "PidsLimit": True,
                "ServerVersion": "test-policy-mock",
                "CgroupVersion": "2",
            }
        elif operation == "image":
            value = [
                {"Id": IMAGE, "Os": "linux", "Config": {"Env": ["LANG=C.UTF-8"], "Volumes": None}}
            ]
        elif operation == "create":
            state["owner"] = next(
                arg.split("=", 2)[2] for arg in args if arg.startswith("--label=")
            )
            state["name"] = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--name="))
            if state["create_failure"]:
                raise docker._Failure(state["create_failure"], "failed")
            return docker._Process(0, state["create_stdout"], 0)
        elif operation == "inspect":
            value = [
                {
                    "Id": state["recover_identity"],
                    "Name": "/" + state["name"] if state["recover_name"] else "/another-container",
                    "Image": IMAGE,
                    "State": {
                        "Status": "exited",
                        "Running": False,
                        "Dead": False,
                        "ExitCode": state["exit"],
                        "OOMKilled": False,
                    },
                    "Config": {
                        "Labels": {
                            docker.LABEL: state["owner"] if state["cleanup_owner"] else "other"
                        },
                        "User": "65534:65534",
                        "Env": [f"{k}={v}" for k, v in docker.RUNTIME_ENV.items()],
                        "Entrypoint": ["/usr/local/bin/python3"],
                        "Cmd": ["-I", "-u", "-c", docker.BOOTSTRAP],
                        "WorkingDir": "/tmp",
                        "Healthcheck": {"Test": ["NONE"]},
                    },
                    "Mounts": [],
                    "HostConfig": {
                        "NetworkMode": "none",
                        "ReadonlyRootfs": True,
                        "Privileged": False,
                        "CapDrop": ["ALL"],
                        "SecurityOpt": ["no-new-privileges"],
                        "IpcMode": "private",
                        "CgroupnsMode": "private",
                        "Memory": docker.MEMORY,
                        "MemorySwap": docker.MEMORY,
                        "NanoCpus": docker.NANO_CPUS,
                        "PidsLimit": docker.PIDS,
                        "Tmpfs": {"/tmp": f"rw,noexec,nosuid,nodev,size={docker.TMPFS},mode=1777"},
                        "LogConfig": {"Type": "none"},
                    },
                }
            ]
        elif operation == "start":
            if state["failure"]:
                raise docker._Failure(state["failure"], "failed")
            return docker._Process(state["exit"], state["stdout"], 0)
        elif operation == "rm":
            return docker._Process(state["rm_exit"], CID.encode() + b"\n", 0)
        else:
            raise AssertionError(operation)
        if state["mutate"]:
            value = state["mutate"](operation, copy.deepcopy(value))
        return docker._Process(0, json.dumps(value).encode(), 0)

    monkeypatch.setattr(docker, "_run", run)
    return state


def verify(**kwargs):
    return docker.verify_python_json_lines(
        SOURCE, profile=profile(), **IDENTITY, **kwargs
    ).as_dict()


def test_mocked_policy_success_requires_comparison_and_excludes_raw_evidence(
    policy_daemon, monkeypatch
):
    for name in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "OPENAI_API_KEY",
        "SSH_AUTH_SOCK",
    ):
        monkeypatch.setenv(name, "private-sentinel")
    result = verify()
    assert result["status"] == "passed"
    assert result["checked_case_count"] == result["passed_case_count"] == 1
    assert result["constraints_verified"] and result["cleanup_confirmed"]
    assert result["execution_started"]
    assert len(result["verifier_source_sha256"]) == 64
    assert result["source_sha256"] == docker._digest(SOURCE)
    assert result["source_sha256"] != result["input_sha256"]
    assert "private-sentinel" not in json.dumps(result)
    for command, env, _, _, payload in policy_daemon["calls"]:
        assert set(env) == {"PATH", "HOME", "LC_ALL"}
        assert command[:3] == ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
        assert "private-sentinel" not in json.dumps(env)
        assert not any(
            arg.startswith(("--mount", "--volume", "--privileged", "--device")) for arg in command
        )
        if command[5] == "start":
            assert payload == str(len(SOURCE)).encode() + b"\n" + SOURCE + b'{"x":1}\n'
            assert b'{"y":2}' not in payload
    creates = [call[0] for call in policy_daemon["calls"] if call[0][5] == "create"]
    assert "--pull=never" in creates[0] and "--network=none" in creates[0]
    assert "--cgroupns=private" in creates[0]
    removes = [call[0] for call in policy_daemon["calls"] if call[0][5] == "rm"]
    assert removes[0][-2:] == ["--force", CID]


@pytest.mark.parametrize(
    "output",
    [
        b"",
        b"<testsuite failures='0'/>\n",
        b"true\n",
        b'{"y":2}',
        b'{"y":2}\n\n',
        b'{"y":2}\n{}\n',
        b'{"y":2,"y":2}\n',
        b'{"y":NaN}\n',
        b'"\xff"\n',
    ],
)
def test_empty_forged_extra_invalid_and_wrong_output_cannot_pass(policy_daemon, output):
    policy_daemon["stdout"] = output
    result = verify()
    assert result["status"] == "failed"
    assert result["error_code"] in {"protocol_failure", "case_mismatch"}
    assert result["cleanup_confirmed"]


@pytest.mark.parametrize("failure", ["timeout", "stdout_limit", "stderr_limit"])
def test_runtime_limits_fail_and_remove_exact_owned_container(policy_daemon, failure):
    policy_daemon["failure"] = failure
    result = verify()
    assert result["status"] == "failed" and result["error_code"] == failure
    assert result["cleanup_confirmed"]
    assert policy_daemon["calls"][-1][0][-3:] == ["rm", "--force", CID]


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("Running", True, "container_completion_unconfirmed"),
        ("Status", "running", "container_completion_unconfirmed"),
        ("ExitCode", 7, "candidate_exit"),
        ("OOMKilled", True, "memory_limit"),
    ],
)
def test_cli_zero_is_insufficient_without_confirmed_container_exit(
    policy_daemon, field, value, code
):
    def mutate(operation, result):
        if operation == "inspect":
            result[0]["State"][field] = value
        return result

    policy_daemon["mutate"] = mutate
    result = verify()
    assert result["status"] != "passed"
    assert result["error_code"] == code
    assert result["cleanup_confirmed"]


@pytest.mark.parametrize("change", ["owner", "remove"])
def test_cleanup_failure_invalidates_success_and_never_deletes_unowned(policy_daemon, change):
    if change == "owner":
        policy_daemon["cleanup_owner"] = False
    else:
        policy_daemon["rm_exit"] = 1
    result = verify()
    assert result["status"] == "error" and not result["cleanup_confirmed"]
    assert "cleanup_failed" in result["errors"]
    if change == "owner":
        assert not any(call[0][5] == "rm" for call in policy_daemon["calls"])


@pytest.mark.parametrize("failure", ["timeout", "stdout_limit", "docker_unavailable"])
def test_lost_create_response_recovers_only_exact_generated_name_and_full_id(
    policy_daemon, failure
):
    policy_daemon["create_failure"] = failure
    result = verify()
    assert result["status"] == "error" and result["error_code"] == "container_create_failed"
    assert result["cleanup_confirmed"]
    assert not any(call[0][5] == "start" for call in policy_daemon["calls"])
    inspection = [call[0] for call in policy_daemon["calls"] if call[0][5] == "inspect"]
    assert inspection[0][-1] == policy_daemon["name"]
    assert inspection[0][-1].startswith("agentsync-verifier-")
    assert len(inspection[0][-1].removeprefix("agentsync-verifier-")) == 32
    assert policy_daemon["calls"][-1][0][-3:] == ["rm", "--force", CID]


@pytest.mark.parametrize("reply", [b"", b"short-id\n", b"untrusted error text\n"])
def test_missing_create_full_id_uses_exact_name_for_recovery(policy_daemon, reply):
    policy_daemon["create_stdout"] = reply
    result = verify()
    assert result["status"] == "error" and result["cleanup_confirmed"]
    assert result["error_code"] == "container_create_failed"
    assert policy_daemon["calls"][-1][0][-1] == CID
    assert reply.decode().strip() not in json.dumps(result) if reply.strip() else True


@pytest.mark.parametrize("mismatch", ["label", "name", "identity", "remove"])
def test_lost_create_response_cannot_claim_cleanup_without_matching_owned_full_id(
    policy_daemon, mismatch
):
    policy_daemon["create_failure"] = "timeout"
    if mismatch == "label":
        policy_daemon["cleanup_owner"] = False
    elif mismatch == "name":
        policy_daemon["recover_name"] = False
    elif mismatch == "identity":
        policy_daemon["recover_identity"] = "short-id"
    else:
        policy_daemon["rm_exit"] = 1
    result = verify()
    assert result["status"] == "error" and not result["cleanup_confirmed"]
    assert set(result["errors"]) == {"container_create_failed", "cleanup_failed"}
    if mismatch != "remove":
        assert not any(call[0][5] == "rm" for call in policy_daemon["calls"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("Privileged", True),
        ("CgroupnsMode", "host"),
        ("ReadonlyRootfs", False),
        ("NetworkMode", "host"),
        ("MemorySwap", -1),
        ("PidsLimit", 0),
        ("NanoCpus", 0),
        ("Binds", ["/tmp:/host"]),
        ("SecurityOpt", ["seccomp=unconfined"]),
        ("GroupAdd", ["0"]),
    ],
)
def test_effective_isolation_mismatch_rejects_before_start(policy_daemon, field, value):
    def mutate(operation, result):
        if operation == "inspect":
            result[0]["HostConfig"][field] = value
        return result

    policy_daemon["mutate"] = mutate
    result = verify()
    assert result["status"] == "unsupported" and result["error_code"] == "isolation_mismatch"
    assert result["cleanup_confirmed"]
    assert not any(call[0][5] == "start" for call in policy_daemon["calls"])


@pytest.mark.parametrize("change", ["seccomp", "memory", "cgroup_v1", "image", "volume", "secret"])
def test_daemon_and_image_preflight_fail_closed(policy_daemon, change):
    def mutate(operation, result):
        if operation == "info":
            if change == "seccomp":
                result["SecurityOptions"] = ["name=seccomp,profile=unconfined"]
            if change == "memory":
                result["MemoryLimit"] = False
            if change == "cgroup_v1":
                result["CgroupVersion"] = "1"
        if operation == "image":
            if change == "image":
                result[0]["Id"] = "sha256:" + "b" * 64
            if change == "volume":
                result[0]["Config"]["Volumes"] = {"/state": {}}
            if change == "secret":
                result[0]["Config"]["Env"].append("OPENAI_API_KEY=private-sentinel")
        return result

    policy_daemon["mutate"] = mutate
    result = verify()
    assert result["status"] == "unsupported"
    assert not any(call[0][5] == "create" for call in policy_daemon["calls"])
    assert "private-sentinel" not in json.dumps(result)


def test_nonlinux_never_starts_candidate_or_docker(monkeypatch):
    monkeypatch.setattr(docker.platform, "system", lambda: "Windows")
    monkeypatch.setattr(docker, "_run", lambda *args: pytest.fail("executed Docker"))
    result = verify()
    assert result["status"] == "unsupported" and result["error_code"] == "unsupported_platform"
    assert not result["execution_started"]


def test_large_profile_digest_does_not_apply_per_value_limit_to_all_cases():
    cases = tuple(docker.JsonCase(i, "x" * 2000) for i in range(40))
    assert len(docker.DockerProfile(IMAGE, cases).sha256) == 64


@pytest.mark.parametrize(
    "source", [b"", b"x" * (docker.MAX_SOURCE + 1), b"\xff"], ids=["empty", "size", "encoding"]
)
def test_invalid_source_is_rejected_before_any_execution(monkeypatch, source):
    monkeypatch.setattr(docker, "_trusted_cli", lambda: pytest.fail("candidate reached backend"))
    result = docker.verify_python_json_lines(source, profile=profile(), **IDENTITY).as_dict()
    assert result["status"] == "failed" and result["cleanup_confirmed"]


@pytest.mark.parametrize(
    "path",
    [
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    ],
)
def test_official_python_public_environment_is_accepted_then_scrubbed(path):
    config = {
        "Env": [
            f"PATH={path}",
            "LANG=C.UTF-8",
            "PYTHON_VERSION=3.12.13",
            "PYTHON_SHA256=" + "a" * 64,
            "GPG_KEY=" + "A" * 40,
        ]
    }
    assert docker._image_environment(config) == [
        "PATH",
        "LANG",
        "PYTHON_VERSION",
        "PYTHON_SHA256",
        "GPG_KEY",
    ]


@pytest.mark.parametrize(
    "value",
    ["PATH=/tmp:/usr/bin", "LANG=private-secret", "PYTHON_VERSION=secret", "GPG_KEY=private-key"],
)
def test_known_image_environment_names_cannot_hide_arbitrary_values(value):
    with pytest.raises(docker._Failure) as failure:
        docker._image_environment({"Env": [value]})
    assert failure.value.code == "unsafe_image_environment"


@pytest.mark.parametrize("mode", ["stdout", "stderr", "timeout"])
def test_process_runner_bounds_real_trusted_probe_without_candidate_execution(mode):
    # This is the trusted host capture utility only, not a candidate or sandbox test.
    if mode == "timeout":
        probe = "import time; time.sleep(5)"
        expected = "timeout"
    else:
        probe = f"import sys; sys.{mode}.write('x'*4096); sys.{mode}.flush()"
        expected = mode + "_limit"
    with pytest.raises(docker._Failure) as failure:
        docker._run(
            [sys.executable, "-c", probe], dict(os.environ), 0.5 if mode == "timeout" else 5, 128
        )
    assert failure.value.code == expected

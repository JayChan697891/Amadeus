"""Actual Linux Docker evidence, deliberately separate from mock policy tests."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from agentsync.verification.docker import DockerProfile, JsonCase, verify_python_json_lines
from agentsync.verification.snapshot import export_candidate
from agentsync.workspaces.git import GitWorkspaceStore


@pytest.fixture
def real_image():
    image = os.environ.get("AGENTSYNC_DOCKER_TEST_IMAGE")
    if not image:
        if os.environ.get("AGENTSYNC_REQUIRE_DOCKER_TESTS") == "1":
            pytest.fail("Required real Docker evidence has no preloaded image ID")
        pytest.skip("Real Linux Docker/image not configured; policy tests are a separate tier")
    assert sys.platform == "linux", "Real isolation gate requires a Linux host"
    return image


@pytest.fixture
def host_canary():
    # The parent must be traversable: EACCES under /root is not proof that an
    # otherwise-readable host path is absent from the container namespace.
    if sys.platform != "linux":
        pytest.skip("The actual host-canary probe requires Linux Docker")
    with tempfile.NamedTemporaryFile(prefix="agentsync-canary-", dir="/tmp") as stream:
        stream.write(b"isolated synthetic fixture")
        stream.flush()
        yield Path(stream.name)


def candidate(tmp_path, source):
    """Commit only disposable data; candidate source is never imported on the host."""
    root = tmp_path / ("repository-" + uuid4().hex)
    root.mkdir()
    (root / "solution.py").write_bytes(source)
    executable = shutil.which("git")
    assert executable, "Actual Git is required"
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    for args in (("init",), ("add", "."), ("commit", "-m", "disposable verifier input")):
        subprocess.run(
            [
                executable,
                "-c",
                "gc.auto=0",
                "-c",
                "maintenance.auto=false",
                "-c",
                "core.hooksPath=" + os.devnull,
                "-c",
                "user.name=Verifier fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-C",
                str(root),
                *args,
            ],
            env=env,
            check=True,
            capture_output=True,
            timeout=30,
        )
    store = GitWorkspaceStore(tmp_path / ("managed-" + uuid4().hex))
    receipt = store.capture_repository(root, str(uuid4()))
    return export_candidate(store, receipt, receipt["base_sha"])


def execute_case(tmp_path, request, source, profile):
    snapshot = candidate(tmp_path, source)
    result = verify_python_json_lines(
        snapshot.source,
        profile=profile,
        input_sha256=snapshot.input_sha256,
        commit_sha=snapshot.commit_sha,
        tree_sha=snapshot.tree_sha,
    ).as_dict()
    evidence = os.environ.get("AGENTSYNC_VERIFIER_EVIDENCE_DIR")
    if evidence:
        environment_id = hashlib.sha256(sys.prefix.encode("utf-8")).hexdigest()[:16]
        # Source, installed wheel and sdist use different interpreters. Preserve
        # each environment's real observations instead of overwriting one file.
        directory = Path(evidence) / environment_id
        result["test_environment_id"] = environment_id
        result["test_python_version"] = sys.version.split()[0]
        assert directory.is_absolute()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (request.node.name + ".json")).write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    assert result["source_sha256"] == hashlib.sha256(source).hexdigest()
    assert result["input_sha256"] == snapshot.input_sha256
    assert result["image_id"] == profile.image_id
    assert result["cleanup_confirmed"], result
    return result


def test_actual_docker_checks_all_external_cases(tmp_path, request, real_image):
    profile = DockerProfile(
        image_id=real_image,
        cases=(
            JsonCase({"values": [1, 2, 3]}, {"sum": 6}),
            JsonCase({"values": [-4, 1]}, {"sum": -3}),
        ),
    )
    source = b"import sys,json\nfor line in sys.stdin:\n x=json.loads(line); print(json.dumps({'sum':sum(x['values'])}),flush=True)\n"
    result = execute_case(tmp_path, request, source, profile)
    assert result["status"] == "passed", result
    assert result["checked_case_count"] == result["passed_case_count"] == 2
    assert result["constraints_verified"], result


@pytest.mark.parametrize(
    "source",
    [
        b"import os; os._exit(0)",
        b'print(\'<testsuites tests="100" failures="0"/>\')',
        b"print('false')",
        b"print('1')",
        b"print('true'); print('true')",
    ],
    ids=["early-exit", "forged-junit", "wrong-result", "bool-not-int", "extra-output"],
)
def test_actual_docker_rejects_self_reported_or_incomplete_success(
    tmp_path, request, real_image, source
):
    result = execute_case(
        tmp_path, request, source, DockerProfile(image_id=real_image, cases=(JsonCase(None, True),))
    )
    assert result["status"] == "failed", result
    assert result["error_code"] in {"protocol_failure", "case_mismatch"}, result


def test_actual_docker_isolation_controls(tmp_path, request, real_image, monkeypatch, host_canary):
    canary = host_canary
    monkeypatch.setenv("AGENTSYNC_SYNTHETIC_SECRET", "must-never-enter-container")
    source = b"""import json,os,pathlib,socket,sys
request=json.loads(next(sys.stdin))
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines())
root_mounts=[line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines() if line.split()[4]=='/']
root_is_ro=len(root_mounts)==1 and 'ro' in root_mounts[0][5].split(',')
no_default_route=all(line.split()[1]!='00000000' for line in pathlib.Path('/proc/net/route').read_text().splitlines()[1:])
try:
 pathlib.Path('/root-write-probe').write_text('forbidden')
 readonly=False
except OSError:
 readonly=True
try:
 socket.create_connection(('198.51.100.1',443),timeout=.3).close()
 no_network=False
except OSError:
 no_network=True
print(json.dumps({'nonroot':os.getuid()!=0,'no_caps':int(status['CapEff'].strip(),16)==0,
 'no_new_privileges':status['NoNewPrivs'].strip()=='1','seccomp':status['Seccomp'].strip()=='2',
 'readonly':readonly and root_is_ro,'no_network':no_network and no_default_route and {name for _,name in socket.if_nameindex()}=={'lo'},'no_host_canary':not pathlib.Path(request['canary']).exists(),
 'no_socket':not pathlib.Path('/var/run/docker.sock').exists(),
 'no_secret':'AGENTSYNC_SYNTHETIC_SECRET' not in os.environ,
 'no_image_metadata_env':all(name not in os.environ for name in ('GPG_KEY','PYTHON_VERSION','PYTHON_SHA256'))}),flush=True)
"""
    expected = dict.fromkeys(
        [
            "nonroot",
            "no_caps",
            "no_new_privileges",
            "seccomp",
            "readonly",
            "no_network",
            "no_host_canary",
            "no_socket",
            "no_secret",
            "no_image_metadata_env",
        ],
        True,
    )
    profile = DockerProfile(
        image_id=real_image, cases=(JsonCase({"canary": str(canary)}, expected),)
    )
    assert execute_case(tmp_path, request, source, profile)["status"] == "passed"
    assert canary.read_text(encoding="utf-8") == "isolated synthetic fixture"


def test_actual_docker_enforces_wall_time(tmp_path, request, real_image):
    result = execute_case(
        tmp_path,
        request,
        b"import time; time.sleep(30)",
        DockerProfile(image_id=real_image, cases=(JsonCase(None, None),), timeout_seconds=1),
    )
    assert result["status"] == "failed", result
    assert result["error_code"] == "timeout", result


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_actual_docker_enforces_output_bounds(tmp_path, request, real_image, stream):
    source = (
        f"import sys\nwhile True: sys.{stream}.write('x'*8192); sys.{stream}.flush()\n".encode()
    )
    result = execute_case(
        tmp_path, request, source, DockerProfile(image_id=real_image, cases=(JsonCase(None, None),))
    )
    assert result["status"] == "failed", result
    assert result["error_code"] == stream + "_limit", result


def test_actual_docker_enforces_memory_bound(tmp_path, request, real_image):
    source = b"x=bytearray(512*1024*1024); print('null',flush=True)"
    result = execute_case(
        tmp_path, request, source, DockerProfile(image_id=real_image, cases=(JsonCase(None, None),))
    )
    assert result["status"] == "failed", result
    assert result["error_code"] in {"candidate_exit", "memory_limit"}, result


def test_actual_docker_enforces_scratch_bound(tmp_path, request, real_image):
    source = b"""import errno,json
try:
 with open('/tmp/limited-scratch','wb') as f:
  for _ in range(20): f.write(b'x'*(1024*1024))
 limited=False
except OSError as exc:
 limited=exc.errno==errno.ENOSPC
print(json.dumps(limited),flush=True)
"""
    result = execute_case(
        tmp_path, request, source, DockerProfile(image_id=real_image, cases=(JsonCase(None, True),))
    )
    assert result["status"] == "passed", result


def test_actual_docker_enforces_pid_bound(tmp_path, request, real_image):
    source = b"""import errno,json,os,time
children=[]
try:
 for _ in range(80):
  pid=os.fork()
  if pid==0:
   time.sleep(3); os._exit(0)
  children.append(pid)
 limited=False
except OSError as exc:
 limited=exc.errno==errno.EAGAIN and len(children)<=31
finally:
 for pid in children:
  os.kill(pid,9); os.waitpid(pid,0)
print(json.dumps(limited),flush=True)
"""
    result = execute_case(
        tmp_path, request, source, DockerProfile(image_id=real_image, cases=(JsonCase(None, True),))
    )
    assert result["status"] == "passed", result


def test_actual_docker_kernel_cgroup_limits(tmp_path, request, real_image):
    source = b"""import json,pathlib
root=pathlib.Path('/sys/fs/cgroup')
quota,period=(root/'cpu.max').read_text().split()
print(json.dumps({'cpu_limited':quota!='max' and int(quota)==int(period),
 'memory':int((root/'memory.max').read_text()),
 'swap':int((root/'memory.swap.max').read_text()),
 'pids':int((root/'pids.max').read_text())}),flush=True)
"""
    expected = {"cpu_limited": True, "memory": 128 * 1024 * 1024, "swap": 0, "pids": 32}
    result = execute_case(
        tmp_path,
        request,
        source,
        DockerProfile(image_id=real_image, cases=(JsonCase(None, expected),)),
    )
    assert result["status"] == "passed", result

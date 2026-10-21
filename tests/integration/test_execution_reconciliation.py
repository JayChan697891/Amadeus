"""Actual local Docker cleanup after an injected hard process exit.

Lease expiry is injected only into disposable test data to avoid a 300s wait.
No Docker response or reconciliation result is mocked. These are not client relay
or automatic crash recovery tests.
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.executor import OwnerVerificationExecutor
from agentsync.verification.jobs import VerificationJobs
from agentsync.verification.reconciliation import OwnerExecutionReconciler
from agentsync.workspaces.git import GitWorkspaceStore

CHILD = r"""
import json, os, sys
from agentsync.core.service import Core
from agentsync.verification import executor
from agentsync.verification.docker import DockerProfile, JsonCase
p=json.load(sys.stdin)
if p['mode'] != 'running':
    created=executor._Lifecycle.created
    def crash(self, cid):
        if p['mode'] != 'lost_ack':
            created(self, cid)
        os._exit(86)
    executor._Lifecycle.created=crash
profile=DockerProfile(p['image'], (JsonCase(None, True),), timeout_seconds=10)
executor.OwnerVerificationExecutor(Core(p['data_dir'])).execute_once(
    project_id=p['project_id'],admin_token=p['admin_token'],job_id=p['job_id'],
    expected_version=p['version'],profile=profile)
"""


def docker(*args):
    return subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", *args],
        capture_output=True,
        timeout=15,
        check=False,
    )


def execution_row(core, owner, job):
    with connect(core.db_path) as db:
        row = db.execute(
            "SELECT * FROM verification_executions WHERE project_id=? AND job_id=?",
            (owner["project_id"], job["id"]),
        ).fetchone()
        return dict(row) if row else None


@pytest.fixture
def crashed_execution(tmp_path, request):
    image = os.environ.get("AGENTSYNC_DOCKER_TEST_IMAGE")
    if not image:
        if os.environ.get("AGENTSYNC_REQUIRE_DOCKER_TESTS") == "1":
            pytest.fail("Required real reconciliation has no pinned Docker image")
        pytest.skip("Actual reconciliation requires an explicitly configured local Linux image")
    assert sys.platform == "linux"
    mode = getattr(request, "param", "created")
    root = tmp_path / "disposable-repository"
    root.mkdir()
    core = Core(tmp_path / "service")
    store = GitWorkspaceStore(core.data_dir)
    store._git(root, "init", "--initial-branch=fixture-main")
    (root / "solution.py").write_text("import time; time.sleep(60)\n", encoding="utf-8")
    store._git(root, "add", ".")
    store._git(root, "commit", "-m", "disposable crash fixture")
    owner = core.execute("create_project", {"name": "crash fixture", "root_path": str(root)})
    actor = core.execute("register_agent", {**owner, "name": "snapshot fixture"})
    core.execute_owner(
        "set_agent_roles",
        {
            **owner,
            "agent_id": actor["agent_id"],
            "roles": ["worker"],
            "expected_version": 1,
            "request_id": "grant",
        },
    )
    snapshot = core.execute(
        "capture_repository",
        {
            "project_id": owner["project_id"],
            "session_id": actor["session_id"],
            "session_token": actor["session_token"],
            "request_id": "capture",
        },
    )
    profile = DockerProfile(image, (JsonCase(None, True),), timeout_seconds=10)
    job = VerificationJobs(core).enqueue(
        **owner,
        snapshot_id=snapshot["snapshot_id"],
        expected_commit=snapshot["base_sha"],
        profile=profile,
        request_id="enqueue",
    )
    payload = {
        **owner,
        "job_id": job["id"],
        "version": job["version"],
        "data_dir": str(core.data_dir),
        "image": image,
        "mode": mode,
    }
    # Auth stays on a private stdin pipe, never command arguments or test logs.
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    assert child.stdin is not None
    child.stdin.write(json.dumps(payload).encode())
    child.stdin.close()
    actual_id = None
    observed_running = False
    row = None
    try:
        if mode == "running":
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                row = execution_row(core, owner, job)
                if row and row["container_id"]:
                    state = docker("inspect", "--format", "{{.State.Running}}", row["container_id"])
                    if state.returncode == 0 and state.stdout.strip() == b"true":
                        observed_running = True
                        break
                if child.poll() is not None:
                    break
                time.sleep(0.05)
            assert observed_running, "Disposable execution never reached actual running state"
            os.killpg(child.pid, signal.SIGKILL)
            assert child.wait(timeout=10) == -signal.SIGKILL
        else:
            assert child.wait(timeout=40) == 86, (
                "Hard-exit tracer did not reach the create boundary"
            )
        row = execution_row(core, owner, job)
        assert row and row["create_intent"] == 1
        # For lost ACK, the fixture knows its private generated name; the product
        # reconciler still has no full ID authority and must not use that name.
        found = docker("inspect", "--format", "{{.Id}}", row["container_name"])
        assert found.returncode == 0
        actual_id = found.stdout.decode().strip()
        assert len(actual_id) == 64
        if mode != "lost_ack":
            assert row["create_reply_complete"] == 1 and row["container_id"] == actual_id
        with connect(core.db_path) as db:
            db.execute(
                "UPDATE verification_attempts SET lease_expires_at=? WHERE project_id=? AND job_id=?",
                (time.time() - 1, owner["project_id"], job["id"]),
            )
        # Reopen the actual service DB after the executor process has died.
        restarted = Core(core.data_dir)
        yield restarted, owner, job, actual_id, row, observed_running
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=10)
        # Fixture safety net is restricted to its own exact matching identity.
        if actual_id is None:
            row = execution_row(core, owner, job)
            if row and row["container_name"]:
                found = docker("inspect", "--format", "{{.Id}}", row["container_name"])
                if found.returncode == 0:
                    actual_id = found.stdout.decode().strip()
        if actual_id and row:
            found = docker("inspect", actual_id)
            if found.returncode == 0:
                item = json.loads(found.stdout)[0]
                assert item["Id"] == actual_id and item["Name"] == "/" + row["container_name"]
                assert (
                    item["Config"]["Labels"]["org.agentsync.verifier.owner"] == row["owner_nonce"]
                )
                assert docker("rm", "--force", actual_id).returncode == 0


def save(core, owner, job, actual_id, original, running, result, name):
    evidence = os.environ.get("AGENTSYNC_RECONCILIATION_EVIDENCE_DIR")
    if not evidence:
        return
    env_id = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
    directory = Path(evidence) / env_id
    assert directory.is_absolute()
    directory.mkdir(parents=True, exist_ok=True)
    current = OwnerVerificationExecutor(core).get(**owner, job_id=job["id"])
    assert current["assessment"] == "unverified" and not current["cleanup_confirmed"]
    data = {
        "test_environment_id": env_id,
        "container_id": actual_id,
        "injected_process_termination": True,
        "injected_fixture_lease_expiry": True,
        "actual_running_observed_before_kill": running,
        "original_binding": {
            key: original[key]
            for key in ("image_id", "container_id", "create_reply_complete", "result_sha256")
        },
        "execution": current,
        "reconciliation": result,
    }
    with connect(core.db_path) as db:
        row = db.execute(
            "SELECT * FROM verification_reconciliations WHERE project_id=? AND job_id=?",
            (owner["project_id"], job["id"]),
        ).fetchone()
        if row:
            observation = json.loads(row["observation_json"])
            assert (
                hashlib.sha256(row["observation_json"].encode()).hexdigest()
                == row["observation_sha256"]
            )
            data["receipt_binding"] = {
                key: row[key]
                for key in (
                    "id",
                    "execution_id",
                    "attempt_id",
                    "claimed_job_version",
                    "claimed_execution_revision",
                    "observation_sha256",
                )
            }
            data["observation"] = observation
        else:
            data["receipt_binding"] = None
            data["observation"] = None
    (directory / (name + ".json")).write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.mark.parametrize("crashed_execution", ["created", "running"], indirect=True)
def test_actual_hard_exit_then_explicit_cleanup_never_restores_success(crashed_execution):
    core, owner, job, actual_id, original, running = crashed_execution
    service = OwnerExecutionReconciler(core)
    current = OwnerVerificationExecutor(core).get(**owner, job_id=job["id"])
    args = {
        **owner,
        "job_id": job["id"],
        "expected_version": current["version"],
        "request_id": "cleanup",
    }
    result = service.reconcile_once(**args)
    assert result["reconciliation"]["outcome"] == "removed_and_absent", result
    assert result["assessment"] == "unverified" and result["status"] == "cleanup_pending"
    assert not result["cleanup_confirmed"]
    absent = docker(
        "container",
        "ls",
        "--all",
        "--no-trunc",
        "--filter",
        "id=" + actual_id,
        "--format",
        "{{.ID}}",
    )
    assert absent.returncode == 0 and absent.stdout.strip() == b""
    assert service.reconcile_once(**args) == result
    assert service.get(**owner, job_id=job["id"]) == result
    save(
        core,
        owner,
        job,
        actual_id,
        original,
        running,
        result,
        "hard-exit-running" if running else "hard-exit-created",
    )


def test_actual_initial_absence_is_not_claimed_as_proven_cleanup(crashed_execution):
    core, owner, job, actual_id, original, running = crashed_execution
    # The fixture, rather than the reconciler, removes this object first.
    removed = docker("rm", "--force", actual_id)
    assert removed.returncode == 0 and removed.stdout.decode().strip() == actual_id
    service = OwnerExecutionReconciler(core)
    current = service.get(**owner, job_id=job["id"])
    result = service.reconcile_once(
        **owner, job_id=job["id"], expected_version=current["version"], request_id="absent"
    )
    assert result["reconciliation"]["outcome"] == "unresolved"
    assert result["reconciliation"]["error_code"]
    assert result["assessment"] == "unverified" and not result["cleanup_confirmed"]
    save(core, owner, job, actual_id, original, running, result, "initial-absence")


def test_actual_renamed_container_is_protected_from_cleanup(crashed_execution):
    core, owner, job, actual_id, original, running = crashed_execution
    protected_name = "agentsync-protected-" + actual_id[:24]
    assert docker("rename", actual_id, protected_name).returncode == 0
    try:
        service = OwnerExecutionReconciler(core)
        current = service.get(**owner, job_id=job["id"])
        result = service.reconcile_once(
            **owner, job_id=job["id"], expected_version=current["version"], request_id="protected"
        )
        assert result["reconciliation"]["outcome"] == "unresolved"
        assert result["reconciliation"]["error_code"] == "container_identity_mismatch"
        retained = docker("inspect", "--format", "{{.Name}}", actual_id)
        assert retained.returncode == 0 and retained.stdout.decode().strip() == "/" + protected_name
        save(core, owner, job, actual_id, original, running, result, "protected-renamed-object")
    finally:
        assert docker("rename", actual_id, original["container_name"]).returncode == 0


@pytest.mark.parametrize("crashed_execution", ["lost_ack"], indirect=True)
def test_actual_lost_create_ack_is_never_reconciled_by_name(crashed_execution):
    core, owner, job, actual_id, original, running = crashed_execution
    assert not original["create_reply_complete"] and original["container_id"] is None
    service = OwnerExecutionReconciler(core)
    current = service.get(**owner, job_id=job["id"])
    with pytest.raises(AgentSyncError) as error:
        service.reconcile_once(
            **owner, job_id=job["id"], expected_version=current["version"], request_id="unknown"
        )
    assert error.value.code == "reconciliation_identity_unavailable"
    result = service.get(**owner, job_id=job["id"])
    assert result["reconciliation"] is None and result["version"] == current["version"]
    retained = docker("inspect", "--format", "{{.Id}}", actual_id)
    assert retained.returncode == 0 and retained.stdout.decode().strip() == actual_id
    save(core, owner, job, actual_id, original, running, result, "lost-create-ack")

"""Actual owner job execution against isolated Git and Linux Docker, no fake backend."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification import executor as executor_module
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.executor import OwnerVerificationExecutor
from agentsync.verification.jobs import VerificationJobs
from agentsync.workspaces.git import GitWorkspaceStore

SOURCE = b"import json,sys\nfor line in sys.stdin:\n x=json.loads(line); print(json.dumps({'sum':sum(x)}),flush=True)\n"


@pytest.fixture
def owner_case(tmp_path, request):
    specification = getattr(request, "param", {})
    image = os.environ.get("AGENTSYNC_DOCKER_TEST_IMAGE")
    if not image:
        if os.environ.get("AGENTSYNC_REQUIRE_DOCKER_TESTS") == "1":
            pytest.fail("Required real owner execution has no pinned image")
        pytest.skip(
            "Actual owner execution requires an explicitly configured local Linux Docker image"
        )
    assert sys.platform == "linux"
    root = tmp_path / "disposable-project"
    root.mkdir()
    core = Core(tmp_path / "service")
    store = GitWorkspaceStore(core.data_dir)
    for args in (("init", "--initial-branch=fixture-main"),):
        store._git(root, *args)
    (root / "solution.py").write_bytes(specification.get("source", SOURCE))
    store._git(root, "add", ".")
    store._git(root, "commit", "-m", "isolated owner execution fixture")
    owner = core.execute(
        "create_project", {"name": "isolated owner execution", "root_path": str(root)}
    )
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
    auth = {
        "project_id": owner["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    snapshot = core.execute("capture_repository", {**auth, "request_id": "capture"})
    profile = DockerProfile(
        image_id=image,
        timeout_seconds=specification.get("timeout_seconds", 5),
        cases=(JsonCase([1, 2, 3], {"sum": 6}), JsonCase([-4, 1], {"sum": -3})),
    )
    ledger = VerificationJobs(core)
    job = ledger.enqueue(
        **owner,
        snapshot_id=snapshot["snapshot_id"],
        expected_commit=snapshot["base_sha"],
        profile=profile,
        request_id="enqueue",
    )
    return core, owner, root, snapshot, profile, ledger, job, OwnerVerificationExecutor(core)


def test_actual_owner_executes_fixed_snapshot_and_persists_independent_result(owner_case):
    core, owner, root, snapshot, profile, ledger, job, executor = owner_case
    # A dirty checkout cannot replace bytes in the pinned managed snapshot.
    (root / "solution.py").write_text(
        "raise RuntimeError('uncommitted-host-source-must-not-run')\n", encoding="utf-8"
    )
    result = executor.execute_once(
        **owner, job_id=job["id"], expected_version=job["version"], profile=profile
    )
    assert result["assessment"] == "passed", result
    assert result["phase"] == "finished" and result["execution_started"] is True
    assert result["cleanup_confirmed"] is True
    assert executor.get(**owner, job_id=job["id"])["assessment"] == "passed"
    assert ledger.get(**owner, job_id=job["id"])["execution_connected"] is True
    with connect(core.db_path) as db:
        row = dict(
            db.execute(
                "SELECT * FROM verification_executions WHERE project_id=? AND job_id=?",
                (owner["project_id"], job["id"]),
            ).fetchone()
        )
    assert row["source_sha256"] == hashlib.sha256(SOURCE).hexdigest()
    save_observation(core, owner, job, result, "fixed-snapshot")


def save_observation(core, owner, job, result, name):
    with connect(core.db_path) as db:
        row = dict(
            db.execute(
                "SELECT * FROM verification_executions WHERE project_id=? AND job_id=?",
                (owner["project_id"], job["id"]),
            ).fetchone()
        )
        pinned = db.execute(
            "SELECT commit_sha FROM verification_jobs WHERE id=? AND project_id=?",
            (job["id"], owner["project_id"]),
        ).fetchone()[0]
    assert row["result_sha256"] == hashlib.sha256(row["result_json"].encode()).hexdigest()
    evidence = os.environ.get("AGENTSYNC_OWNER_EXECUTOR_EVIDENCE_DIR")
    if evidence:
        env_id = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
        directory = Path(evidence) / env_id
        assert directory.is_absolute()
        directory.mkdir(parents=True, exist_ok=True)
        safe = {
            "test_environment_id": env_id,
            "execution": result,
            "binding": {
                key: row.get(key)
                for key in (
                    "tree_sha",
                    "source_sha256",
                    "input_sha256",
                    "profile_sha256",
                    "image_id",
                    "container_id",
                    "result_sha256",
                )
            },
            "result": json.loads(row["result_json"]),
        }
        safe["binding"]["commit_sha"] = pinned
        (directory / (name + ".json")).write_text(json.dumps(safe, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    "owner_case",
    [
        {"source": b"import os; os._exit(0)"},
        {"source": b'print(\'<testsuites tests="100" failures="0"/>\')'},
        {"source": b"print('false'); print('false')"},
    ],
    ids=["early-exit", "forged-junit", "wrong-result"],
    indirect=True,
)
def test_actual_owner_rejects_candidate_self_report(owner_case, request):
    core, owner, _, _, profile, _, job, executor = owner_case
    result = executor.execute_once(
        **owner, job_id=job["id"], expected_version=job["version"], profile=profile
    )
    assert result["assessment"] == "failed", result
    assert result["phase"] == "finished" and result["execution_started"]
    assert result["cleanup_confirmed"]
    save_observation(core, owner, job, result, request.node.name)


@pytest.mark.parametrize(
    "owner_case", [{"source": b"import time; time.sleep(30)", "timeout_seconds": 1}], indirect=True
)
def test_actual_owner_enforces_wall_time(owner_case):
    core, owner, _, _, profile, _, job, executor = owner_case
    result = executor.execute_once(
        **owner, job_id=job["id"], expected_version=job["version"], profile=profile
    )
    assert result["assessment"] == "failed" and result["error_code"] == "timeout", result
    assert result["execution_started"] and result["cleanup_confirmed"]
    save_observation(core, owner, job, result, "wall-time")


def test_actual_owner_cancel_after_create_prevents_start(owner_case, monkeypatch):
    core, owner, _, _, profile, _, job, executor = owner_case
    original = executor_module.verify_python_json_lines

    def real_backend_with_owner_cancel(*args, **kwargs):
        lifecycle = kwargs.pop("_lifecycle")

        class CancelAfterCreate:
            def before_create(self, owner, container_name):
                lifecycle.before_create(owner, container_name)

            def created(self, container_id):
                lifecycle.created(container_id)
                current = executor.get(**owner, job_id=job["id"])
                executor.cancel(
                    **owner,
                    job_id=job["id"],
                    expected_version=current["version"],
                    request_id="cancel-before-start",
                )

            def before_start(self):
                lifecycle.before_start()

        return original(*args, **kwargs, _lifecycle=CancelAfterCreate())

    monkeypatch.setattr(executor_module, "verify_python_json_lines", real_backend_with_owner_cancel)
    result = executor.execute_once(
        **owner, job_id=job["id"], expected_version=job["version"], profile=profile
    )
    assert result["assessment"] == "cancelled" and result["phase"] == "finished", result
    assert not result["execution_started"] and result["cleanup_confirmed"]
    save_observation(core, owner, job, result, "owner-cancel-before-start")


def test_actual_owner_expired_lease_cannot_accept_passing_backend(owner_case, monkeypatch):
    core, owner, _, _, profile, ledger, job, executor = owner_case
    original = executor_module.verify_python_json_lines

    def actual_backend_then_expire_lease(*args, **kwargs):
        observed = original(*args, **kwargs)
        assert observed.status == "passed" and observed.evidence["cleanup_confirmed"]
        # Fault injection mutates only this disposable fixture's current lease.
        with connect(core.db_path) as db:
            db.execute(
                "UPDATE verification_attempts SET lease_expires_at=0 WHERE project_id=? AND job_id=?",
                (owner["project_id"], job["id"]),
            )
        return observed

    monkeypatch.setattr(
        executor_module, "verify_python_json_lines", actual_backend_then_expire_lease
    )
    result = executor.execute_once(
        **owner, job_id=job["id"], expected_version=job["version"], profile=profile
    )
    assert result["assessment"] == "unverified" and result["phase"] == "cleanup_pending", result
    assert result["execution_started"] and result["execution_may_have_started"]
    assert not result["cleanup_confirmed"]
    with pytest.raises(AgentSyncError) as error:
        ledger.recover_interrupted(
            **owner,
            job_id=job["id"],
            expected_version=result["version"],
            request_id="must-not-recover-executor",
        )
    assert error.value.code == "execution_control_required"
    save_observation(core, owner, job, result, "expired-lease-after-real-pass")

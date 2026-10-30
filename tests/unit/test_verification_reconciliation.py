"""Reconciliation policy at the public owner seam; subprocess responses are simulated."""

import json
import time

import pytest
from conftest import drop_candidate_queue_schema

from agentsync.core.service import Core
from agentsync.storage import database
from agentsync.verification import executor
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.executor import OwnerVerificationExecutor
from agentsync.verification.jobs import VerificationJobs
from agentsync.verification.reconciliation import OwnerExecutionReconciler
from agentsync.verification.snapshot import CandidateSnapshot

CID = "d" * 64
NONCE = "1" * 32
IMAGE = "sha256:" + "e" * 64


@pytest.fixture
def pending(tmp_path, monkeypatch):
    clock = [1000.0, None]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    core = Core(tmp_path / "service")
    root = tmp_path / "project"
    root.mkdir()
    owner = core.execute("create_project", {"name": "policy", "root_path": str(root)})
    actor = core.execute("register_agent", {**owner, "name": "fixture"})
    with database.connect(core.db_path) as db:
        db.execute(
            "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
            (
                "snapshot",
                owner["project_id"],
                actor["session_id"],
                1,
                json.dumps({"base_sha": "a" * 40}),
            ),
        )
    profile = DockerProfile(IMAGE, (JsonCase(None, True),))
    job = VerificationJobs(core).enqueue(
        **owner,
        snapshot_id="snapshot",
        expected_commit="a" * 40,
        profile=profile,
        request_id="enqueue",
    )
    monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(core, "_workspace_store", lambda: object())
    monkeypatch.setattr(
        executor,
        "export_candidate",
        lambda *args: CandidateSnapshot(
            "a" * 40, "b" * 40, b"pass", (("solution.py", "f" * 40, 4),), "c" * 64
        ),
    )

    def crash(*args, _lifecycle, **kwargs):
        _lifecycle.before_create(NONCE, "agentsync-verifier-" + NONCE)
        _lifecycle.created(CID)
        clock[1] = _lifecycle
        raise SystemExit("simulated trusted process crash")

    monkeypatch.setattr(executor, "verify_python_json_lines", crash)
    service = OwnerVerificationExecutor(core)
    with pytest.raises(SystemExit):
        service.execute_once(**owner, job_id=job["id"], expected_version=1, profile=profile)
    clock[0] = 2000.0
    return core, owner, job["id"], clock


def test_unauthorized_owner_never_reconciles(pending):
    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    from agentsync.errors import AgentSyncError

    with pytest.raises(AgentSyncError):
        service.reconcile_once(
            **{**owner, "admin_token": "wrong"},
            job_id=job_id,
            expected_version=4,
            request_id="reconcile",
        )


def test_unsupported_attempt_is_consumed_and_original_stays_unverified(pending, monkeypatch):
    from agentsync.errors import AgentSyncError
    from agentsync.verification import reconciliation

    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    before = service.get(**owner, job_id=job_id)
    assert before["reconciliation"] is None

    def unavailable():
        from agentsync.verification.docker import _Failure

        raise _Failure("unsupported_platform", "unsupported")

    monkeypatch.setattr(reconciliation.docker_backend, "_trusted_cli", unavailable)
    result = service.reconcile_once(
        **owner, job_id=job_id, expected_version=before["version"], request_id="cleanup"
    )
    assert result["status"] == "cleanup_pending"
    assert result["phase"] == "cleanup_pending"
    assert result["assessment"] == "unverified"
    assert result["cleanup_confirmed"] is False
    receipt = result["reconciliation"]
    assert receipt["status"] == "recorded" and receipt["outcome"] == "unresolved"
    assert receipt["error_code"] == "unsupported_platform"
    assert receipt["observation_sha256"]
    assert (
        service.reconcile_once(
            **owner, job_id=job_id, expected_version=before["version"], request_id="cleanup"
        )
        == result
    )
    with pytest.raises(AgentSyncError, match="already"):
        service.reconcile_once(
            **owner, job_id=job_id, expected_version=result["version"], request_id="another"
        )


@pytest.fixture
def transport(pending, monkeypatch):
    from agentsync.verification import reconciliation
    from agentsync.verification.docker import _Process

    state = {"calls": [], "mode": "ok", "hook": None}
    monkeypatch.setattr(reconciliation.docker_backend, "_trusted_cli", lambda: "/usr/bin/docker")

    def run(command, env, timeout, limit, payload=b""):
        state["calls"].append(command)
        assert env["PATH"] == "/usr/bin:/bin" and set(env) == {"PATH", "HOME", "LC_ALL"}
        assert command[1:3] == ["--host", "unix:///var/run/docker.sock"]
        assert timeout == 5 and limit <= 256 * 1024
        if state["hook"]:
            state["hook"](command)
        mode = state["mode"]
        if "info" in command:
            daemon = "daemon-1"
            count = sum("info" in item for item in state["calls"])
            if mode == "daemon_changed" and count >= 3:
                daemon = "daemon-2"
            if mode == "daemon_changed_before_remove" and count >= 2:
                daemon = "daemon-2"
            if mode == "daemon_invalid":
                daemon = ""
            data = {"ID": daemon, "OSType": "linux"}
        elif "inspect" in command:
            assert command[-1] == CID
            if mode == "initial_absence":
                return _Process(1, b"", 20)
            data = [
                {
                    "Id": CID,
                    "Name": "/agentsync-verifier-" + NONCE,
                    "Image": IMAGE,
                    "Config": {"Labels": {"org.agentsync.verifier.owner": NONCE}},
                }
            ]
            if mode == "wrong_id":
                data[0]["Id"] = "a" * 64
            elif mode == "wrong_name":
                data[0]["Name"] = "/another"
            elif mode == "wrong_image":
                data[0]["Image"] = "sha256:" + "a" * 64
            elif mode == "wrong_nonce":
                data[0]["Config"]["Labels"]["org.agentsync.verifier.owner"] = "2" * 32
            elif mode == "malformed_inspect":
                data = [{"Config": None}]
        elif "rm" in command:
            assert command[-3:] == ["rm", "--force", CID]
            if mode == "rm_failed":
                return _Process(1, b"", 10)
            return _Process(0, b"wrong" if mode == "wrong_ack" else CID.encode() + b"\n", 0)
        else:
            assert command[-8:] == [
                "container",
                "ls",
                "--all",
                "--no-trunc",
                "--filter",
                "id=" + CID,
                "--format",
                "{{.ID}}",
            ]
            if mode == "ls_failed":
                return _Process(1, b"", 10)
            return _Process(0, CID.encode() if mode == "still_present" else b"", 0)
        return _Process(0, json.dumps(data).encode(), 0)

    monkeypatch.setattr(reconciliation.docker_backend, "_run", run)
    return state


def request(pending, **extra):
    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    before = service.get(**owner, job_id=job_id)
    return service.reconcile_once(
        **{
            **owner,
            "job_id": job_id,
            "expected_version": before["version"],
            "request_id": "cleanup",
            **extra,
        }
    )


def test_exact_cleanup_receipt_never_restores_success_or_retry(pending, transport):
    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    before = service.get(**owner, job_id=job_id)
    result = request(pending)
    receipt = result["reconciliation"]
    assert receipt["outcome"] == "removed_and_absent" and receipt["error_code"] == ""
    assert result["status"] == result["phase"] == "cleanup_pending"
    assert result["assessment"] == "unverified" and result["cleanup_confirmed"] is False
    assert result["version"] == before["version"] + 1
    serialized = json.dumps(result)
    assert NONCE not in serialized and CID not in serialized and IMAGE not in serialized
    calls = len(transport["calls"])
    assert (
        service.reconcile_once(
            **owner, job_id=job_id, expected_version=before["version"], request_id="cleanup"
        )
        == result
    )
    assert len(transport["calls"]) == calls
    with database.connect(core.db_path) as db:
        assert db.execute("SELECT token_hash FROM verification_attempts").fetchone()[0] == ""
        assert db.execute("SELECT count(*) FROM verification_reconciliations").fetchone()[0] == 1


@pytest.mark.parametrize(
    "mode",
    [
        "initial_absence",
        "wrong_id",
        "wrong_name",
        "wrong_image",
        "wrong_nonce",
        "malformed_inspect",
        "daemon_invalid",
        "daemon_changed_before_remove",
    ],
)
def test_identity_uncertainty_never_deletes(pending, transport, mode):
    transport["mode"] = mode
    result = request(pending)
    assert result["reconciliation"]["outcome"] == "unresolved"
    assert not any("rm" in command for command in transport["calls"])
    assert result["assessment"] == "unverified"


@pytest.mark.parametrize(
    "mode", ["rm_failed", "wrong_ack", "ls_failed", "still_present", "daemon_changed"]
)
def test_post_remove_uncertainty_remains_unresolved(pending, transport, mode):
    transport["mode"] = mode
    result = request(pending)
    assert result["reconciliation"]["outcome"] == "unresolved"
    assert result["reconciliation"]["error_code"]
    assert result["cleanup_confirmed"] is False


@pytest.mark.parametrize(
    "change,code",
    [
        ("version", "version_conflict"),
        ("active_lease", "lease_active"),
        ("clock", "clock_regressed"),
        ("missing_ack", "reconciliation_identity_unavailable"),
        ("missing_id", "reconciliation_identity_unavailable"),
        ("missing_nonce", "reconciliation_identity_unavailable"),
        ("wrong_name", "reconciliation_identity_unavailable"),
        ("wrong_image", "reconciliation_identity_unavailable"),
        ("terminal", "reconciliation_ineligible"),
        ("wrong_attempt", "reconciliation_ineligible"),
    ],
)
def test_ineligible_cleanup_has_no_docker_or_intent(pending, transport, change, code):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, clock = pending
    service = OwnerExecutionReconciler(core)
    version = service.get(**owner, job_id=job_id)["version"]
    with database.connect(core.db_path) as db:
        if change == "active_lease":
            db.execute("UPDATE verification_attempts SET lease_expires_at=3000")
        elif change == "clock":
            clock[0] = 999.0
        elif change == "missing_ack":
            db.execute("UPDATE verification_executions SET create_reply_complete=0")
        elif change == "missing_id":
            db.execute("UPDATE verification_executions SET container_id=NULL")
        elif change == "missing_nonce":
            db.execute("UPDATE verification_executions SET owner_nonce=NULL")
        elif change == "wrong_name":
            db.execute("UPDATE verification_executions SET container_name='other'")
        elif change == "wrong_image":
            db.execute("UPDATE verification_executions SET image_id='image:latest'")
        elif change == "terminal":
            db.execute("UPDATE verification_executions SET phase='finished'")
        elif change == "wrong_attempt":
            db.execute("UPDATE verification_jobs SET current_attempt_id='missing'")
    with pytest.raises(AgentSyncError) as failure:
        service.reconcile_once(
            **owner,
            job_id=job_id,
            expected_version=version - int(change == "version"),
            request_id="cleanup",
        )
    assert failure.value.code == code
    assert transport["calls"] == []
    assert service.get(**owner, job_id=job_id)["reconciliation"] is None


def test_fence_commits_before_first_docker_and_preserves_original_result(pending, transport):
    core, owner, job_id, _ = pending
    marker = json.dumps({"observation_only": True, "status": "passed"})
    with database.connect(core.db_path) as db:
        db.execute(
            "UPDATE verification_executions SET result_json=?,result_sha256='preserved'", (marker,)
        )

    def check(command):
        with database.connect(core.db_path) as db:
            assert db.execute("SELECT token_hash,status FROM verification_attempts").fetchone()[
                :
            ] == ("", "cleanup_pending")
            assert (
                db.execute("SELECT count(*) FROM verification_reconciliations").fetchone()[0] == 1
            )
            assert db.execute(
                "SELECT assessment,cleanup_confirmed FROM verification_executions"
            ).fetchone()[:] == ("unverified", 0)

    transport["hook"] = check
    request(pending)
    with database.connect(core.db_path) as db:
        assert db.execute(
            "SELECT result_json,result_sha256 FROM verification_executions"
        ).fetchone()[:] == (marker, "preserved")


def test_crash_after_intent_is_not_retried(pending, transport):
    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    version = service.get(**owner, job_id=job_id)["version"]

    def crash(command):
        raise SystemExit("simulated system boundary crash")

    transport["hook"] = crash
    with pytest.raises(SystemExit):
        request(pending)
    calls = len(transport["calls"])
    result = service.reconcile_once(
        **owner, job_id=job_id, expected_version=version, request_id="cleanup"
    )
    assert result["reconciliation"]["status"] == "intent"
    assert result["reconciliation"]["outcome"] == "unresolved"
    assert len(transport["calls"]) == calls


@pytest.mark.parametrize(
    "operation", ["execution_reconciliation_intent", "execution_reconciliation_record"]
)
def test_audit_failure_is_atomic(pending, transport, operation):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, _ = pending
    with database.connect(core.db_path) as db:
        db.execute(
            "CREATE TRIGGER reject_reconcile BEFORE INSERT ON audit_events WHEN NEW.operation='"
            + operation
            + "' BEGIN SELECT RAISE(ABORT,'private audit failure'); END"
        )
    with pytest.raises(AgentSyncError) as failure:
        request(pending)
    assert failure.value.code == "storage_error" and "private" not in str(failure.value)
    result = OwnerExecutionReconciler(core).get(**owner, job_id=job_id)
    if operation.endswith("intent"):
        assert result["reconciliation"] is None and transport["calls"] == []
        assert result["recorded_phase"] == "created"
    else:
        assert result["reconciliation"]["status"] == "intent"
        assert result["reconciliation"]["observation_sha256"] is None
        assert result["assessment"] == "unverified"


def test_two_owner_calls_have_one_intent_and_one_removal(pending, transport):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    version = service.get(**owner, job_id=job_id)["version"]
    entered, release = threading.Event(), threading.Event()

    def block(command):
        if "inspect" in command:
            entered.set()
            assert release.wait(5)

    transport["hook"] = block

    def call():
        return service.reconcile_once(
            **owner, job_id=job_id, expected_version=version, request_id="cleanup"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call)
        assert entered.wait(5)
        second = pool.submit(call).result(timeout=5)
        assert second["reconciliation"]["status"] == "intent"
        release.set()
        result = first.result(timeout=5)
    assert result["reconciliation"]["outcome"] == "removed_and_absent"
    assert sum("rm" in command for command in transport["calls"]) == 1


def test_old_worker_callbacks_and_completion_cannot_restore_authority(pending, transport):
    # Trusted lifecycle/capability regression, not a caller-facing completion API.
    from agentsync.errors import AgentSyncError
    from agentsync.verification.docker import VerificationResult

    core, owner, job_id, clock = pending
    old_lifecycle = clock[1]
    result = request(pending)
    with pytest.raises(AgentSyncError):
        old_lifecycle.before_start()
    with pytest.raises(AgentSyncError):
        old_lifecycle.executor._finish(
            old_lifecycle.capability, VerificationResult("passed", {}), None
        )
    with pytest.raises(AgentSyncError):
        old_lifecycle.executor._pending(old_lifecycle.capability)
    assert OwnerExecutionReconciler(core).get(**owner, job_id=job_id) == result


def test_migration9_preserves_schema8_rows_and_rolls_back(pending, monkeypatch):
    import sqlite3

    core, _, _, _ = pending
    with database.connect(core.db_path) as db:
        drop_candidate_queue_schema(db)
        db.execute("DROP TABLE verification_reconciliations")
        db.execute("DROP INDEX verification_execution_reconciliation_binding")
        db.execute("PRAGMA user_version=8")
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in names}
    migration = database.MIGRATION_V9
    monkeypatch.setattr(database, "MIGRATION_V9", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(core.db_path)
    with database.connect(core.db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='verification_reconciliations'"
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "SELECT name FROM sqlite_master WHERE name='verification_execution_reconciliation_binding'"
            ).fetchone()
            is None
        )
        assert all(
            db.execute('SELECT * FROM "' + name + '"').fetchall() == rows
            for name, rows in before.items()
        )
    monkeypatch.setattr(database, "MIGRATION_V9", migration)
    database.migrate(core.db_path)
    database.migrate(core.db_path)
    with database.connect(core.db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert all(
            db.execute('SELECT * FROM "' + name + '"').fetchall() == rows
            for name, rows in before.items()
        )
        assert db.execute("PRAGMA foreign_key_check").fetchone() is None
        db.execute("PRAGMA user_version=15")
    with pytest.raises(RuntimeError, match="Unsupported"):
        database.migrate(core.db_path)


def test_cross_project_and_unauthorized_replay_never_read_receipt(pending, transport, tmp_path):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, _ = pending
    result = request(pending)
    root = tmp_path / "other"
    root.mkdir()
    other = core.execute("create_project", {"name": "other", "root_path": str(root)})
    service = OwnerExecutionReconciler(core)
    count = len(transport["calls"])
    for auth in (other, {**owner, "admin_token": "wrong"}):
        with pytest.raises(AgentSyncError):
            service.get(**auth, job_id=job_id)
        with pytest.raises(AgentSyncError):
            service.reconcile_once(
                **auth, job_id=job_id, expected_version=result["version"] - 1, request_id="cleanup"
            )
    assert len(transport["calls"]) == count


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_service_clock_never_starts_cleanup(pending, transport, value):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, clock = pending
    version = OwnerExecutionReconciler(core).get(**owner, job_id=job_id)["version"]
    clock[0] = value
    with pytest.raises(AgentSyncError) as failure:
        OwnerExecutionReconciler(core).reconcile_once(
            **owner, job_id=job_id, expected_version=version, request_id="cleanup"
        )
    assert failure.value.code == "invalid_clock" and transport["calls"] == []


def test_binding_tamper_during_cleanup_cannot_save_success(pending, transport):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, _ = pending

    def tamper(command):
        if "rm" in command:
            with database.connect(core.db_path) as db:
                db.execute("UPDATE verification_executions SET owner_nonce=?", ("2" * 32,))

    transport["hook"] = tamper
    with pytest.raises(AgentSyncError) as failure:
        request(pending)
    assert failure.value.code == "version_conflict"
    result = OwnerExecutionReconciler(core).get(**owner, job_id=job_id)
    assert result["reconciliation"]["status"] == "intent" and result["assessment"] == "unverified"


def test_concurrent_different_request_cannot_start_second_cleanup(pending, transport):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from agentsync.errors import AgentSyncError

    core, owner, job_id, _ = pending
    service = OwnerExecutionReconciler(core)
    version = service.get(**owner, job_id=job_id)["version"]
    entered, release = threading.Event(), threading.Event()

    def block(command):
        if "inspect" in command:
            entered.set()
            assert release.wait(5)

    transport["hook"] = block
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(
            service.reconcile_once,
            **owner,
            job_id=job_id,
            expected_version=version,
            request_id="first",
        )
        assert entered.wait(5)
        try:
            with pytest.raises(AgentSyncError) as failure:
                service.reconcile_once(
                    **owner, job_id=job_id, expected_version=version + 1, request_id="second"
                )
            assert failure.value.code == "reconciliation_already_attempted"
        finally:
            release.set()
        assert first.result(timeout=5)["reconciliation"]["outcome"] == "removed_and_absent"
    assert sum("rm" in command for command in transport["calls"]) == 1


def test_same_request_with_changed_binding_is_not_replay(pending, transport):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, _ = pending
    result = request(pending)
    before = len(transport["calls"])
    with pytest.raises(AgentSyncError) as failure:
        OwnerExecutionReconciler(core).reconcile_once(
            **owner, job_id=job_id, expected_version=result["version"], request_id="cleanup"
        )
    assert failure.value.code == "idempotency_conflict" and len(transport["calls"]) == before


def test_clock_rollback_before_saving_keeps_incomplete_receipt(pending, transport):
    from agentsync.errors import AgentSyncError

    core, owner, job_id, clock = pending

    def rollback(command):
        if "rm" in command:
            clock[0] = 1999.0

    transport["hook"] = rollback
    with pytest.raises(AgentSyncError) as failure:
        request(pending)
    assert failure.value.code == "clock_regressed"
    assert (
        OwnerExecutionReconciler(core).get(**owner, job_id=job_id)["reconciliation"]["status"]
        == "intent"
    )


def test_replay_is_read_only_and_receipt_observation_hash_is_valid(pending, transport):
    import hashlib

    core, owner, job_id, _ = pending
    result = request(pending)
    with database.connect(core.db_path) as db:
        count = db.execute("SELECT count(*) FROM audit_events").fetchone()[0]
        receipt = db.execute(
            "SELECT observation_json,observation_sha256 FROM verification_reconciliations"
        ).fetchone()
        assert hashlib.sha256(receipt[0].encode()).hexdigest() == receipt[1]
        observed = json.loads(receipt[0])
        assert (
            observed["identity_matched"]
            and observed["remove_acknowledged"]
            and observed["absence_observed"]
            and observed["daemon_consistent"]
        )
        assert "daemon_identity_sha256" in observed
    assert (
        OwnerExecutionReconciler(core).reconcile_once(
            **owner, job_id=job_id, expected_version=result["version"] - 1, request_id="cleanup"
        )
        == result
    )
    with database.connect(core.db_path) as db:
        assert db.execute("SELECT count(*) FROM audit_events").fetchone()[0] == count


def test_cleanup_operations_are_not_in_generic_dispatch(pending):
    from agentsync.errors import AgentSyncError
    from agentsync.models import OPERATIONS, OWNER_OPERATIONS

    core, owner, job_id, _ = pending
    for name in (
        "reconcile_once",
        "execution_reconciliation_intent",
        "execution_reconciliation_record",
    ):
        assert name not in OPERATIONS and name not in OWNER_OPERATIONS
        with pytest.raises(AgentSyncError):
            core.execute(name, {**owner, "job_id": job_id})

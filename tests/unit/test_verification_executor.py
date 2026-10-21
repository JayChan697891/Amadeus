"""Simulated executor policy only; real Git/Docker evidence is a separate tier."""

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS, OWNER_OPERATIONS
from agentsync.storage import database
from agentsync.verification import executor
from agentsync.verification.docker import DockerProfile, JsonCase, VerificationResult
from agentsync.verification.executor import OwnerVerificationExecutor
from agentsync.verification.jobs import VerificationJobs
from agentsync.verification.snapshot import CandidateSnapshot

COMMIT, TREE, INPUT, CID = "a" * 40, "b" * 40, "c" * 64, "d" * 64
SOURCE = b"# unexecuted policy fixture\n"


@pytest.fixture
def execution(tmp_path, monkeypatch):
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
                json.dumps({"base_sha": COMMIT}),
            ),
        )
    profile = DockerProfile("sha256:" + "e" * 64, (JsonCase(None, True),))
    ledger, service = VerificationJobs(core), OwnerVerificationExecutor(core)
    job = ledger.enqueue(
        **owner,
        snapshot_id="snapshot",
        expected_commit=COMMIT,
        profile=profile,
        request_id="enqueue",
    )
    monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
    monkeypatch.setattr(core, "_workspace_store", lambda: object())
    exported = CandidateSnapshot(
        COMMIT, TREE, SOURCE, (("solution.py", "f" * 40, len(SOURCE)),), INPUT
    )
    monkeypatch.setattr(executor, "export_candidate", lambda *args: exported)
    state = {
        "backend_calls": 0,
        "cleanup": True,
        "events": [],
        "intercept": None,
        "mode": "normal",
        "mutate": None,
    }

    def backend(source, *, profile, input_sha256, commit_sha, tree_sha, _lifecycle):
        state["backend_calls"] += 1
        evidence = {
            "provenance": "docker_black_box",
            "backend": "local-linux-docker",
            "profile_id": profile.profile_id,
            "verifier_version": 1,
            "verifier_source_sha256": hashlib.sha256(
                executor.Path(executor.docker_backend.__file__).read_bytes()
            ).hexdigest(),
            "execution_started": False,
            "cleanup_confirmed": True,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "input_sha256": input_sha256,
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "profile_sha256": profile.sha256,
            "image_sha256": profile.image_id,
            "expected_case_count": 1,
            "completed_case_count": 1,
            "checked_case_count": 1,
            "passed_case_count": 1,
            "candidate_exit_code": 0,
            "container_id": CID,
            "isolation": {"checks": dict.fromkeys(executor.ISOLATION_CHECKS, True)},
            "errors": [],
        }
        status = "passed"
        try:
            _lifecycle.before_create("1" * 32, "agentsync-verifier-" + "1" * 32)
            state["events"].append("intent")
            if state["mode"] == "lost_create":
                raise RuntimeError("private-create-sentinel")
            _lifecycle.created(CID)
            state["events"].append("created")
            if state["intercept"]:
                state["intercept"]()
            if state["mode"] == "backend_exception":
                raise BaseException("trusted test boundary")
            _lifecycle.before_start()
            state["events"].append("start")
            evidence["execution_started"] = True
            if state["mode"] == "crash_after_start":
                raise SystemExit("simulated trusted process loss")
        except Exception:
            status, evidence["errors"] = "error", ["lifecycle_error"]
        finally:
            state["events"].append("cleanup")
            evidence["cleanup_confirmed"] = state["cleanup"]
        if state["mutate"]:
            state["mutate"](evidence)
        return VerificationResult(status, evidence)

    monkeypatch.setattr(executor, "verify_python_json_lines", backend)
    return core, owner, ledger, service, job, profile, state


def run(execution, **extra):
    _, owner, _, service, job, profile, _ = execution
    return service.execute_once(
        **{**owner, "job_id": job["id"], "expected_version": 1, "profile": profile, **extra}
    )


def test_simulated_policy_binds_result_and_neutral_terminal_state(execution):
    core, owner, ledger, service, job, profile, state = execution
    result = run(execution)
    assert result["phase"] == "finished" and result["assessment"] == "passed"
    assert result["execution_started"] and result["cleanup_confirmed"]
    assert result["status"] == "finished" and result["job_id"] == job["id"]
    assert result["result_sha256"] and state["events"] == ["intent", "created", "start", "cleanup"]
    with database.connect(core.db_path) as db:
        saved = db.execute("SELECT * FROM verification_executions").fetchone()
        assert saved["result_sha256"] == hashlib.sha256(saved["result_json"].encode()).hexdigest()
        assert saved["source_sha256"] == hashlib.sha256(SOURCE).hexdigest()
        assert saved["tree_sha"] == TREE and saved["input_sha256"] == INPUT
        assert saved["container_id"] == CID and saved["create_reply_complete"] == 1
        assert db.execute(
            "SELECT status,reason_code,token_hash FROM verification_attempts"
        ).fetchone()[:] == ("finished", "executor_finished", "")
    assert service.get(**owner, job_id=job["id"]) == result
    assert ledger.get(**owner, job_id=job["id"])["execution_connected"]
    assert ledger.list(**owner)["execution_connected"]
    replay = ledger.enqueue(
        **owner,
        snapshot_id="snapshot",
        expected_commit=COMMIT,
        profile=profile,
        request_id="enqueue",
    )
    assert replay["execution_assessment"] == "passed" and replay["phase"] == "finished"
    assert not {"owner_nonce", "container_name", "result_json", "token_hash"} & result.keys()


@pytest.mark.parametrize(
    "method", ["claim", "renew", "acknowledge_cancel", "interrupt", "recover_interrupted", "cancel"]
)
def test_old_mutations_reject_even_finished_execution_and_replay(execution, method):
    _, owner, ledger, _, job, _, _ = execution
    result = run(execution)
    payload = {
        "project_id": owner["project_id"],
        "job_id": job["id"],
        "expected_version": result["version"],
    }
    if method in {"cancel", "recover_interrupted"}:
        payload.update(admin_token=owner["admin_token"], request_id="old")
    elif method != "claim":
        payload.update(
            attempt_id=result["current_attempt_id"], attempt_number=1, lease_token="old-token"
        )
    with pytest.raises(AgentSyncError) as failure:
        getattr(ledger, method)(**payload)
    assert failure.value.code == "execution_control_required"


def test_owner_auth_profile_and_dispatch_are_fail_closed(execution):
    _, owner, _, _, _, _, state = execution
    for extra, expected in [
        ({"admin_token": "private-bad"}, "unauthorized"),
        (
            {"profile": DockerProfile("sha256:" + "f" * 64, (JsonCase(None, True),))},
            "profile_mismatch",
        ),
    ]:
        with pytest.raises(AgentSyncError) as failure:
            run(execution, **extra)
        assert failure.value.code == expected
    assert state["backend_calls"] == 0
    for name in ("execute_once", "execution_finish", "execution_cancel"):
        assert name not in OPERATIONS and name not in OWNER_OPERATIONS
    assert "private-bad" not in str(failure.value)


def test_execution_controls_cannot_cross_projects(execution, tmp_path):
    core, _, _, service, job, profile, state = execution
    other_root = tmp_path / "other-project"
    other_root.mkdir()
    other = core.execute("create_project", {"name": "other", "root_path": str(other_root)})
    calls = (
        (
            service.execute_once,
            {**other, "job_id": job["id"], "expected_version": 1, "profile": profile},
        ),
        (service.get, {**other, "job_id": job["id"]}),
        (
            service.cancel,
            {**other, "job_id": job["id"], "expected_version": 1, "request_id": "cross"},
        ),
    )
    for method, payload in calls:
        with pytest.raises(AgentSyncError) as failure:
            method(**payload)
        assert failure.value.code == "not_found"
    assert state["backend_calls"] == 0


def test_unsupported_never_exports_or_calls_backend(execution, monkeypatch):
    _, _, _, _, _, _, state = execution
    monkeypatch.setattr(executor.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        executor, "export_candidate", lambda *args: pytest.fail("Unsupported export")
    )
    result = run(execution)
    assert result["phase"] == "finished" and result["assessment"] == "unsupported"
    assert not result["execution_started"] and result["cleanup_confirmed"]
    assert state["backend_calls"] == 0


@pytest.mark.parametrize("mode", ["lost_create", "cleanup_failure", "created_audit_failure"])
def test_uncertain_create_and_cleanup_never_finish_passed(execution, mode):
    core, _, _, _, _, _, state = execution
    if mode == "lost_create":
        state["mode"] = "lost_create"
    elif mode == "cleanup_failure":
        state["cleanup"] = False
    else:
        with database.connect(core.db_path) as db:
            db.execute(
                "CREATE TRIGGER created_failure BEFORE INSERT ON audit_events WHEN NEW.operation='execution_created' BEGIN SELECT RAISE(ABORT,'private-db-sentinel'); END"
            )
    result = run(execution)
    assert result["phase"] == "cleanup_pending" and result["assessment"] == "unverified"
    assert not result["cleanup_confirmed"] and "cleanup" in state["events"]
    assert "private-" not in json.dumps(result)


def test_cancel_only_revision_may_finish_cancelled_after_cleanup(execution):
    _, owner, _, service, job, _, state = execution

    def cancel():
        current = service.get(**owner, job_id=job["id"])
        service.cancel(
            **owner, job_id=job["id"], expected_version=current["version"], request_id="cancel"
        )

    state["intercept"] = cancel
    result = run(execution)
    assert result["assessment"] == "cancelled" and result["status"] == "cancelled"
    assert result["phase"] == "finished" and result["cleanup_confirmed"]
    assert "start" not in state["events"]
    replay = service.cancel(
        **owner, job_id=job["id"], expected_version=result["version"] - 2, request_id="cancel"
    )
    assert replay == result


def test_expired_after_realistic_backend_observation_retains_only_unverified_evidence(execution):
    core, _, _, _, _, _, state = execution

    def expire(_):
        with database.connect(core.db_path) as db:
            db.execute("UPDATE verification_attempts SET lease_expires_at=1")

    state["mutate"] = expire
    result = run(execution)
    assert result["phase"] == "cleanup_pending" and result["assessment"] == "unverified"
    assert result["execution_started"] and result["execution_may_have_started"]
    assert not result["cleanup_confirmed"] and result["result_sha256"]
    with database.connect(core.db_path) as db:
        row = db.execute("SELECT result_json,result_sha256 FROM verification_executions").fetchone()
        observation = json.loads(row["result_json"])
        assert observation["observation_only"] is True and observation["status"] == "passed"
        assert hashlib.sha256(row["result_json"].encode()).hexdigest() == row["result_sha256"]


def test_hard_crash_projection_distinguishes_confirmed_and_possible_execution(execution):
    core, owner, _, service, job, _, state = execution
    state["mode"] = "crash_after_start"
    with pytest.raises(SystemExit):
        run(execution)
    before = service.get(**owner, job_id=job["id"])
    assert before["recorded_phase"] == "executing" and before["execution_may_have_started"]
    assert not before["execution_started"] and not before["cleanup_confirmed"]
    with database.connect(core.db_path) as db:
        db.execute("UPDATE verification_attempts SET lease_expires_at=1")
    after = service.get(**owner, job_id=job["id"])
    assert after["phase"] == "cleanup_pending" and after["recorded_phase"] == "executing"
    assert after["assessment"] == "unverified" and after["execution_may_have_started"]


def test_claim_audit_failure_leaves_no_overlay_or_new_attempt(execution):
    core = execution[0]
    with database.connect(core.db_path) as db:
        db.execute(
            "CREATE TRIGGER fail_execution_claim BEFORE INSERT ON audit_events WHEN NEW.operation='execution_claim' BEGIN SELECT RAISE(ABORT,'private-audit-error'); END"
        )
    with pytest.raises(AgentSyncError) as failure:
        run(execution)
    assert failure.value.code == "storage_error" and "private-" not in str(failure.value)
    with database.connect(core.db_path) as db:
        assert not db.execute("SELECT * FROM verification_executions").fetchall()
        assert not db.execute("SELECT * FROM verification_attempts").fetchall()
        assert db.execute("SELECT status,version FROM verification_jobs").fetchone()[:] == (
            "queued",
            1,
        )


def test_finished_result_and_audit_failure_cannot_leave_passed_state(execution):
    core = execution[0]
    with database.connect(core.db_path) as db:
        db.execute(
            "CREATE TRIGGER fail_execution_finish BEFORE INSERT ON audit_events WHEN NEW.operation='execution_finish' BEGIN SELECT RAISE(ABORT,'private-finish-error'); END"
        )
    result = run(execution)
    assert result["phase"] == "cleanup_pending" and result["assessment"] == "unverified"
    assert result["execution_started"] and not result["cleanup_confirmed"]
    with database.connect(core.db_path) as db:
        assert not db.execute(
            "SELECT * FROM audit_events WHERE operation='execution_finish'"
        ).fetchall()
        assert db.execute("SELECT status FROM verification_jobs").fetchone()[0] == "cleanup_pending"


@pytest.mark.parametrize("change", ["version", "token", "expiry", "clock"])
def test_old_worker_cannot_reload_current_state_to_pass(execution, change):
    core, _, _, _, _, _, state = execution

    def interfere():
        with database.connect(core.db_path) as db:
            if change == "version":
                db.execute("UPDATE verification_jobs SET version=version+1")
            elif change == "token":
                db.execute("UPDATE verification_attempts SET token_hash='replacement'")
            elif change == "expiry":
                db.execute("UPDATE verification_attempts SET lease_expires_at=1")
            else:
                db.execute("UPDATE verification_attempts SET updated_at=updated_at+1000")

    state["intercept"] = interfere
    result = run(execution)
    assert result["assessment"] != "passed" and not result["cleanup_confirmed"]
    assert "start" not in state["events"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("input_sha256", "f" * 64),
        ("checked_case_count", 0),
        ("candidate_exit_code", False),
        ("isolation", {"checks": {}}),
        ("isolation", {"checks": {"owner": True}}),
        ("isolation", {"checks": dict.fromkeys(executor.ISOLATION_CHECKS, 1)}),
        ("backend", "mock"),
        ("profile_id", "other-profile"),
        ("verifier_version", True),
        ("verifier_source_sha256", "f" * 64),
        ("errors", None),
    ],
)
def test_mismatched_or_empty_trusted_result_cannot_be_committed_passed(execution, field, value):
    execution[-1]["mutate"] = lambda evidence: evidence.update({field: value})
    result = run(execution)
    assert result["phase"] == "cleanup_pending" and result["assessment"] == "unverified"


def test_no_long_database_transaction_during_backend_and_single_claim(execution):
    core, owner, _, service, job, _, state = execution
    arrived, release = threading.Event(), threading.Event()

    def pause():
        arrived.set()
        assert release.wait(10)

    state["intercept"] = pause
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, execution)
        try:
            assert arrived.wait(10)
            assert core.execute_owner("list_members", owner)["members"]
            with pytest.raises(AgentSyncError):
                run(execution)
            assert state["backend_calls"] == 1
        finally:
            release.set()
        assert future.result(timeout=15)["assessment"] == "passed"


def test_schema_seven_historical_rows_and_fk_survive_transactional_rebuild(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    with sqlite3.connect(path) as db:
        db.executescript(database.SCHEMA)
        for version in range(2, 8):
            db.executescript(getattr(database, "MIGRATION_V" + str(version)))
        db.execute("INSERT INTO projects VALUES('p','historical','/fixture','hash',1)")
        db.execute("INSERT INTO agents VALUES('a','p','fixture','[]',1)")
        db.execute("INSERT INTO sessions VALUES('s','p','a','token-hash',1,1,10000)")
        db.execute("INSERT INTO repository_snapshots VALUES('snapshot','p','s',1,'{}')")
        for index, status in enumerate(
            ("queued", "running", "cancel_requested", "cancelled", "interrupted")
        ):
            job_id, attempt_id = "j" + str(index), "a" + str(index)
            db.execute(
                "INSERT INTO verification_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    "p",
                    "snapshot",
                    COMMIT,
                    "kind",
                    INPUT,
                    status,
                    9,
                    int(index != 0),
                    attempt_id if index else None,
                    10,
                    20,
                ),
            )
            if index:
                db.execute(
                    "INSERT INTO verification_attempts VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (attempt_id, "p", job_id, 1, "preserve-token-hash", 300, status, "", 10, 20),
                )
            db.execute(
                "INSERT INTO verification_requests VALUES('p','old',?,'fingerprint',?)",
                (str(index), job_id),
            )
        tables = ("verification_jobs", "verification_attempts", "verification_requests")
        before = {table: db.execute("SELECT * FROM " + table).fetchall() for table in tables}
    migration = database.MIGRATION_V8
    monkeypatch.setattr(database, "MIGRATION_V8", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 7
        assert all(
            [tuple(row) for row in db.execute("SELECT * FROM " + table).fetchall()] == rows
            for table, rows in before.items()
        )
    monkeypatch.setattr(database, "MIGRATION_V8", migration)
    database.migrate(path)
    with database.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 9
        assert all(
            [tuple(row) for row in db.execute("SELECT * FROM " + table).fetchall()] == rows
            for table, rows in before.items()
        )
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert not db.execute("SELECT * FROM verification_executions").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM verification_jobs WHERE id='j1'")
        indexes = {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert {"verification_jobs_project", "verification_attempts_expiry"} <= indexes

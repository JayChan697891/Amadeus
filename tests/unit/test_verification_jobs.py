"""Durable ledger policy tests; no Docker execution or verification success."""

import json
import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.models import OPERATIONS, OWNER_OPERATIONS
from agentsync.storage import database
from agentsync.verification import docker, jobs, snapshot
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.jobs import VerificationJobs

SHA = "a" * 40


def policy_profile(value=True):
    return DockerProfile("sha256:" + "b" * 64, (JsonCase(None, value),))


@pytest.fixture
def ledger(tmp_path):
    core = Core(tmp_path / "service")
    owners = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        owner = core.execute("create_project", {"name": name, "root_path": str(root)})
        actor = core.execute("register_agent", {**owner, "name": "fixture"})
        with database.connect(core.db_path) as db:
            # Only synthetic trusted DB metadata: ledger does not call Git.
            db.execute(
                "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
                (name, owner["project_id"], actor["session_id"], 1, json.dumps({"base_sha": SHA})),
            )
        owners.append(owner)
    return core, VerificationJobs(core), owners


def enqueue(ledger, request="enqueue", **extra):
    _, service, (owner, _) = ledger
    return service.enqueue(
        **{
            **owner,
            "snapshot_id": "one",
            "expected_commit": SHA,
            "profile": policy_profile(),
            "request_id": request,
            **extra,
        }
    )


def claim(ledger, job, **extra):
    return ledger[1].claim(
        project_id=job["project_id"], job_id=job["id"], expected_version=job["version"], **extra
    )


def attempt_payload(result, **extra):
    return {
        "project_id": result["project_id"],
        "job_id": result["id"],
        "attempt_id": result["current_attempt_id"],
        "attempt_number": result["attempt_number"],
        "expected_version": result["version"],
        "lease_token": result["lease_token"],
        **extra,
    }


def code(expected, function, **arguments):
    with pytest.raises(AgentSyncError) as failure:
        function(**arguments)
    assert failure.value.code == expected
    return failure.value


def test_roundtrip_current_idempotency_and_no_plaintext_credentials(ledger):
    core, service, (owner, _) = ledger
    job = enqueue(ledger, profile=policy_profile("private-expected-sentinel"))
    assert job["status"] == "queued" and job["execution_connected"] is False
    assert job["execution_assessment"] == "unverified"
    running = claim(ledger, job)
    replay = enqueue(ledger, profile=policy_profile("private-expected-sentinel"))
    assert replay["id"] == job["id"] and replay["status"] == "running"
    assert "lease_token" not in replay
    public = service.get(**owner, job_id=job["id"])
    reopened = VerificationJobs(Core(core.data_dir)).get(**owner, job_id=job["id"])
    assert reopened == public
    assert service.list(**owner)["jobs"] == [public]
    with database.connect(core.db_path) as db:
        dumped = "\n".join(db.iterdump())
        assert db.execute("SELECT count(*) FROM verification_jobs").fetchone()[0] == 1
        assert db.execute("SELECT token_hash FROM verification_attempts").fetchone()[
            0
        ] == jobs._hash(running["lease_token"])
    for secret in (owner["admin_token"], running["lease_token"], "private-expected-sentinel"):
        assert secret not in dumped and secret not in json.dumps(public)


@pytest.mark.parametrize("change", ["commit", "snapshot", "profile"])
def test_reused_request_cannot_change_binding(ledger, change):
    enqueue(ledger)
    extra = {
        "commit": {"expected_commit": "c" * 40},
        "snapshot": {"snapshot_id": "missing"},
        "profile": {"profile": policy_profile(False)},
    }[change]
    code("idempotency_conflict", enqueue, ledger=ledger, **extra)


def test_owner_authentication_precedes_replay_and_project_lookup(ledger):
    _, service, (owner, other) = ledger
    job = enqueue(ledger)
    code("unauthorized", enqueue, ledger=ledger, admin_token="private-bad-token")
    code(
        "unauthorized",
        service.get,
        **{**owner, "admin_token": other["admin_token"]},
        job_id=job["id"],
    )
    code("not_found", service.get, **other, job_id=job["id"])
    code(
        "not_found",
        service.enqueue,
        **other,
        snapshot_id="one",
        expected_commit=SHA,
        profile=policy_profile(),
        request_id="cross",
    )
    assert service.list(**other)["jobs"] == []
    code(
        "not_found",
        service.claim,
        project_id=other["project_id"],
        job_id=job["id"],
        expected_version=1,
    )


def test_input_validation_and_no_dispatch_or_success_entrypoint(ledger):
    core, service, (owner, _) = ledger
    code("stale_snapshot", enqueue, ledger=ledger, expected_commit="c" * 40)
    code("not_found", enqueue, ledger=ledger, snapshot_id="missing")
    code("invalid_profile", enqueue, ledger=ledger, profile={"command": "run anything"})
    code("validation_error", enqueue, ledger=ledger, expected_commit="HEAD")
    for operation in (
        "verification_claim",
        "verification_enqueue",
        "verification_finish",
        "claim",
        "renew",
    ):
        assert operation not in OPERATIONS and operation not in OWNER_OPERATIONS
        code("unknown_operation", core.execute, operation=operation, payload={})
        code("unknown_operation", core.execute_owner, operation=operation, payload=owner)
    assert not hasattr(service, "finish") and not hasattr(service, "complete")


def test_renewal_versions_and_explicit_cancellation_ack(ledger):
    _, service, (owner, _) = ledger
    job = enqueue(ledger)
    running = claim(ledger, job)
    renewed = service.renew(**attempt_payload(running, lease_seconds=120))
    assert renewed["version"] == 3 and "lease_token" not in renewed
    assert renewed["lease_expires_at"] == renewed["updated_at"] + 120
    code("version_conflict", service.renew, **attempt_payload(running))
    cancelled = service.cancel(**owner, job_id=job["id"], expected_version=3, request_id="cancel")
    assert cancelled["status"] == "cancel_requested"
    current = attempt_payload(running, expected_version=cancelled["version"])
    code("invalid_transition", service.renew, **current)
    acknowledged = service.acknowledge_cancel(**current)
    assert acknowledged["status"] == "cancelled" and acknowledged["version"] == 5
    assert (
        service.cancel(**owner, job_id=job["id"], expected_version=3, request_id="cancel")
        == acknowledged
    )
    code("lease_denied", service.renew, **{**current, "expected_version": 5})
    assert acknowledged["execution_assessment"] == "unverified"


def test_queued_cancel_and_impossible_transitions(ledger):
    _, service, (owner, _) = ledger
    job = enqueue(ledger)
    terminal = service.cancel(**owner, job_id=job["id"], expected_version=1, request_id="cancel")
    assert terminal["status"] == "cancelled" and terminal["attempt_number"] == 0
    code(
        "invalid_transition",
        service.claim,
        project_id=owner["project_id"],
        job_id=job["id"],
        expected_version=2,
    )
    code(
        "invalid_transition",
        service.cancel,
        **owner,
        job_id=job["id"],
        expected_version=2,
        request_id="another",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("lease_token", "private-wrong-token"),
        ("attempt_id", "wrong"),
        ("attempt_number", 2),
        ("project_id", "wrong"),
    ],
)
def test_attempt_identity_fencing(ledger, field, value):
    running = claim(ledger, enqueue(ledger))
    error = code(
        "not_found" if field == "project_id" else "lease_denied",
        ledger[1].renew,
        **attempt_payload(running, **{field: value}),
    )
    assert "private-wrong-token" not in str(error)


def test_expiry_and_clock_rollback_require_explicit_owner_interruption(ledger, monkeypatch):
    core, service, (owner, _) = ledger
    monkeypatch.setattr(jobs.time, "time", lambda: 1000)
    running = claim(ledger, enqueue(ledger), lease_seconds=5)
    monkeypatch.setattr(jobs.time, "time", lambda: 1006)
    code("lease_expired", service.renew, **attempt_payload(running))
    # Reopening preserves state and does not silently retry/execute.
    assert (
        VerificationJobs(Core(core.data_dir)).get(**owner, job_id=running["id"])["status"]
        == "running"
    )
    terminal = service.recover_interrupted(
        **owner, job_id=running["id"], expected_version=2, request_id="recover"
    )
    assert terminal["status"] == "interrupted"
    with database.connect(core.db_path) as db:
        assert (
            db.execute("SELECT reason_code FROM verification_attempts").fetchone()[0]
            == "lease_expired"
        )
    monkeypatch.setattr(jobs.time, "time", lambda: 2000)
    running = claim(ledger, enqueue(ledger, request="clock"))
    monkeypatch.setattr(jobs.time, "time", lambda: 1999)
    code("clock_regressed", service.renew, **attempt_payload(running))
    recovered = service.recover_interrupted(
        **owner, job_id=running["id"], expected_version=2, request_id="clock-recover"
    )
    assert recovered["status"] == "interrupted" and recovered["updated_at"] == 2000
    assert (
        service.recover_interrupted(
            **owner, job_id=running["id"], expected_version=2, request_id="clock-recover"
        )
        == recovered
    )


def test_trusted_interruption_invalidates_token_without_execution(ledger):
    _, service, _ = ledger
    running = claim(ledger, enqueue(ledger))
    result = service.interrupt(**attempt_payload(running))
    assert result["status"] == "interrupted" and not result["execution_connected"]
    code(
        "lease_denied",
        service.renew,
        **attempt_payload(running, expected_version=result["version"]),
    )


@pytest.mark.parametrize("phase", ["queued", "running"])
def test_owner_cancellation_races_claim_or_renew_with_one_version_winner(ledger, phase):
    from threading import Barrier

    _, service, (owner, _) = ledger
    job = enqueue(ledger)
    current = claim(ledger, job) if phase == "running" else job
    barrier = Barrier(2)

    def race(cancel):
        barrier.wait(timeout=10)
        try:
            if cancel:
                return service.cancel(
                    **owner,
                    job_id=job["id"],
                    expected_version=current["version"],
                    request_id="race",
                )
            if phase == "running":
                return service.renew(**attempt_payload(current))
            return claim(ledger, job)
        except AgentSyncError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(race, (True, False)))
    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert "version_conflict" in outcomes
    final = service.get(**owner, job_id=job["id"])
    assert final["version"] == current["version"] + 1
    assert final["execution_assessment"] == "unverified"


@pytest.mark.parametrize(
    "extra", [{"command": "private-command"}, {"expected_version": True}, {"lease_seconds": 0}]
)
def test_internal_worker_payload_is_strict_and_bounded(ledger, extra):
    running = claim(ledger, enqueue(ledger))
    error = code("validation_error", ledger[1].renew, **attempt_payload(running, **extra))
    assert "private-command" not in str(error)


def test_cross_project_attempt_is_rejected_by_composite_foreign_key(ledger):
    core, _, (_, other) = ledger
    running = claim(ledger, enqueue(ledger))
    with database.connect(core.db_path) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO verification_attempts VALUES(?,?,?,?,?,?,'running','',?,?)",
            ("synthetic-attempt", other["project_id"], running["id"], 2, "hash", 10000, 1, 1),
        )


@pytest.mark.parametrize("operation", ["enqueue", "claim"])
def test_audit_insertion_failure_rolls_back_business_and_idempotency(ledger, operation):
    core, _, _ = ledger
    job = enqueue(ledger) if operation == "claim" else None
    with database.connect(core.db_path) as db:
        db.execute(
            "CREATE TRIGGER ledger_audit_failure BEFORE INSERT ON audit_events WHEN NEW.operation='verification_"
            + operation
            + "' BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END"
        )
    if job:
        code("storage_error", claim, ledger=ledger, job=job)
    else:
        code("storage_error", enqueue, ledger=ledger)
    with database.connect(core.db_path) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM verification_requests").fetchone()[0] == (
            1 if job else 0
        )
        if job:
            assert db.execute("SELECT status,version FROM verification_jobs").fetchone()[:] == (
                "queued",
                1,
            )


def test_ledger_never_calls_git_or_docker_and_does_not_block_other_core_work(ledger, monkeypatch):
    core, service, (owner, _) = ledger

    def forbidden(*args, **kwargs):
        pytest.fail("Ledger invoked executable backend")

    monkeypatch.setattr(docker, "verify_python_json_lines", forbidden)
    monkeypatch.setattr(docker, "_run", forbidden)
    monkeypatch.setattr(snapshot, "export_candidate", forbidden)
    monkeypatch.setattr(core, "_workspace_store", forbidden)
    running = claim(ledger, enqueue(ledger))
    assert core.execute_owner("list_members", owner)["members"]
    assert service.list(**owner)["execution_assessment"] == "unverified"
    service.interrupt(**attempt_payload(running))


def _process_claim(data_dir, project_id, job_id, gate, results):
    try:
        service = VerificationJobs(Core(data_dir))
        gate.wait(15)
        service.claim(project_id=project_id, job_id=job_id, expected_version=1)
        results.put("winner")
    except AgentSyncError as error:
        results.put(error.code)


@pytest.mark.parametrize("mode", ["threads", "processes"])
def test_two_claimants_have_exactly_one_winner(ledger, mode):
    core, service, (owner, _) = ledger
    job = enqueue(ledger)
    if mode == "threads":

        def race(_):
            try:
                service.claim(project_id=owner["project_id"], job_id=job["id"], expected_version=1)
                return "winner"
            except AgentSyncError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(race, range(2)))
    else:
        context = multiprocessing.get_context("spawn")
        gate, results = context.Event(), context.Queue()
        children = [
            context.Process(
                target=_process_claim,
                args=(str(core.data_dir), owner["project_id"], job["id"], gate, results),
            )
            for _ in range(2)
        ]
        try:
            for child in children:
                child.start()
            gate.set()
            outcomes = [results.get(timeout=30) for _ in children]
            for child in children:
                child.join(30)
                assert child.exitcode == 0
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                child.join(5)
            results.close()
    assert sorted(outcomes) == ["version_conflict", "winner"]
    with database.connect(core.db_path) as db:
        assert db.execute("SELECT count(*) FROM verification_attempts").fetchone()[0] == 1


def test_schema_six_upgrade_preserves_all_existing_rows_and_failure_rolls_back(
    tmp_path, monkeypatch
):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript(database.SCHEMA)
        for version in range(2, 7):
            db.executescript(getattr(database, "MIGRATION_V" + str(version)))
        db.execute("INSERT INTO projects VALUES('p','old','/synthetic','owner-hash',1)")
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_search%' AND name NOT LIKE 'context_search%'"
            )
        ]
        before = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name in tables}
    migration = database.MIGRATION_V7
    monkeypatch.setattr(
        database, "MIGRATION_V7", migration + "; CREATE TABLE deliberately invalid syntax"
    )
    with pytest.raises(sqlite3.Error):
        database.migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 6
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE name='verification_jobs'"
        ).fetchone()
    monkeypatch.setattr(database, "MIGRATION_V7", migration)
    database.migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 16
        assert all(
            db.execute('SELECT * FROM "' + name + '"').fetchall() == rows
            for name, rows in before.items()
        )
        assert db.execute("SELECT count(*) FROM verification_jobs").fetchone()[0] == 0

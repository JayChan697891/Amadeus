"""Exact Git/SQLite acceptance; synthetic observations are explicitly separate from Docker."""

import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import drop_mock_workflow_schema, owner_grant
from test_candidate_execution import (
    JSON_LINES_CANDIDATE,
    actual_docker_image,
    actual_identity,
    attempt,
    protocol_candidate,
    safety_cleanup,
    synthetic_backend,
)
from test_candidate_jobs import owner, profile
from test_candidate_jobs import prepared as prepared
from test_candidate_jobs import world as world
from test_m4b_workspaces import git, source_fingerprint

import agentsync
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.sdk import AgentSyncClient
from agentsync.storage import database
from agentsync.storage.database import connect
from agentsync.verification import candidate_executor, candidate_jobs, task_completion
from agentsync.verification.candidate_jobs import CandidateVerificationJobs, _dump, _hash
from agentsync.verification.docker import DockerProfile, JsonCase
from agentsync.verification.task_completion import OwnerVerifiedTaskCompletion
from agentsync.workspaces.git import GitWorkspaceStore


def submit_pair(prepared, world):
    core = prepared[0]
    for tree, actor in zip(prepared[2:4], world[2], strict=True):
        claimed = core.execute(
            "claim_task",
            actor
            | {
                "task_id": tree["task_id"],
                "expected_version": 1,
                "request_id": "claim-" + tree["task_id"],
            },
        )
        submitted = core.execute(
            "update_task",
            actor
            | {
                "task_id": tree["task_id"],
                "expected_version": claimed["version"],
                "lease_token": claimed["lease_token"],
                "status": "review",
                "result": "asserted candidate",
                "request_id": "submit-" + tree["task_id"],
            },
        )
        assert submitted["version"] == 3 and submitted["task_verification"] == "unverified"


def reviewer(prepared):
    registered = prepared[0].execute(
        "register_agent", owner(prepared) | {"name": "Independent verifier"}
    )
    owner_grant(prepared[0], owner(prepared), registered, ("reviewer",))
    return {key: registered[key] for key in ("session_id", "session_token")}


def completion_args(prepared, args, executed, independent):
    return (
        owner(prepared)
        | independent
        | {
            "task_id": prepared[2]["task_id"],
            "expected_version": 3,
            "job_id": args["job_id"],
            "execution_id": executed["execution_id"],
            "expected_execution_revision": executed["execution"]["revision"],
            "request_id": "verified-completion",
            "profile": args["profile"],
        }
    )


@pytest.fixture
def ready(prepared, world, monkeypatch):
    submit_pair(prepared, world)
    independent = reviewer(prepared)
    executor, args, receipts = attempt(prepared)
    monkeypatch.setattr(candidate_executor, "verify_python_json_lines", synthetic_backend)
    executed = executor.execute_once(**args)
    assert executed["execution_assessment"] == "passed"
    return (
        prepared,
        OwnerVerifiedTaskCompletion(prepared[0]),
        completion_args(prepared, args, executed, independent),
        receipts,
    )


def state(core):
    with connect(core.db_path) as db:
        return {
            table: [tuple(row) for row in db.execute("SELECT * FROM " + table)]
            for table in (
                "tasks",
                "reviews",
                "task_verifications",
                "task_verification_requests",
            )
        }


def public_task(core, task_id):
    with connect(core.db_path) as db:
        return core._public_task(
            db, db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        )


def test_atomic_completion_reopen_replay_and_immutable_old_receipts(ready):
    prepared, complete, args, receipts = ready
    result = complete.complete_once(**args)
    assert result["task_verification"] == "verified" and result["version"] == 4
    assert result["current_state"] is False
    reopened = Core(prepared[0].data_dir)
    assert OwnerVerifiedTaskCompletion(reopened).complete_once(**args) == result
    assert public_task(reopened, args["task_id"])["verification"] == result["verification"]
    lookup = {key: args[key] for key in ("project_id", "admin_token", "task_id")}
    assert reopened.execute_owner("get_task_verification", lookup) == {
        "task_id": args["task_id"],
        "task_version": result["version"],
        "status": "completed",
        "task_verification": "verified",
        "verification": result["verification"],
    }
    assert public_task(reopened, prepared[3]["task_id"])["task_verification"] == "unverified"
    # The second side has a fresh target version but a stale paired version.
    with pytest.raises(AgentSyncError) as exc:
        complete.complete_once(
            **(args | {"task_id": prepared[3]["task_id"], "request_id": "other-side"})
        )
    assert exc.value.code == "stale_candidate_input"
    # Later task changes must not contaminate the historical completion receipt.
    with connect(reopened.db_path) as db:
        db.execute(
            "UPDATE tasks SET version=version+1,status='pending' WHERE id=?", (args["task_id"],)
        )
    assert public_task(reopened, args["task_id"])["task_verification"] == "unverified"
    current_proof = reopened.execute_owner("get_task_verification", lookup)
    assert current_proof["task_version"] == result["version"] + 1
    assert current_proof["task_verification"] == "unverified"
    assert current_proof["verification"] is None
    assert complete.complete_once(**args) == result
    assert (
        CandidateVerificationJobs(reopened).enqueue(
            **prepared[1], request_id="enqueue", profile=args["profile"]
        )
        == receipts[0]
    )
    with connect(reopened.db_path) as db:
        assert db.execute("SELECT count(*) FROM reviews").fetchone()[0] == 1
        events = db.execute(
            "SELECT actor_kind,operation FROM audit_events WHERE operation='task_verified_complete' AND outcome='success'"
        ).fetchall()
        assert sorted(tuple(row) for row in events) == [
            ("agent", "task_verified_complete"),
            ("owner", "task_verified_complete"),
        ]


def approve_delivery(prepared, requester, completed):
    core, candidate = prepared[:2]
    approval = core.execute(
        "request_approval",
        {
            **requester,
            "action": "apply_merge_candidate",
            "subject_id": candidate["candidate_id"],
            "subject_sha": candidate["expected_candidate_sha"],
            "request_id": "fixture-delivery-approval",
        },
    )
    lookup = {**owner(prepared), "approval_id": approval["id"]}
    payload = {
        **lookup,
        "expected_version": approval["version"],
        "task_id": completed["task_id"],
        "expected_task_version": completed["version"],
        "session_id": requester["session_id"],
        "session_token": requester["session_token"],
    }
    client = AgentSyncClient(core.data_dir)
    preview = client.owner_call("preview_candidate_delivery", **payload)["data"]
    plan = preview["plan"]
    assert plan["candidate_sha"] == candidate["expected_candidate_sha"]
    assert plan["destination_ref"].startswith("refs/agentsync/deliveries/")
    denied = client.owner_call("approve_candidate_delivery", **payload, plan_sha256="0" * 64)
    assert denied["error"]["code"] == "delivery_plan_changed"
    approved = client.owner_call(
        "approve_candidate_delivery",
        **payload,
        plan_sha256=preview["plan_sha256"],
    )["data"]
    publish = {
        **payload,
        "expected_version": approved["approval"]["version"],
        "plan_sha256": preview["plan_sha256"],
    }
    return lookup, plan, publish


def test_verified_candidate_delivery_is_create_only_and_uses_the_exact_approved_plan(
    ready, world, monkeypatch
):
    prepared, complete, args, _ = ready
    core, source = prepared[0], world[3]
    (source / "left.txt").write_text("staged fixture change\n", encoding="utf-8")
    git(source, "add", "left.txt")
    (source / "right.txt").write_text("unstaged fixture change\n", encoding="utf-8")
    (source / "private.txt").write_text("untracked fixture change\n", encoding="utf-8")
    original = source_fingerprint(source)
    completed = complete.complete_once(**args)
    client = AgentSyncClient(core.data_dir)
    operation = "publish_candidate_delivery"
    lookup, plan, publish = approve_delivery(prepared, world[2][0], completed)
    approved = {"plan": plan, "approval_status": "approved", "effect": "not_attempted"}
    writes = []
    original_git = GitWorkspaceStore._git

    def record_git(store, cwd, *argv, **kwargs):
        if argv[0] == "update-ref":
            writes.append((cwd, argv))
        return original_git(store, cwd, *argv, **kwargs)

    monkeypatch.setattr(GitWorkspaceStore, "_git", record_git)
    assert client.call(operation, **publish)["error"]["code"] == "unknown_operation"
    assert (
        client.owner_call(operation, **(publish | {"admin_token": "wrong"}))["error"]["code"]
        == "unauthorized"
    )
    for changes in (
        {"expected_version": publish["expected_version"] - 1},
        {"expected_task_version": publish["expected_task_version"] - 1},
        {"plan_sha256": "0" * 64},
    ):
        denied = client.owner_call(operation, **(publish | changes))
        assert denied["error"]["code"] == "delivery_plan_changed"
    with monkeypatch.context() as patch:
        patch.setattr(candidate_jobs, "time", SimpleNamespace(time=lambda: plan["expires_at"]))
        denied = client.owner_call(operation, **publish)
        assert denied["error"]["code"] == "delivery_plan_changed"
        assert client.owner_call("get_candidate_delivery_status", **lookup)["data"] == (
            approved | {"approval_status": "expired"}
        )
    assert client.owner_call("get_candidate_delivery_status", **lookup)["data"] == approved
    assert writes == []

    result = client.owner_call(operation, **publish)["data"]
    assert result == {"plan": plan, "approval_status": "consumed", "effect": "exact"}
    (write,) = writes
    repo, argv = write
    assert repo.is_relative_to(core.data_dir)
    assert argv == (
        "update-ref",
        "--no-deref",
        plan["destination_ref"],
        plan["candidate_sha"],
        "0" * len(plan["candidate_sha"]),
    )
    assert git(repo, "rev-parse", plan["destination_ref"]) == plan["candidate_sha"]
    assert client.owner_call(operation, **publish)["error"]["code"] == "delivery_plan_changed"
    reopened = AgentSyncClient(core.data_dir)
    assert reopened.owner_call("get_candidate_delivery_status", **lookup)["data"] == result
    assert writes == [write]
    assert source_fingerprint(source) == original


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "token",
        "role",
        "expiry",
        "author",
        "same_agent_new_session",
        "left_version",
        "right_version",
        "profile",
        "revision",
        "failed",
        "result_hash",
        "source_removed",
    ],
)
def test_failclosed_current_authority_binding_and_execution(ready, world, monkeypatch, fault):
    prepared, complete, args, _ = ready
    if fault == "owner":
        args["admin_token"] = "wrong"
    elif fault == "token":
        args["session_token"] = "wrong"
        args["job_id"] = "nonexistent-job"
        monkeypatch.setattr(
            complete.jobs,
            "_row",
            lambda *_: pytest.fail("Job lookup preceded reviewer authentication"),
        )
    elif fault in {"author", "same_agent_new_session"}:
        args.update({key: world[2][0][key] for key in ("session_id", "session_token")})
        if fault == "same_agent_new_session":
            with connect(prepared[0].db_path) as db:
                original = db.execute(
                    "SELECT * FROM sessions WHERE id=?", (args["session_id"],)
                ).fetchone()
                args["session_id"] = "another-author-session"
                db.execute(
                    "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                    (
                        args["session_id"],
                        original["project_id"],
                        original["agent_id"],
                        original["token_hash"],
                        original["created_at"],
                        original["heartbeat_at"],
                        original["expires_at"],
                    ),
                )
    elif fault == "profile":
        args["profile"] = profile(False)
    elif fault == "revision":
        args["expected_execution_revision"] += 1
    else:
        with connect(prepared[0].db_path) as db:
            if fault == "role":
                db.execute(
                    "UPDATE agent_memberships SET roles='[\"viewer\"]' WHERE agent_id=(SELECT agent_id FROM sessions WHERE id=?)",
                    (args["session_id"],),
                )
            elif fault == "expiry":
                db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (args["session_id"],))
            elif fault in {"left_version", "right_version"}:
                db.execute(
                    "UPDATE tasks SET version=version+1 WHERE id=?",
                    (prepared[2 if fault == "left_version" else 3]["task_id"],),
                )
            elif fault == "failed":
                db.execute(
                    "UPDATE candidate_executions SET assessment='failed' WHERE id=?",
                    (args["execution_id"],),
                )
            elif fault == "result_hash":
                db.execute(
                    "UPDATE candidate_executions SET result_sha256=? WHERE id=?",
                    ("a" * 64, args["execution_id"]),
                )
            elif fault == "source_removed":
                # The export's filesystem check must fail even though DB pins remain intact.
                receipt = json.loads(
                    db.execute("SELECT receipt FROM merge_candidates").fetchone()[0]
                )
                path = Path(receipt["candidate_path"])
                path.rename(path.with_name(path.name + "-removed"))
    before = state(prepared[0])
    with pytest.raises(AgentSyncError):
        complete.complete_once(**args)
    assert state(prepared[0]) == before


@pytest.mark.parametrize("fault", ["owner", "role", "expiry", "token", "request_conflict"])
def test_auth_and_conflict_before_historical_replay(ready, fault):
    prepared, complete, args, _ = ready
    complete.complete_once(**args)
    if fault == "owner":
        args["admin_token"] = "wrong"
    elif fault == "token":
        args["session_token"] = "wrong"
    elif fault == "request_conflict":
        args["expected_version"] = 2
    else:
        with connect(prepared[0].db_path) as db:
            if fault == "role":
                db.execute(
                    "UPDATE agent_memberships SET roles='[]' WHERE agent_id=(SELECT agent_id FROM sessions WHERE id=?)",
                    (args["session_id"],),
                )
            else:
                db.execute("UPDATE sessions SET expires_at=0 WHERE id=?", (args["session_id"],))
    with pytest.raises(AgentSyncError):
        complete.complete_once(**args)


def test_concurrent_requests_commit_once_and_audit_failure_rolls_back(ready, monkeypatch):
    prepared, complete, args, _ = ready
    original = prepared[0]._audit_event

    def fail(*a, **k):
        if a[4] == "task_verified_complete" and a[2] == "agent":
            raise sqlite3.OperationalError("injected audit failure")
        return original(*a, **k)

    before = state(prepared[0])
    monkeypatch.setattr(prepared[0], "_audit_event", fail)
    with pytest.raises(AgentSyncError):
        complete.complete_once(**args)
    assert state(prepared[0]) == before
    monkeypatch.setattr(prepared[0], "_audit_event", original)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: complete.complete_once(**args), range(2)))
    assert results[0] == results[1]
    with connect(prepared[0].db_path) as db:
        assert db.execute("SELECT count(*) FROM task_verifications").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT count(*) FROM audit_events WHERE operation='task_verified_complete' AND outcome='success'"
            ).fetchone()[0]
            == 2
        )


def test_completed_proof_review_and_result_corruption_reject_projection_and_replay(ready):
    prepared, complete, args, _ = ready
    complete.complete_once(**args)
    corruptions = (
        ("task_verifications", "proof_sha256", "0" * 64),
        ("reviews", "evidence", "forged-text"),
        ("task_verification_requests", "response_sha256", "0" * 64),
        ("candidate_executions", "result_json", None),
    )
    for table, field, replacement in corruptions:
        with connect(prepared[0].db_path) as db:
            original = db.execute("SELECT " + field + " FROM " + table).fetchone()[0]
            if replacement is None:
                malformed = json.loads(original)
                malformed["isolation"] = None
                replacement = _dump(malformed)
            db.execute("UPDATE " + table + " SET " + field + "=?", (replacement,))
            if table == "candidate_executions":
                db.execute("UPDATE candidate_executions SET result_sha256=?", (_hash(replacement),))
        if table != "task_verification_requests":
            with pytest.raises(AgentSyncError):
                public_task(prepared[0], args["task_id"])
        with pytest.raises(AgentSyncError):
            complete.complete_once(**args)
        with connect(prepared[0].db_path) as db:
            db.execute("UPDATE " + table + " SET " + field + "=?", (original,))
            if table == "candidate_executions":
                db.execute("UPDATE candidate_executions SET result_sha256=?", (_hash(original),))
    assert public_task(prepared[0], args["task_id"])["task_verification"] == "verified"


@pytest.mark.parametrize("phase", ["export", "audit", "replay"])
def test_expiry_during_work_or_replay_rechecks_authority_and_rolls_back(ready, monkeypatch, phase):
    prepared, complete, args, _ = ready
    if phase == "replay":
        complete.complete_once(**args)
    before = state(prepared[0])
    with connect(prepared[0].db_path) as db:
        expiry = db.execute(
            "SELECT expires_at FROM sessions WHERE id=?", (args["session_id"],)
        ).fetchone()[0]
    original_time = task_completion.clock.time.time
    current_time = [original_time()]
    monkeypatch.setattr(
        task_completion,
        "clock",
        SimpleNamespace(time=SimpleNamespace(time=lambda: max(current_time[0], original_time()))),
    )
    if phase == "export":
        original = task_completion.OwnerCandidateExporter.export

        def export(*a, **k):
            result = original(*a, **k)
            current_time[0] = expiry
            return result

        monkeypatch.setattr(task_completion.OwnerCandidateExporter, "export", export)
    elif phase == "audit":
        original = prepared[0]._audit_event

        def audit(*a, **k):
            result = original(*a, **k)
            if a[4] == "task_verified_complete" and a[2] == "agent":
                current_time[0] = expiry
            return result

        monkeypatch.setattr(prepared[0], "_audit_event", audit)
    else:
        original = task_completion._proof

        def proof(*a, **k):
            result = original(*a, **k)
            current_time[0] = expiry
            return result

        monkeypatch.setattr(task_completion, "_proof", proof)
    with pytest.raises(AgentSyncError) as exc:
        complete.complete_once(**args)
    assert exc.value.code == "session_expired"
    assert state(prepared[0]) == before


def test_text_review_and_legacy_cached_response_remain_unverified(prepared, world):
    submit_pair(prepared, world)
    independent = reviewer(prepared)
    args = {
        "project_id": prepared[1]["project_id"],
        **independent,
        "task_id": prepared[2]["task_id"],
        "expected_version": 3,
        "accept": True,
        "evidence": "only a textual assertion",
        "request_id": "legacy-review",
    }
    response = prepared[0].execute("review_task", args)
    assert response["task_verification"] == "unverified"
    with connect(prepared[0].db_path) as db:
        cached = json.loads(
            db.execute("SELECT response FROM idempotency WHERE operation='review_task'").fetchone()[
                0
            ]
        )
        cached.pop("task_verification")
        cached.pop("verification")
        db.execute(
            "UPDATE idempotency SET response=? WHERE operation='review_task'", (json.dumps(cached),)
        )
    assert prepared[0].execute("review_task", args)["task_verification"] == "unverified"


def test_schema13_upgrade_preserves_history_and_atomic_migration_rollback(ready, monkeypatch):
    prepared, _, _, _ = ready
    with connect(prepared[0].db_path) as db:
        drop_mock_workflow_schema(db)
        db.execute("DROP TABLE project_usage")
        db.execute("DROP TABLE task_verification_requests")
        db.execute("DROP TABLE task_verifications")
        db.execute("DROP INDEX completion_execution_binding")
        db.execute("PRAGMA user_version=13")
        before = {
            name: [tuple(row) for row in db.execute("SELECT * FROM " + name)]
            for name in (
                "tasks",
                "reviews",
                "candidate_executions",
                "candidate_verification_requests",
            )
        }
    migration = database.MIGRATION_V14
    monkeypatch.setattr(database, "MIGRATION_V14", migration + "; INVALID SQL")
    with pytest.raises(sqlite3.Error):
        database.migrate(prepared[0].db_path)
    with connect(prepared[0].db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 13
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE name='task_verifications'").fetchone()
            is None
        )
    monkeypatch.setattr(database, "MIGRATION_V14", migration)
    database.migrate(prepared[0].db_path)
    with connect(prepared[0].db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        assert all(
            [tuple(row) for row in db.execute("SELECT * FROM " + name)] == rows
            for name, rows in before.items()
        )
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_actual_linux_docker_to_independent_verified_completion(world):
    policy = DockerProfile(actual_docker_image(), (JsonCase(None, "candidate"),))
    prepared = protocol_candidate(world, JSON_LINES_CANDIDATE)
    submit_pair(prepared, world)
    independent = reviewer(prepared)
    executor, args, receipts = attempt(prepared, policy)
    observation = {"real_docker": True, "real_clients": "NOT RUN"}
    try:
        executed = executor.execute_once(**args)
        assert executed["execution_assessment"] == "passed"
        complete_args = completion_args(prepared, args, executed, independent)
        receipt = OwnerVerifiedTaskCompletion(prepared[0]).complete_once(**complete_args)
        current = public_task(prepared[0], complete_args["task_id"])
        assert current["task_verification"] == "verified" and current["version"] == 4
        assert receipt["verification"] == current["verification"]
        assert receipt["verification"]["candidate_sha"] == receipts[0]["candidate_sha"]
        observation.update(receipt=receipt, current=current, execution=executed)
        source = world[3]
        original = source_fingerprint(source)
        lookup, plan, publish = approve_delivery(prepared, world[2][0], receipt)
        core = prepared[0]
        cli = subprocess.run(
            [
                sys.executable,
                "-s",
                "-B",
                "-m",
                "agentsync",
                "--data-dir",
                str(core.data_dir),
                "owner",
                "publish_candidate_delivery",
            ],
            cwd=core.data_dir,
            env=os.environ | {"PYTHONPATH": str(Path(agentsync.__file__).resolve().parents[1])},
            input=json.dumps(publish),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        for token in (publish["admin_token"], publish["session_token"]):
            assert token not in cli.stdout and token not in cli.stderr
        assert cli.returncode == 0, cli.stderr
        delivered = {"plan": plan, "approval_status": "consumed", "effect": "exact"}
        assert json.loads(cli.stdout) == {"ok": True, "data": delivered}
        reopened = AgentSyncClient(core.data_dir)
        assert reopened.owner_call("get_candidate_delivery_status", **lookup)["data"] == delivered
        assert source_fingerprint(source) == original
        observation["delivery"] = {
            "owner_cli_exit_code": cli.returncode,
            "result": delivered,
            "reopened_status_matches": True,
            "source_unchanged": True,
        }
    finally:
        with connect(prepared[0].db_path) as db:
            row = db.execute(
                "SELECT * FROM candidate_executions WHERE job_id=?", (args["job_id"],)
            ).fetchone()
            proofs = [dict(row) for row in db.execute("SELECT * FROM task_verifications")]
            requests = [dict(row) for row in db.execute("SELECT * FROM task_verification_requests")]
        cleanup = safety_cleanup(actual_identity(row))
        observation.update(
            fixture_safety_cleanup=cleanup, stored_verifications=proofs, stored_requests=requests
        )
        directory = os.environ.get("AGENTSYNC_TASK_COMPLETION_EVIDENCE_DIR")
        if directory:
            target = Path(directory)
            assert target.is_absolute()
            target.mkdir(parents=True, exist_ok=True)
            (target / "actual-verified-task-completion.json").write_text(
                json.dumps(observation, indent=2), encoding="utf-8"
            )
        assert cleanup["absence_observed"] is True

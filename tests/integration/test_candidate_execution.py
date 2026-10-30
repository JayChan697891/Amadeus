"""Real Git/SQLite plus explicitly synthetic backend observations; no real client."""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from test_candidate_claims import recover
from test_candidate_intents import abandon
from test_candidate_jobs import enqueue, owner, profile
from test_candidate_jobs import prepared as prepared
from test_candidate_jobs import world as world
from test_m4b_workspaces import call, capture, commit_edit, comparison, git, worktree

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage import database
from agentsync.storage.database import connect
from agentsync.verification import candidate_executor as module
from agentsync.verification import docker
from agentsync.verification.candidate_claims import OwnerCandidateClaims
from agentsync.verification.candidate_executor import OwnerCandidateExecutor
from agentsync.verification.candidate_intents import OwnerCandidateExecutionIntents
from agentsync.verification.candidate_jobs import CandidateVerificationJobs, _dump, _hash
from agentsync.verification.executor import ISOLATION_CHECKS


def attempt(prepared, policy=None):
    policy = policy or profile()
    job = enqueue(prepared, profile=policy)
    reserved = OwnerCandidateClaims(prepared[0]).claim_once(
        **owner(prepared), job_id=job["id"], expected_version=1, profile=policy
    )
    intent = OwnerCandidateExecutionIntents(prepared[0]).prepare_once(
        **owner(prepared), job_id=job["id"], expected_version=2, profile=policy
    )
    args = dict(
        **owner(prepared),
        job_id=job["id"],
        intent_id=intent["intent"]["id"],
        expected_job_version=2,
        expected_intent_revision=1,
        profile=policy,
    )
    return OwnerCandidateExecutor(prepared[0]), args, (job, reserved, intent)


def synthetic_backend(source, *, profile, input_sha256, commit_sha, tree_sha, _lifecycle):
    _lifecycle.before_create("a" * 32, "agentsync-verifier-" + "a" * 32)
    _lifecycle.created("c" * 64)
    _lifecycle.before_start()
    cases = [
        {"input": docker._json(case.input_json), "expected": docker._json(case.expected_json)}
        for case in profile.cases
    ]
    return docker.VerificationResult(
        "passed",
        dict(
            provenance="docker_black_box",
            backend="local-linux-docker",
            verifier_version=1,
            verifier_source_sha256=_hash(Path(docker.__file__).read_bytes()),
            execution_started=True,
            profile_id=profile.profile_id,
            profile_sha256=profile.sha256,
            cases_sha256=_hash(_dump(cases)),
            image_sha256=profile.image_id,
            input_sha256=input_sha256,
            source_sha256=_hash(source),
            commit_sha=commit_sha,
            tree_sha=tree_sha,
            expected_case_count=len(profile.cases),
            completed_case_count=len(profile.cases),
            checked_case_count=len(profile.cases),
            passed_case_count=len(profile.cases),
            candidate_exit_code=0,
            cleanup_confirmed=True,
            errors=[],
            container_id="c" * 64,
            isolation={"checks": dict.fromkeys(ISOLATION_CHECKS, True)},
        ),
    )


def current(executor, args):
    return executor.get(**{key: args[key] for key in ("project_id", "admin_token", "job_id")})


def assert_fenced(prepared, executor, args, receipts):
    with pytest.raises(AgentSyncError) as exc:
        executor.execute_once(**args)
    assert exc.value.code == "candidate_execution_exists"
    with pytest.raises(AgentSyncError) as exc:
        abandon(prepared, receipts[2])
    assert exc.value.code == "candidate_execution_exists"
    with pytest.raises(AgentSyncError) as exc:
        recover(prepared, receipts[1])
    assert exc.value.code == "candidate_execution_exists"


def test_actual_candidate_bytes_not_base_and_old_receipts_stay_immutable(prepared, monkeypatch):
    executor, args, receipts = attempt(prepared)
    seen = []

    def unexpected_quarantine(*_args):
        raise AssertionError("Synthetic success must not quarantine") from sys.exception()

    monkeypatch.setattr(executor, "_quarantine", unexpected_quarantine)

    def backend(source, **options):
        seen.append((source, options["commit_sha"]))
        assert source == b"def solve(x): return 'candidate'\n"
        assert options["commit_sha"] == receipts[0]["candidate_sha"] != prepared[2]["base_sha"]
        return synthetic_backend(source, **options)

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    result = executor.execute_once(**args)
    assert result["execution_assessment"] == "passed" and len(seen) == 1
    assert result["execution"]["result"]["execution_id"] == result["execution_id"]
    assert (
        result["execution"]["permanently_fenced"]
        and result["execution"]["task_verification"] == "unverified"
    )
    assert enqueue(prepared) == receipts[0]
    assert CandidateVerificationJobs(prepared[0]).get(**owner(prepared), job_id=args["job_id"])[
        "execution_connected"
    ]
    assert OwnerCandidateClaims(prepared[0]).get(**owner(prepared), job_id=args["job_id"])[
        "reservation"
    ]["execution_connected"]
    assert OwnerCandidateExecutionIntents(prepared[0]).get(
        **owner(prepared), job_id=args["job_id"]
    )["intent"]["execution_connected"]
    assert_fenced(prepared, executor, args, receipts)


@pytest.mark.parametrize(
    "fault", ["owner", "profile", "task", "candidate", "job_version", "intent_revision"]
)
def test_owner_and_stale_inputs_reject_before_backend(prepared, monkeypatch, fault):
    executor, args, _ = attempt(prepared)
    called = []
    monkeypatch.setattr(module, "verify_python_json_lines", lambda *_a, **_k: called.append(True))
    if fault == "owner":
        args["admin_token"] = "not-owner"
        monkeypatch.setattr(
            module.OwnerCandidateExporter,
            "export",
            lambda *_a, **_k: pytest.fail("Unauthenticated Git export"),
        )
    elif fault == "profile":
        args["profile"] = profile(False)
    elif fault in {"job_version", "intent_revision"}:
        args["expected_" + fault] += 1
    else:
        with connect(prepared[0].db_path) as db:
            job = db.execute(
                "SELECT * FROM candidate_verification_jobs WHERE id=?", (args["job_id"],)
            ).fetchone()
            if fault == "task":
                db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (job["left_task_id"],))
            else:
                receipt = json.loads(
                    db.execute(
                        "SELECT receipt FROM merge_candidates WHERE id=?", (job["candidate_id"],)
                    ).fetchone()[0]
                )
                receipt["candidate_sha"] = "f" * 40
                db.execute(
                    "UPDATE merge_candidates SET receipt=? WHERE id=?",
                    (json.dumps(receipt), job["candidate_id"]),
                )
    with pytest.raises(AgentSyncError):
        executor.execute_once(**args)
    assert not called
    with connect(prepared[0].db_path) as db:
        assert db.execute("SELECT count(*) FROM candidate_executions").fetchone()[0] == 0


def test_concurrent_execution_and_old_release_paths_allow_one_attempt(prepared, monkeypatch):
    executor, args, receipts = attempt(prepared)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def backend(source, **options):
        calls.append(True)
        entered.set()
        assert release.wait(10)
        return synthetic_backend(source, **options)

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(executor.execute_once, **args)
        try:
            assert entered.wait(10)
            second = pool.submit(executor.execute_once, **args)
            with pytest.raises(AgentSyncError) as error:
                second.result(timeout=10)
            assert error.value.code == "candidate_execution_exists"
            assert_fenced(prepared, executor, args, receipts)
        finally:
            release.set()
        assert first.result(timeout=10)["execution_assessment"] == "passed"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_sha",
        "forged_backend",
        "typed_count",
        "cleanup_unknown",
        "failed",
        "timeout",
        "expired",
    ],
)
def test_bad_failed_or_uncertain_results_never_pass_or_release(prepared, monkeypatch, fault):
    executor, args, receipts = attempt(prepared)

    def backend(source, **options):
        result = synthetic_backend(source, **options)
        evidence = result.evidence.copy()
        status = result.status
        if fault == "wrong_sha":
            evidence["commit_sha"] = "f" * 40
        elif fault == "forged_backend":
            evidence["backend"] = "candidate-assertion"
        elif fault == "typed_count":
            evidence["checked_case_count"] = True
        elif fault == "cleanup_unknown":
            evidence["cleanup_confirmed"] = False
        elif fault == "failed":
            status = "failed"
            evidence["errors"] = ["case_mismatch"]
        elif fault == "timeout":
            status = "failed"
            evidence["errors"] = ["timeout"]
        else:
            with connect(prepared[0].db_path) as db:
                deadline = db.execute(
                    "SELECT lease_expires_at FROM candidate_verification_claims"
                ).fetchone()[0]
            monkeypatch.setattr(module.queue_module.time, "time", lambda: deadline + 1)
        return docker.VerificationResult(status, evidence)

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    result = executor.execute_once(**args)
    assert result["execution_assessment"] == ("failed" if fault == "failed" else "unverified")
    assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


def test_cancel_between_create_intent_and_ack_retains_id_and_cleanup_is_one_shot(
    prepared, monkeypatch
):
    executor, args, receipts = attempt(prepared)

    def backend(_source, *, _lifecycle, **_options):
        _lifecycle.before_create("a" * 32, "agentsync-verifier-" + "a" * 32)
        view = current(executor, args)
        executor.cancel(
            **owner(prepared),
            job_id=args["job_id"],
            execution_id=view["execution_id"],
            expected_revision=view["execution"]["revision"],
        )
        _lifecycle.created("c" * 64)
        with pytest.raises(AgentSyncError) as error:
            _lifecycle.before_start()
        assert error.value.code == "execution_cancelled"
        return docker.VerificationResult(
            "error", {"cleanup_confirmed": False, "errors": ["owner_cancelled"]}
        )

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    result = executor.execute_once(**args)
    assert result["execution_assessment"] == "unverified"
    assert (
        result["execution"]["container_id"] == "c" * 64 and not result["execution"]["start_intent"]
    )
    with connect(prepared[0].db_path) as db:
        deadline = db.execute(
            "SELECT lease_expires_at FROM candidate_verification_claims"
        ).fetchone()[0]
    monkeypatch.setattr(module.queue_module.time, "time", lambda: deadline + 1)
    observed = []

    def cleanup(identity):
        observed.append(identity)
        assert identity == dict(
            container_id="c" * 64,
            container_name="agentsync-verifier-" + "a" * 32,
            owner_nonce="a" * 32,
            image_id=args["profile"].image_id,
        )
        return {
            "outcome": "removed_and_absent",
            "identity_matched": True,
            "remove_acknowledged": True,
            "absence_observed": True,
            "daemon_consistent": True,
        }

    monkeypatch.setattr(module, "_observation", cleanup)
    action = dict(
        **owner(prepared),
        job_id=args["job_id"],
        execution_id=result["execution_id"],
        expected_revision=result["execution"]["revision"],
    )
    result = executor.cleanup_once(**action)
    assert result["execution_assessment"] == "unverified" and len(observed) == 1
    action["expected_revision"] = result["execution"]["revision"]
    with pytest.raises(AgentSyncError):
        executor.cleanup_once(**action)
    assert_fenced(prepared, executor, args, receipts)


def test_lost_ack_has_no_name_based_cleanup_and_stays_fenced(prepared, monkeypatch):
    executor, args, receipts = attempt(prepared)

    def backend(_source, *, _lifecycle, **_options):
        _lifecycle.before_create("a" * 32, "agentsync-verifier-" + "a" * 32)
        raise RuntimeError("Synthetic lost create acknowledgement")

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    result = executor.execute_once(**args)
    assert result["execution"]["create_intent"] and not result["execution"]["container_id"]
    monkeypatch.setattr(
        module, "_observation", lambda *_: pytest.fail("Cleanup by name is forbidden")
    )
    with connect(prepared[0].db_path) as db:
        deadline = db.execute(
            "SELECT lease_expires_at FROM candidate_verification_claims"
        ).fetchone()[0]
    monkeypatch.setattr(module.queue_module.time, "time", lambda: deadline + 1)
    with pytest.raises(AgentSyncError) as error:
        executor.cleanup_once(
            **owner(prepared),
            job_id=args["job_id"],
            execution_id=result["execution_id"],
            expected_revision=result["execution"]["revision"],
        )
    assert error.value.code == "cleanup_identity_unavailable"
    assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


def test_cleanup_keeps_observation_when_expired_executor_returns(prepared, monkeypatch):
    executor, args, receipts = attempt(prepared)
    entered, release = threading.Event(), threading.Event()

    def backend(source, **options):
        result = synthetic_backend(source, **options)
        entered.set()
        assert release.wait(30)
        return result

    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(executor.execute_once, **args)
        try:
            assert entered.wait(30)
            with connect(prepared[0].db_path) as db:
                deadline = db.execute(
                    "SELECT lease_expires_at FROM candidate_verification_claims"
                ).fetchone()[0]
            monkeypatch.setattr(module.queue_module.time, "time", lambda: deadline + 1)
            view = current(executor, args)

            def observe(identity):
                assert identity["container_id"] == "c" * 64
                release.set()
                returned = running.result(timeout=30)
                assert returned["execution_assessment"] == "unverified"
                return {"outcome": "removed_and_absent", "absence_observed": True}

            monkeypatch.setattr(module, "_observation", observe)
            result = executor.cleanup_once(
                **owner(prepared),
                job_id=args["job_id"],
                execution_id=view["execution_id"],
                expected_revision=view["execution"]["revision"],
            )
        finally:
            release.set()
    assert result["execution"]["cleanup"]["status"] == "observed"
    assert result["execution"]["cleanup"]["observation"]["absence_observed"] is True
    assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


@pytest.mark.parametrize("phase", ["preparing", "executing"])
def test_commit_ack_loss_preserves_fence_before_next_external_step(prepared, monkeypatch, phase):
    executor, args, receipts = attempt(prepared)
    original_connect = module.queue_module.connect
    injected, backend_calls, continued = [], [], []

    class CommitAckLoss:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def commit(self):
            row = self.db.execute("SELECT phase FROM candidate_executions").fetchone()
            self.db.commit()
            if row is not None and row["phase"] == phase and not injected:
                injected.append(phase)
                raise sqlite3.OperationalError("Controlled lost commit acknowledgement")

    def backend(source, **options):
        backend_calls.append(True)
        result = synthetic_backend(source, **options)
        continued.append(True)
        return result

    monkeypatch.setattr(
        module.queue_module, "connect", lambda path: CommitAckLoss(original_connect(path))
    )
    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    if phase == "preparing":
        with pytest.raises(AgentSyncError) as error:
            executor.execute_once(**args)
        assert error.value.code == "storage_error"
        assert not backend_calls
    else:
        assert executor.execute_once(**args)["execution_assessment"] == "unverified"
        assert len(backend_calls) == 1
    assert injected == [phase] and not continued
    assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


@pytest.mark.parametrize("operation", ["candidate_execution_admit", "candidate_execution_finish"])
def test_audit_failure_rolls_back_and_never_grants_success(prepared, monkeypatch, operation):
    executor, args, receipts = attempt(prepared)
    original, calls = prepared[0]._audit_event, []

    def audit(db, project, actor_kind, actor, op, *rest):
        if op == operation:
            raise sqlite3.OperationalError("controlled audit failure")
        return original(db, project, actor_kind, actor, op, *rest)

    def backend(source, **options):
        calls.append(True)
        return synthetic_backend(source, **options)

    monkeypatch.setattr(prepared[0], "_audit_event", audit)
    monkeypatch.setattr(module, "verify_python_json_lines", backend)
    if operation == "candidate_execution_admit":
        with pytest.raises(AgentSyncError):
            executor.execute_once(**args)
        assert not calls
        with connect(prepared[0].db_path) as db:
            assert db.execute("SELECT count(*) FROM candidate_executions").fetchone()[0] == 0
    else:
        assert executor.execute_once(**args)["execution_assessment"] == "unverified"
        assert_fenced(prepared, executor, args, receipts)


def test_controlled_process_exit_after_create_fence_survives_reopen(prepared):
    executor, args, receipts = attempt(prepared)
    program = """import json,os,sys
from agentsync.core.service import Core
from agentsync.verification import candidate_executor as m
from agentsync.verification.docker import DockerProfile,JsonCase
p=json.load(sys.stdin);core=Core(p.pop('data_dir'));p['profile']=DockerProfile('sha256:'+'b'*64,(JsonCase(None,True),))
def backend(source,**options):
 options['_lifecycle'].before_create('a'*32,'agentsync-verifier-'+'a'*32)
 os._exit(86)
m.verify_python_json_lines=backend
m.OwnerCandidateExecutor(core).execute_once(**p)
"""
    payload = {key: value for key, value in args.items() if key != "profile"} | {
        "data_dir": str(prepared[0].data_dir)
    }
    result = subprocess.run(
        [sys.executable, "-c", program],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 86 and result.stdout == b""
    reopened = OwnerCandidateExecutor(Core(prepared[0].data_dir))
    view = current(reopened, args)
    assert (
        view["execution_assessment"] == "unverified"
        and view["execution"]["phase"] == "create_intent"
    )
    assert_fenced(prepared, reopened, args, receipts)


@pytest.mark.parametrize(
    "fault", ["project", "claim", "orphan", "float_count", "revision", "phase", "result"]
)
def test_all_current_readers_reject_corrupt_execution_relations(prepared, monkeypatch, fault):
    executor, args, _ = attempt(prepared)
    monkeypatch.setattr(module, "verify_python_json_lines", synthetic_backend)
    executor.execute_once(**args)
    with connect(prepared[0].db_path) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("PRAGMA ignore_check_constraints=ON")
        if fault == "project":
            db.execute("UPDATE candidate_executions SET project_id='foreign'")
        elif fault == "claim":
            db.execute("UPDATE candidate_executions SET claim_id='missing'")
        elif fault == "orphan":
            db.execute(
                "UPDATE candidate_executions SET job_id='missing',claim_id='missing',intent_id='missing'"
            )
        elif fault == "revision":
            db.execute("UPDATE candidate_executions SET revision=0")
        elif fault == "phase":
            db.execute("UPDATE candidate_executions SET phase='invented'")
        elif fault == "result":
            db.execute("UPDATE candidate_executions SET result_json='{}',result_sha256=NULL")
        else:
            proof = json.loads(
                db.execute("SELECT proof_json FROM candidate_executions").fetchone()[0]
            )
            proof["case_count"] = 1.0
            raw = _dump(proof)
            db.execute(
                "UPDATE candidate_executions SET proof_json=?,proof_sha256=?", (raw, _hash(raw))
            )
    for read in (
        lambda: current(executor, args),
        lambda: CandidateVerificationJobs(prepared[0]).get(
            **owner(prepared), job_id=args["job_id"]
        ),
        lambda: CandidateVerificationJobs(prepared[0]).list(**owner(prepared)),
        lambda: OwnerCandidateClaims(prepared[0]).get(**owner(prepared), job_id=args["job_id"]),
        lambda: OwnerCandidateExecutionIntents(prepared[0]).get(
            **owner(prepared), job_id=args["job_id"]
        ),
    ):
        with pytest.raises(AgentSyncError):
            read()


def test_schema12_upgrade_preserves_receipt_rows_and_missing_schema_fails_closed(
    prepared, monkeypatch
):
    _, args, receipts = attempt(prepared)
    tables = (
        "candidate_verification_jobs",
        "candidate_verification_requests",
        "candidate_verification_claims",
        "candidate_execution_intents",
    )
    with connect(prepared[0].db_path) as db:
        before = {
            name: [tuple(row) for row in db.execute("SELECT * FROM " + name)] for name in tables
        }
        db.execute("DROP TABLE task_verification_requests")
        db.execute("DROP TABLE task_verifications")
        db.execute("DROP TABLE candidate_executions")
        db.execute("PRAGMA user_version=12")
    database.migrate(prepared[0].db_path)
    with connect(prepared[0].db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 14
        assert {
            name: [tuple(row) for row in db.execute("SELECT * FROM " + name)] for name in tables
        } == before
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        db.execute("DROP TABLE candidate_executions")
    with pytest.raises(AgentSyncError):
        CandidateVerificationJobs(prepared[0]).get(**owner(prepared), job_id=args["job_id"])


@pytest.mark.skipif(
    sys.platform == "linux",
    reason="Actual Linux backend belongs to the separately controlled Docker fixture",
)
def test_unavailable_isolation_is_unsupported_without_host_execution(prepared, monkeypatch):
    executor, args, receipts = attempt(prepared)
    monkeypatch.setattr(
        docker, "_run", lambda *_a, **_k: pytest.fail("Unsupported host attempted Docker")
    )
    result = executor.execute_once(**args)
    assert result["execution_assessment"] == "unsupported"
    assert not result["execution"]["create_intent"] and not result["execution"]["start_intent"]
    assert_fenced(prepared, executor, args, receipts)


JSON_LINES_CANDIDATE = (
    b"import json,sys\nfor line in sys.stdin:\n json.loads(line)\n print(json.dumps('candidate'))\n"
)


def actual_docker_image():
    image = os.environ.get("AGENTSYNC_DOCKER_TEST_IMAGE")
    if not image or sys.platform != "linux":
        if os.environ.get("AGENTSYNC_REQUIRE_DOCKER_TESTS") == "1":
            pytest.fail("Required candidate Docker fixture unavailable")
        pytest.skip(
            "Requires separately controlled local Linux Docker and preloaded immutable image"
        )
    return image


def protocol_candidate(world, source):
    # Candidate bytes are committed/exported as data. Only the isolated verifier
    # executes them; the baseline has a different, valid JSON-lines answer.
    core, credentials, (a, b), root = world
    (root / "solution.py").write_bytes(JSON_LINES_CANDIDATE.replace(b"'candidate'", b"'base'"))
    git(root, "add", ".")
    git(root, "commit", "-m", "candidate protocol baseline")
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lh = commit_edit(left, "solution.py", source.decode())
    rh = commit_edit(right, "right.txt", "right changed\n")
    candidate = call(
        core, a, "prepare_merge_candidate", **comparison(left, right, lh, rh), request_id="protocol"
    )
    with connect(core.db_path) as db:
        receipt = json.loads(
            db.execute(
                "SELECT receipt FROM merge_candidates WHERE id=?", (candidate["candidate_id"],)
            ).fetchone()[0]
        )
    return (
        core,
        credentials
        | {
            "candidate_id": candidate["candidate_id"],
            "expected_candidate_sha": candidate["candidate_sha"],
        },
        left,
        right,
        receipt,
    )


def save_actual(scenario, observation, prepared, args):
    with connect(prepared[0].db_path) as db:
        stored = db.execute(
            "SELECT * FROM candidate_executions WHERE job_id=?", (args["job_id"],)
        ).fetchone()
    row = None if stored is None else dict(stored)
    if row is not None:
        row.pop("token_hash")
    observation["stored_execution"] = row
    directory = os.environ.get("AGENTSYNC_CANDIDATE_EXECUTOR_EVIDENCE_DIR")
    if directory:
        target = Path(directory)
        if not target.is_absolute():
            raise ValueError("Absolute evidence directory required")
        target.mkdir(parents=True, exist_ok=True)
        # Values come from public receipts and a row with its capability removed.
        (target / (scenario + ".json")).write_text(
            json.dumps(observation, indent=2), encoding="utf-8"
        )


def actual_identity(row):
    if row is None or not row["create_reply_complete"] or not row["container_id"]:
        return None
    identity = {key: row[key] for key in ("container_id", "container_name", "owner_nonce")}
    if not docker.CONTAINER_ID.fullmatch(identity["container_id"]):
        raise ValueError("Full owned container ID required")
    identity["image_id"] = json.loads(row["proof_json"])["image_id"]
    return identity


def actual_cli(arguments):
    # The test observes only its acknowledged full ID on the fixed local daemon,
    # using the same trusted CLI selection and empty config as the verifier.
    cli = docker._trusted_cli()
    with TemporaryDirectory(prefix="agentsync-candidate-test-config-") as config:
        env = {"PATH": "/usr/bin:/bin", "HOME": config, "LC_ALL": "C"}
        return docker._run(
            [cli, "--host", "unix:///var/run/docker.sock", "--config", config, *arguments],
            env,
            2,
            256 * 1024,
        )


def owned_container_state(identity):
    items = docker._inspect_json(actual_cli(["inspect", identity["container_id"]]))
    if not isinstance(items, list) or len(items) != 1:
        raise ValueError("Owned container inspection unavailable")
    item = items[0]
    if not (
        item.get("Id") == identity["container_id"]
        and item.get("Name") == "/" + identity["container_name"]
        and item.get("Image") == identity["image_id"]
        and item.get("Config", {}).get("Labels", {}).get(docker.LABEL) == identity["owner_nonce"]
    ):
        raise ValueError("Owned container inspection identity mismatch")
    return {
        "container_id": identity["container_id"],
        "identity_matched": True,
        "running": item.get("State", {}).get("Running") is True,
        "status": item.get("State", {}).get("Status"),
    }


def safety_cleanup(identity):
    if identity is None:
        return {"outcome": "identity_unavailable", "absence_observed": False}
    listed = actual_cli(
        [
            "container",
            "ls",
            "--all",
            "--no-trunc",
            "--filter",
            "id=" + identity["container_id"],
            "--format",
            "{{.ID}}",
        ]
    )
    if listed.returncode == 0 and not listed.stdout.strip():
        return {"outcome": "already_absent", "absence_observed": True}
    # This implementation checks full ID, nonce, name, image and daemon identity
    # before its single exact-ID removal, and checks absence afterwards.
    return module._observation(identity)


@contextmanager
def actual_attempt(world, source, policy, scenario):
    prepared = protocol_candidate(world, source)
    executor, args, receipts = attempt(prepared, policy)
    observation = {
        "schema": "agentsync.candidate-executor-observation.v1",
        "real_docker": True,
        "real_clients": "NOT RUN",
        "base_sha": prepared[2]["base_sha"],
        "expected_source_sha256": hashlib.sha256(source).hexdigest(),
        "current": None,
        "stored_execution": None,
        "historical_receipts": receipts,
    }
    try:
        yield prepared, executor, args, receipts, observation
    finally:
        with connect(prepared[0].db_path) as db:
            stored = db.execute(
                "SELECT * FROM candidate_executions WHERE job_id=?", (args["job_id"],)
            ).fetchone()
        row = None if stored is None else dict(stored)
        if row is not None:
            row.pop("token_hash")
        observation["stored_execution"] = row
        cleanup = {"outcome": "cleanup_error", "absence_observed": False}
        try:
            save_actual(scenario, observation, prepared, args)
        finally:
            # Evidence I/O failure must never bypass owned-container cleanup.
            try:
                cleanup = safety_cleanup(actual_identity(row))
            finally:
                observation["fixture_safety_cleanup"] = cleanup
                save_actual(scenario, observation, prepared, args)
        assert cleanup["absence_observed"] is True, "Owned fixture container remains unresolved"


def test_actual_linux_docker_executes_candidate_not_base(world):
    policy = docker.DockerProfile(actual_docker_image(), (docker.JsonCase(None, "candidate"),))
    scenario = "actual-candidate-execution"
    with actual_attempt(world, JSON_LINES_CANDIDATE, policy, scenario) as values:
        prepared, executor, args, receipts, observation = values
        result = executor.execute_once(**args)
        observation["current"] = result
        save_actual(scenario, observation, prepared, args)
        assert result["execution_assessment"] == "passed"
        evidence = result["execution"]["result"]
        assert evidence["commit_sha"] == receipts[0]["candidate_sha"] != prepared[2]["base_sha"]
        assert evidence["source_sha256"] == hashlib.sha256(JSON_LINES_CANDIDATE).hexdigest()
        assert evidence["cleanup_confirmed"] is True
        assert_fenced(prepared, executor, args, receipts)


def test_actual_linux_docker_wrong_result_fails_and_stays_fenced(world):
    policy = docker.DockerProfile(actual_docker_image(), (docker.JsonCase(None, "candidate"),))
    source = JSON_LINES_CANDIDATE.replace(b"'candidate'", b"'wrong'")
    scenario = "actual-candidate-wrong-result"
    with actual_attempt(world, source, policy, scenario) as values:
        prepared, executor, args, receipts, observation = values
        result = executor.execute_once(**args)
        observation["current"] = result
        save_actual(scenario, observation, prepared, args)
        assert result["execution_assessment"] == "failed"
        assert result["execution"]["phase"] == "finished"
        assert "case_mismatch" in result["execution"]["result"]["errors"]
        assert result["execution"]["result"]["cleanup_confirmed"] is True
        assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


def test_actual_linux_docker_timeout_is_unresolved_and_never_retried(world):
    policy = docker.DockerProfile(
        actual_docker_image(), (docker.JsonCase(None, "candidate"),), timeout_seconds=1
    )
    source = b"import time\ntime.sleep(30)\n"
    scenario = "actual-candidate-timeout"
    with actual_attempt(world, source, policy, scenario) as values:
        prepared, executor, args, receipts, observation = values
        result = executor.execute_once(**args)
        observation["current"] = result
        save_actual(scenario, observation, prepared, args)
        assert result["execution_assessment"] == "unverified"
        assert result["execution"]["phase"] == "unresolved"
        evidence = result["execution"]["result"]
        assert evidence["execution_started"] is True and "timeout" in evidence["errors"]
        assert evidence["source_sha256"] == hashlib.sha256(source).hexdigest()
        assert evidence["cleanup_confirmed"] is True
        assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


def test_actual_linux_docker_cancel_after_running_keeps_correct_result_unverified(world):
    policy = docker.DockerProfile(
        actual_docker_image(), (docker.JsonCase(None, "candidate"),), timeout_seconds=8
    )
    source = JSON_LINES_CANDIDATE.replace(b"import json,sys", b"import json,sys,time").replace(
        b" print(json.dumps", b" time.sleep(3)\n print(json.dumps"
    )
    scenario = "actual-candidate-running-cancel"
    with actual_attempt(world, source, policy, scenario) as values:
        prepared, executor, args, receipts, observation = values
        with ThreadPoolExecutor(1) as pool:
            running = pool.submit(executor.execute_once, **args)
            deadline = time.monotonic() + 12
            state = None
            try:
                while time.monotonic() < deadline and not running.done():
                    with connect(prepared[0].db_path) as db:
                        row = db.execute(
                            "SELECT * FROM candidate_executions WHERE job_id=?", (args["job_id"],)
                        ).fetchone()
                    identity = actual_identity(row)
                    if identity is not None:
                        state = owned_container_state(identity)
                        if state["running"]:
                            break
                    time.sleep(0.05)
                observation["running_observation"] = state
                save_actual(scenario, observation, prepared, args)
                assert state is not None and state["running"] is True
                view = current(executor, args)
                cancelled = executor.cancel(
                    **owner(prepared),
                    job_id=args["job_id"],
                    execution_id=view["execution_id"],
                    expected_revision=view["execution"]["revision"],
                )
                observation["cancel_receipt"] = cancelled
            finally:
                # Cancellation is cooperative: wait for the finite candidate and
                # verifier cleanup; no immediate-kill or server-cancel claim.
                result = running.result(timeout=45)
                observation["current"] = result
                save_actual(scenario, observation, prepared, args)
        assert result["execution_assessment"] == "unverified"
        assert result["execution"]["phase"] == "unresolved"
        assert result["execution"]["cancel_requested"] == 1
        evidence = result["execution"]["result"]
        assert evidence["passed_case_count"] == 1 and evidence["candidate_exit_code"] == 0
        assert evidence["cleanup_confirmed"] is True and not evidence["errors"]
        assert_fenced(prepared, OwnerCandidateExecutor(Core(prepared[0].data_dir)), args, receipts)


def test_actual_linux_docker_crash_after_created_reopens_and_cleans_exact_id(world, monkeypatch):
    policy = docker.DockerProfile(actual_docker_image(), (docker.JsonCase(None, "candidate"),))
    scenario = "actual-candidate-created-crash-cleanup"
    with actual_attempt(world, JSON_LINES_CANDIDATE, policy, scenario) as values:
        prepared, executor, args, receipts, observation = values
        program = """import json,os,sys
from agentsync.core.service import Core
from agentsync.verification import candidate_executor as m
from agentsync.verification.docker import DockerProfile,JsonCase
p=json.load(sys.stdin)
core=Core(p.pop('data_dir'))
p['profile']=DockerProfile(p.pop('image_id'),(JsonCase(None,'candidate'),))
original=m._Lifecycle.created
def committed_then_exit(self,container_id):
 original(self,container_id)
 os._exit(86)
m._Lifecycle.created=committed_then_exit
m.OwnerCandidateExecutor(core).execute_once(**p)
"""
        payload = {key: value for key, value in args.items() if key != "profile"} | {
            "data_dir": str(prepared[0].data_dir),
            "image_id": policy.image_id,
        }
        # Only interpreter/OS essentials and the trusted source import path are
        # inherited. Credentials travel via private stdin, never argv or output.
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
        env.update(
            PYTHONPATH=str(Path(module.__file__).resolve().parents[2]),
            PYTHONNOUSERSITE="1",
            PYTHONDONTWRITEBYTECODE="1",
        )
        child = subprocess.run(
            [sys.executable, "-c", program],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=45,
            env=env,
        )
        reopened = OwnerCandidateExecutor(Core(prepared[0].data_dir))
        view = current(reopened, args)
        with connect(prepared[0].db_path) as db:
            row = db.execute(
                "SELECT * FROM candidate_executions WHERE job_id=?", (args["job_id"],)
            ).fetchone()
            expires = db.execute(
                "SELECT lease_expires_at FROM candidate_verification_claims WHERE job_id=?",
                (args["job_id"],),
            ).fetchone()[0]
        observation.update(
            current=view,
            child_exit_code=child.returncode,
            child_stdout_bytes=len(child.stdout),
            child_stderr_bytes=len(child.stderr),
            created_container=owned_container_state(actual_identity(row)),
            controlled_clock={
                "scope": "service clock only",
                "lease_expires_at": expires,
                "now": expires + 1,
            },
        )
        save_actual(scenario, observation, prepared, args)
        assert child.returncode == 86 and not child.stdout and not child.stderr
        assert (
            view["execution"]["phase"] == "created" and view["execution"]["create_reply_complete"]
        )
        assert observation["created_container"]["running"] is False
        monkeypatch.setattr(module.queue_module.time, "time", lambda: expires + 1)
        action = dict(
            **owner(prepared),
            job_id=args["job_id"],
            execution_id=view["execution_id"],
            expected_revision=view["execution"]["revision"],
        )
        cleaned = reopened.cleanup_once(**action)
        observation["current"] = cleaned
        save_actual(scenario, observation, prepared, args)
        cleanup = cleaned["execution"]["cleanup"]
        assert cleanup["status"] == "observed"
        assert cleanup["container_id"] == row["container_id"]
        assert cleanup["observation"]["identity_matched"] is True
        assert cleanup["observation"]["absence_observed"] is True
        assert cleanup["observation"]["outcome"] == "removed_and_absent"
        assert cleanup["observation"]["remove_acknowledged"] is True
        assert cleanup["observation"]["daemon_consistent"] is True
        assert cleanup["observation"]["error_code"] == ""
        assert cleaned["execution_assessment"] == "unverified"
        action["expected_revision"] = cleaned["execution"]["revision"]
        with pytest.raises(AgentSyncError) as error:
            reopened.cleanup_once(**action)
        assert error.value.code == "cleanup_ineligible"
        assert_fenced(prepared, reopened, args, receipts)

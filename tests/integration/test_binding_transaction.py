"""Explicit internal transaction seam with actual SQLite/Git-generated records."""

import subprocess

import pytest
from test_candidate_binding_git_records import prepared as prepared
from test_candidate_binding_git_records import world as world

from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.binding import OwnerCandidateBindings


def arguments(prepared):
    return {
        **prepared[1],
        "candidate_id": prepared[7]["candidate_id"],
        "expected_candidate_sha": prepared[7]["candidate_sha"],
    }


def test_transaction_reads_uncommitted_task_version_and_preserves_rollback(prepared):
    core = prepared[0]
    service = OwnerCandidateBindings(core)
    args = arguments(prepared)
    baseline = service.capture(**args)
    with connect(core.db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (baseline.left_task_id,))
        actual = service._capture_in_transaction(db, **args)
        assert actual.left_task_version == baseline.left_task_version + 1
        assert actual.provenance_sha256 != baseline.provenance_sha256
        assert db.in_transaction
        db.rollback()
    assert service.capture(**args) == baseline


def test_caller_can_commit_after_helper_without_losing_own_writes(prepared):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    args = arguments(prepared)
    before = service.capture(**args)
    db = connect(core.db_path)
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (before.left_task_id,))
        actual = service._capture_in_transaction(db, **args)
        assert db.in_transaction
        assert (
            db.execute("SELECT version FROM tasks WHERE id=?", (before.left_task_id,)).fetchone()[0]
            == actual.left_task_version
        )
        db.commit()
    finally:
        db.close()
    assert service.capture(**args) == actual


def test_helper_reads_uncommitted_owner_revocation_without_rollback(prepared):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    args = arguments(prepared)
    before = service.capture(**args)
    with connect(core.db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE projects SET admin_hash=? WHERE id=?", ("0" * 64, args["project_id"]))
        with pytest.raises(AgentSyncError) as exc:
            service._capture_in_transaction(db, **args)
        assert exc.value.code == "unauthorized"
        assert db.in_transaction
        assert (
            db.execute(
                "SELECT admin_hash FROM projects WHERE id=?", (args["project_id"],)
            ).fetchone()[0]
            == "0" * 64
        )
        db.rollback()
    assert service.capture(**args) == before


def test_helper_requires_existing_transaction_without_starting_one(prepared):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    with connect(core.db_path) as db:
        assert not db.in_transaction
        with pytest.raises(AgentSyncError) as exc:
            service._capture_in_transaction(db, **arguments(prepared))
        assert exc.value.code == "transaction_required"
        assert not db.in_transaction
        assert db.execute("SELECT 1").fetchone()[0] == 1


def test_helper_validates_request_without_touching_transaction(prepared):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    with connect(core.db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        before = list(db.iterdump())
        with pytest.raises(AgentSyncError) as exc:
            service._capture_in_transaction(
                db, **(arguments(prepared) | {"expected_candidate_sha": "secret-sentinel"})
            )
        assert exc.value.code == "validation_error"
        assert "secret-sentinel" not in str(exc.value)
        assert db.in_transaction and list(db.iterdump()) == before
        db.rollback()


def test_helper_has_no_git_or_state_write_and_matches_public_capture(prepared, monkeypatch):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    args = arguments(prepared)
    expected = service.capture(**args)

    def forbidden(*args, **kwargs):
        pytest.fail("Metadata transaction must never invoke Git or a candidate process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    with connect(core.db_path) as db:
        db.execute("BEGIN")
        before = list(db.iterdump())
        assert service._capture_in_transaction(db, **args) == expected
        assert list(db.iterdump()) == before and db.in_transaction
        db.rollback()
    assert service.capture(**args) == expected


def test_helper_authenticates_before_candidate_lookup(prepared):
    core, service = prepared[0], OwnerCandidateBindings(prepared[0])
    with connect(core.db_path) as db:
        db.execute("BEGIN")
        with pytest.raises(AgentSyncError) as exc:
            service._capture_in_transaction(
                db,
                **(
                    arguments(prepared)
                    | {"candidate_id": "missing", "admin_token": "invalid-private-token"}
                ),
            )
        assert exc.value.code == "unauthorized"
        assert "invalid-private-token" not in str(exc.value)
        assert db.in_transaction
        db.rollback()

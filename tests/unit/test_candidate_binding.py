"""Synthetic SQLite receipt metadata fixtures; no actual Git verification."""

import json
from dataclasses import FrozenInstanceError

import pytest

from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.binding import CandidateBinding, OwnerCandidateBindings

SHA = "a" * 40


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    core = Core(tmp_path / "service")
    root = tmp_path / "root"
    root.mkdir()
    owner = core.execute("create_project", {"name": "metadata", "root_path": str(root)})
    actor = core.execute("register_agent", {**owner, "name": "synthetic"})
    core.execute_owner(
        "set_agent_roles",
        {
            **owner,
            "agent_id": actor["agent_id"],
            "roles": ["worker"],
            "expected_version": 1,
            "request_id": "roles",
        },
    )
    auth = {
        "project_id": owner["project_id"],
        "session_id": actor["session_id"],
        "session_token": actor["session_token"],
    }
    tasks = [
        core.execute("create_task", {**auth, "title": side, "request_id": side})["id"]
        for side in ("left", "right")
    ]
    sr = {
        "id": "snapshot",
        "operation": "capture",
        "base_sha": SHA,
        "repository_path": "metadata-only/repo",
        "root_identity": ["1", "2"],
        "config_sha256": "c" * 64,
    }
    lr = {
        "id": "left",
        "operation": "create",
        "snapshot_id": "snapshot",
        "task_id": tasks[0],
        "base_sha": SHA,
        "head_sha": SHA,
        "repository_path": sr["repository_path"],
        "repository_identity": sr["root_identity"],
        "config_sha256": sr["config_sha256"],
    }
    rr = {**lr, "id": "right", "task_id": tasks[1]}
    cr = {
        "operation": "candidate",
        "candidate_id": "candidate",
        "candidate_sha": "d" * 40,
        "base_sha": SHA,
        "left_sha": "e" * 40,
        "right_sha": "f" * 40,
        "input_binding": {
            "operation": "merge",
            "snapshot_id": "snapshot",
            "right_snapshot_id": "snapshot",
            "base_sha": SHA,
            "right_base_sha": SHA,
            "left_id": "left",
            "right_id": "right",
            "left": "e" * 40,
            "right": "f" * 40,
        },
    }
    project, session = owner["project_id"], actor["session_id"]
    with connect(core.db_path) as db:
        db.execute(
            "INSERT INTO repository_snapshots VALUES(?,?,?,?,?)",
            ("snapshot", project, session, 1, json.dumps(sr)),
        )
        for name, task, receipt in zip(("left", "right"), tasks, (lr, rr), strict=True):
            db.execute(
                "INSERT INTO managed_worktrees VALUES(?,?,?,?,?,?,?)",
                (name, project, "snapshot", task, session, 1, json.dumps(receipt)),
            )
        db.execute(
            "INSERT INTO merge_candidates VALUES(?,?,?,?,?,?,?)",
            ("candidate", project, "left", "right", session, 1, json.dumps(cr)),
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("Metadata capture must not construct a Git backend")

    monkeypatch.setattr(core, "_workspace_store", forbidden)
    return (
        core,
        OwnerCandidateBindings(core),
        {**owner, "candidate_id": "candidate", "expected_candidate_sha": "d" * 40},
    )


def capture(metadata, **extra):
    return metadata[1].capture(**(metadata[2] | extra))


def test_valid_frozen_stable_and_no_write(metadata):
    core, _, _ = metadata
    with connect(core.db_path) as db:
        before = list(db.iterdump())
    result = capture(metadata)
    assert result == capture(metadata)
    assert result.source_kind == "managed_merge_candidate_metadata"
    assert len(result.provenance_sha256) == 64 and len(result.receipts) == 4
    assert all(isinstance(receipt, str) for receipt in result.receipts)
    assert "admin_token" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.base_sha = "x"
    with connect(core.db_path) as db:
        assert before == list(db.iterdump())


@pytest.mark.parametrize(
    "extra,code",
    [
        ({"admin_token": "secret-sentinel"}, "unauthorized"),
        ({"project_id": "foreign"}, "unauthorized"),
        ({"candidate_id": "missing"}, "not_found"),
        ({"expected_candidate_sha": "b" * 40}, "version_conflict"),
        ({"expected_candidate_sha": "short"}, "validation_error"),
        ({"candidate_id": ""}, "validation_error"),
        ({"candidate_id": "x" * 201}, "validation_error"),
    ],
)
def test_safe_request_errors(metadata, extra, code):
    with pytest.raises(AgentSyncError) as exc:
        capture(metadata, **extra)
    assert exc.value.code == code
    assert "secret-sentinel" not in str(exc.value)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "{",
        '{"secret-sentinel":1,"secret-sentinel":2}',
        '{"x":NaN}',
        '{"x":1e999}',
        json.dumps({"x": "secret-sentinel" * 6000}),
        '{"x":' + "[" * 1100 + "0" + "]" * 1100 + "}",
    ],
    ids=["array", "null", "malformed", "duplicate", "nan", "overflow", "oversized", "deep"],
)
def test_invalid_receipts_fail_safely(metadata, raw):
    with connect(metadata[0].db_path) as db:
        db.execute("UPDATE merge_candidates SET receipt=?", (raw,))
    with pytest.raises(AgentSyncError) as exc:
        capture(metadata)
    assert exc.value.code == "invalid_candidate_binding"
    assert "secret-sentinel" not in str(exc.value)


@pytest.mark.parametrize(
    "table,key,value",
    [
        ("merge_candidates", "base_sha", "b" * 40),
        ("managed_worktrees", "snapshot_id", "foreign"),
        ("managed_worktrees", "task_id", "foreign"),
        ("managed_worktrees", "config_sha256", "a" * 64),
        ("repository_snapshots", "operation", "create"),
        ("merge_candidates", "input_binding", {}),
    ],
)
def test_receipt_relation_tampering(metadata, table, key, value):
    with connect(metadata[0].db_path) as db:
        row = db.execute(f"SELECT id,receipt FROM {table} LIMIT 1").fetchone()
        receipt = json.loads(row["receipt"])
        receipt[key] = value
        db.execute(f"UPDATE {table} SET receipt=? WHERE id=?", (json.dumps(receipt), row["id"]))
    with pytest.raises(AgentSyncError, match="Stored candidate metadata is invalid"):
        capture(metadata)


def test_task_version_changes_provenance_and_old_value_is_immutable(metadata):
    old = capture(metadata)
    with connect(metadata[0].db_path) as db:
        db.execute("UPDATE tasks SET version=version+1 WHERE id=?", (old.left_task_id,))
    new = capture(metadata)
    assert new.left_task_version == old.left_task_version + 1
    assert new.provenance_sha256 != old.provenance_sha256


def test_cross_project_linked_row_rejected(metadata):
    core = metadata[0]
    other_root = core.data_dir.parent / "other"
    other_root.mkdir()
    other = core.execute("create_project", {"name": "other", "root_path": str(other_root)})
    with connect(core.db_path) as db:
        db.execute(
            "UPDATE managed_worktrees SET project_id=? WHERE id='left'", (other["project_id"],)
        )
    with pytest.raises(AgentSyncError) as exc:
        capture(metadata)
    assert exc.value.code == "invalid_candidate_binding"


def test_metadata_seam_exists():
    assert CandidateBinding.__dataclass_params__.frozen
    assert callable(OwnerCandidateBindings.capture)

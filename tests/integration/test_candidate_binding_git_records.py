"""Metadata capture against actual prepared Git records; no content validation claim."""

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_m4b_workspaces import (
    call,
    capture,
    commit_edit,
    comparison,
    source_fingerprint,
    worktree,
)
from test_m4b_workspaces import world as world

from agentsync.verification.binding import OwnerCandidateBindings


def save_binding(binding, name):
    directory = os.environ.get("AGENTSYNC_BINDING_EVIDENCE_DIR")
    if not directory:
        return
    fields = dataclasses.asdict(binding)
    receipts = fields.pop("receipts")
    digest = fields.pop("provenance_sha256")
    provenance = {
        "schema": "agentsync.candidate-binding.v1",
        **fields,
        "receipt_sha256": [hashlib.sha256(r.encode()).hexdigest() for r in receipts],
    }
    encoded = json.dumps(
        provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    assert hashlib.sha256(encoded).hexdigest() == digest
    env_id = hashlib.sha256(sys.prefix.encode()).hexdigest()[:16]
    target = Path(directory) / env_id
    assert target.is_absolute()
    target.mkdir(parents=True, exist_ok=True)
    data = {
        "environment_id": env_id,
        "provenance": provenance,
        "provenance_sha256": digest,
        "actual_git_setup": True,
        "filesystem_verified": False,
        "execution_verified": False,
    }
    (target / (name + ".json")).write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def prepared(world):
    core, owner, (a, b), root = world
    snapshot = capture(world)
    left, right = worktree(world, snapshot, a), worktree(world, snapshot, b)
    lh = commit_edit(left, "left.txt", "left fixture change\n")
    rh = commit_edit(right, "right.txt", "right fixture change\n")
    candidate = call(
        core,
        a,
        "prepare_merge_candidate",
        **comparison(left, right, lh, rh),
        request_id="metadata-candidate",
    )
    return core, owner, a, root, snapshot, left, right, candidate, lh, rh


def test_actual_prepared_records_capture_metadata_without_git_or_state_changes(
    prepared, monkeypatch
):
    core, owner, _, _, snapshot, left, right, candidate, lh, rh = prepared
    before = source_fingerprint(core.data_dir / "managed-git")

    def forbidden(*args, **kwargs):
        pytest.fail("Metadata capture must never start Git, Docker or a candidate process")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    service = OwnerCandidateBindings(core)
    result = service.capture(
        **owner,
        candidate_id=candidate["candidate_id"],
        expected_candidate_sha=candidate["candidate_sha"],
    )
    assert result.source_kind == "managed_merge_candidate_metadata"
    assert result.candidate_sha == candidate["candidate_sha"]
    assert result.base_sha == snapshot["base_sha"] and result.candidate_sha != result.base_sha
    assert (result.left_sha, result.right_sha) == (lh, rh)
    assert (result.left_worktree_id, result.right_worktree_id) == (
        left["worktree_id"],
        right["worktree_id"],
    )
    assert result.snapshot_id == snapshot["snapshot_id"]
    assert (
        service.capture(
            **owner,
            candidate_id=candidate["candidate_id"],
            expected_candidate_sha=candidate["candidate_sha"],
        )
        == result
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.candidate_sha = "0" * 40
    assert source_fingerprint(core.data_dir / "managed-git") == before
    save_binding(result, "prepared-records")


def test_metadata_capture_does_not_attest_dirty_candidate_files(prepared):
    core, owner, _, _, _, _, _, candidate, _, _ = prepared
    service = OwnerCandidateBindings(core)
    args = {
        **owner,
        "candidate_id": candidate["candidate_id"],
        "expected_candidate_sha": candidate["candidate_sha"],
    }
    before = service.capture(**args)
    # Deliberately mutate only this fixture's candidate checkout. This DB-only
    # stage must make no assertion about its disk contents or cleanliness.
    import json

    from agentsync.storage.database import connect

    with connect(core.db_path) as db:
        receipt = json.loads(
            db.execute(
                "SELECT receipt FROM merge_candidates WHERE id=?", (candidate["candidate_id"],)
            ).fetchone()[0]
        )
    path = Path(receipt["candidate_path"]) / "uncommitted-fixture.txt"
    path.write_text("must be rejected by future Git bridge, not metadata capture\n")
    assert service.capture(**args) == before
    assert not hasattr(before, "source") and not hasattr(before, "assessment")
    assert len(before.provenance_sha256) == hashlib.sha256().digest_size * 2
    save_binding(before, "dirty-disk-not-attested")

"""Independent actual-Git queue corruption regressions; no candidate execution."""

import hashlib
import json
import subprocess

import pytest
from test_candidate_export import prepared as prepared
from test_candidate_export import world as world

from agentsync.errors import AgentSyncError
from agentsync.storage.database import connect
from agentsync.verification.candidate_jobs import CandidateVerificationJobs
from agentsync.verification.docker import DockerProfile, JsonCase


@pytest.mark.parametrize(
    ("column", "replacement"),
    [
        ("profile_sha256", "9" * 64),
        ("image_id", "sha256:" + "9" * 64),
        ("profile_kind", "different-valid-looking-profile"),
    ],
)
def test_single_profile_column_change_rejected_by_all_queue_read_paths(
    prepared, monkeypatch, column, replacement
):
    core, args = prepared[:2]
    service = CandidateVerificationJobs(core)
    policy = DockerProfile("sha256:" + "b" * 64, (JsonCase(None, True),))
    queued = service.enqueue(**args, profile=policy, request_id="original")
    auth = {key: args[key] for key in ("project_id", "admin_token")}
    assert service.get(**auth, job_id=queued["id"])["status"] == "queued"
    with connect(core.db_path) as db:
        db.execute(
            "UPDATE candidate_verification_jobs SET " + column + "=? WHERE id=?",
            (replacement, queued["id"]),
        )

    def forbidden(*args, **kwargs):
        pytest.fail("Queue corruption reads must not invoke Git or candidate processes")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    operations = [
        lambda: service.get(**auth, job_id=queued["id"]),
        lambda: service.list(**auth),
        lambda: service.cancel(
            **auth, job_id=queued["id"], expected_version=1, request_id="cancel-corrupt"
        ),
        lambda: service.enqueue(**args, profile=policy, request_id="original"),
    ]
    for operation in operations:
        with pytest.raises(AgentSyncError) as error:
            operation()
        assert error.value.code == "corrupt_candidate_queue"
    with connect(core.db_path) as db:
        assert tuple(
            db.execute(
                "SELECT status,version FROM candidate_verification_jobs WHERE id=?",
                (queued["id"],),
            ).fetchone()
        ) == ("queued", 1)
        assert db.execute("SELECT count(*) FROM candidate_verification_requests").fetchone()[0] == 1


def store_policy_fixture(core, job_id, envelope):
    """Craft storage-policy inputs; these mutations do not attest actual Git objects."""

    def canonical(value, ascii_only=False):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii_only)

    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    binding, snapshot = envelope["binding"], envelope["snapshot"]
    fields = {
        key: value for key, value in binding.items() if key not in {"receipts", "provenance_sha256"}
    }
    binding["provenance_sha256"] = digest(
        canonical(
            {
                "schema": "agentsync.candidate-binding.v1",
                **fields,
                "receipt_sha256": [digest(value) for value in binding["receipts"]],
            }
        )
    )
    snapshot["input_sha256"] = digest(
        canonical(
            {
                "format": "agentsync-candidate-v1",
                **{
                    key: snapshot[key]
                    for key in ("commit_sha", "tree_sha", "manifest", "source_sha256")
                },
            },
            True,
        )
    )
    envelope["provenance_sha256"] = digest(
        canonical(
            {
                "schema": "agentsync.candidate-input.v1",
                "source_kind": "managed_merge_candidate_input",
                "binding_sha256": binding["provenance_sha256"],
                **{
                    key: snapshot[key]
                    for key in ("commit_sha", "tree_sha", "input_sha256", "source_sha256")
                },
            }
        )
    )
    raw = canonical(envelope)
    with connect(core.db_path) as db:
        db.execute(
            "UPDATE candidate_verification_jobs SET metadata_json=?,metadata_sha256=?,"
            "binding_sha256=?,input_sha256=?,provenance_sha256=? WHERE id=?",
            (
                raw,
                digest(raw),
                binding["provenance_sha256"],
                snapshot["input_sha256"],
                envelope["provenance_sha256"],
                job_id,
            ),
        )


@pytest.mark.parametrize("boundary", ["files", "path", "receipt"])
def test_stored_metadata_policy_limits_at_bound_and_one_beyond(prepared, boundary):
    """Synthetic stored metadata policy, distinct from actual-Git export evidence."""
    core, args = prepared[:2]
    service = CandidateVerificationJobs(core)
    queued = service.enqueue(
        **args,
        profile=DockerProfile("sha256:" + "b" * 64, (JsonCase(None, True),)),
        request_id="boundary",
    )
    auth = {key: args[key] for key in ("project_id", "admin_token")}
    assert service.get(**auth, job_id=queued["id"])["status"] == "queued"
    with connect(core.db_path) as db:
        envelope = json.loads(
            db.execute(
                "SELECT metadata_json FROM candidate_verification_jobs WHERE id=?",
                (queued["id"],),
            ).fetchone()[0]
        )
    manifest = envelope["snapshot"]["manifest"]
    if boundary == "files":
        solution = next(entry for entry in manifest if entry[0] == "solution.py")
        manifest[:] = [[f"file{i:03d}", "1" * 40, 0] for i in range(255)] + [solution]
    elif boundary == "path":
        manifest.append(["a" * 4096, "1" * 40, 0])
        manifest.sort(key=lambda entry: entry[0].encode())
    else:
        receipt = json.loads(envelope["binding"]["receipts"][0])
        receipt["storage-policy-padding"] = ""
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        receipt["storage-policy-padding"] = "x" * (65536 - len(raw.encode()))
        envelope["binding"]["receipts"][0] = json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert len(envelope["binding"]["receipts"][0].encode()) == 65536
    store_policy_fixture(core, queued["id"], envelope)
    assert service.get(**auth, job_id=queued["id"])["status"] == "queued"
    if boundary == "files":
        manifest.append(["zz-over-limit", "1" * 40, 0])
    elif boundary == "path":
        next(entry for entry in manifest if len(entry[0]) == 4096)[0] += "a"
    else:
        envelope["binding"]["receipts"][0] += " "
        assert len(envelope["binding"]["receipts"][0].encode()) == 65537
    store_policy_fixture(core, queued["id"], envelope)
    with pytest.raises(AgentSyncError) as error:
        service.get(**auth, job_id=queued["id"])
    assert error.value.code == "corrupt_candidate_queue"

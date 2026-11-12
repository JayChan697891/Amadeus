"""Offline review declarations never stand in for actual client acceptance."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def review_tool(monkeypatch):
    tools = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    return importlib.import_module("release_review")


def member(root, identity, kind, data):
    name = identity + ".json"
    (root / name).write_bytes(data)
    return {
        "id": identity, "kind": kind, "path": name,
        "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
    }


@pytest.mark.parametrize(
    ("first_kind", "second_kind"),
    [
        ("component", "real_relay"),
        ("independent_review", "real_relay"),
        ("component", "codex"),
        ("codex", "claude_code"),
    ],
)
def test_review_rejects_relabelled_evidence_even_at_distinct_paths(
    review_tool, tmp_path, first_kind, second_kind,
):
    records = [
        member(tmp_path, "first", first_kind, b'{"fixture":1}'),
        member(tmp_path, "second", second_kind, b'{"fixture":1}'),
    ]
    with pytest.raises(ValueError, match="separate"):
        review_tool._checked_members(tmp_path, records)


def test_distinct_declarations_still_require_matching_bytes(review_tool, tmp_path):
    records = [
        member(tmp_path, "execution", "real_relay", b'{"fixture":"execution"}'),
        member(tmp_path, "review", "independent_review", b'{"fixture":"review"}'),
    ]
    assert set(review_tool._checked_members(tmp_path, records)) == {"execution", "review"}
    (tmp_path / "review.json").write_bytes(b'{"fixture":"edited"}')
    with pytest.raises(ValueError):
        review_tool._checked_members(tmp_path, records)


def test_relay_receipt_pins_frozen_source_and_distinct_client_identities(review_tool, tmp_path):
    commit = "a" * 40
    artifact = "b" * 64
    runs = [
        {
            "client": client,
            "client_version": "1.2.3+fixture",
            **{
                name: hashlib.sha256(f"{client}:{name}".encode()).hexdigest()
                for name in ("agent_sha256", "run_sha256", "session_sha256")
            },
        }
        for client in ("codex", "cursor")
    ]
    document = {
        "schema_version": 1, "kind": "real_relay", "commit_sha": commit,
        "runs": runs, "artifact_sha256": artifact,
    }
    record = member(tmp_path, "relay-fixture", "real_relay", json.dumps(document).encode())
    assert review_tool._execution_artifact_digest(tmp_path, record, commit) == artifact
    with pytest.raises(ValueError, match="reviewed client or source"):
        review_tool._execution_artifact_digest(tmp_path, record, "f" * 40)

    runs[1]["agent_sha256"] = runs[0]["agent_sha256"]
    duplicate = member(tmp_path, "duplicate-fixture", "real_relay", json.dumps(document).encode())
    with pytest.raises(ValueError, match="separate agent"):
        review_tool._execution_artifact_digest(tmp_path, duplicate, commit)


def test_prepared_receipt_uses_the_artifact_bytes_from_the_review_directory(review_tool, tmp_path):
    producer = importlib.import_module("release_execution_receipt")
    artifact_record = member(tmp_path, "artifact", "execution_artifact", b"fixture artifact")
    pin = {key: artifact_record[key] for key in ("path", "size", "sha256")}
    run = {
        "client": "codex", "client_version": "fixture-version",
        "agent_sha256": "1" * 64, "run_sha256": "2" * 64, "session_sha256": "3" * 64,
    }
    commit = "a" * 40
    declaration = {"artifact": pin, "runs": [run]}
    receipt = producer.prepare_execution_receipt(tmp_path, "codex", commit, declaration)
    record = member(tmp_path, "client", "codex", json.dumps(receipt).encode())
    assert review_tool._execution_artifact_digest(tmp_path, record, commit) == pin["sha256"]

    (tmp_path / pin["path"]).write_bytes(b"altered artifact")
    with pytest.raises(ValueError):
        producer.prepare_execution_receipt(tmp_path, "codex", commit, declaration)

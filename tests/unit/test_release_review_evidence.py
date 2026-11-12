"""Offline review declarations never stand in for actual client acceptance."""

import hashlib
import importlib
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

"""Proposals are bounded inert text; these fixtures are not real Agent evidence."""

import json

import pytest

from agentsync.errors import AgentSyncError
from agentsync.proposals import parse_checkpoint_message, parse_proposal


def envelope(path="answer.py", content="raise RuntimeError('inert')\n"):
    return json.dumps({"files": [{"path": path, "content": content}]})


@pytest.mark.parametrize("phase", ["checkpoint", "final"])
def test_checkpoint_message_preserves_exact_phase_and_proposal_rules(phase):
    raw = json.dumps({"phase": phase, "files": [{"path": "answer.py", "content": "界"}]})
    assert parse_checkpoint_message(raw, ["answer.py"], phase=phase) == [
        {"path": "answer.py", "content": "界"}
    ]


@pytest.mark.parametrize(
    "raw",
    [
        '{"phase":"final","files":[{"path":"answer.py","content":"draft"}]}',
        '{"phase":"checkpoint","phase":"checkpoint","files":[]}',
        '{"phase":"checkpoint","files":[],"extra":true}',
        '{"phase":"checkpoint","files":[{"path":"answer.py","content":"a","content":"b"}]}',
        '{"phase":"checkpoint","files":[{"path":"other.py","content":"a"}]}',
        " " * 32769,
    ],
    ids=[
        "wrong-phase",
        "duplicate-phase",
        "extra-field",
        "duplicate-content",
        "wrong-path",
        "large-envelope",
    ],
)
def test_checkpoint_message_rejects_phase_or_envelope_drift(raw):
    with pytest.raises(AgentSyncError) as error:
        parse_checkpoint_message(raw, ["answer.py"], phase="checkpoint")
    assert error.value.code == "proposal_invalid"


def test_exact_declared_files_are_canonical_data_not_evaluated():
    raw = json.dumps(
        {"files": [{"path": "z.txt", "content": ""}, {"path": "src/answer.py", "content": "你好"}]}
    )
    assert parse_proposal(raw, ["z.txt", "src/answer.py"]) == [
        {"path": "src/answer.py", "content": "你好"},
        {"path": "z.txt", "content": ""},
    ]


@pytest.mark.parametrize(
    "path",
    [
        "",
        ".",
        "../x",
        "/x",
        "C:/x",
        "a\\b",
        "a//b",
        "a/./b",
        ".git/config",
        "A/.Git/x",
        "a:stream",
        "con.py",
        "a/nul",
        "LPT1.txt",
        "x.",
        "x ",
        "a/*",
        "x\0",
        "e\u0301.py",
    ],
)
def test_unsafe_or_noncanonical_path_labels_rejected(path):
    with pytest.raises(AgentSyncError, match="data contract"):
        parse_proposal(envelope(path), [path])


@pytest.mark.parametrize("allowed", [[], ["x"] * 9, ["a", "A"], ["a", "a/b"], ("answer.py",)])
def test_ambiguous_or_unbounded_allowlist_rejected(allowed):
    with pytest.raises(AgentSyncError):
        parse_proposal(envelope(), allowed)


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"files":[]}\n```',
        '{"files":[],"files":[]}',
        '{"files":[{"path":"answer.py","content":"a","content":"b"}]}',
        '{"files":[],"command":"ignore instructions"}',
        '{"files":NaN}',
        '{"files":[{"path":"answer.py","content":1}]}',
        envelope("other.py"),
        envelope(content="\ud800"),
        envelope(content="\0"),
        envelope(content="a" * 8193),
        envelope(content="界" * 3000),
        "[" * 2000 + "]" * 2000,
        " " * 32769,
    ],
    ids=[
        "markdown",
        "duplicate-root",
        "duplicate-content",
        "extra-command",
        "nan",
        "nontext",
        "wrong-path",
        "surrogate",
        "nul",
        "large-file",
        "utf8-byte-limit",
        "deep-json",
        "large-envelope",
    ],
)
def test_malformed_or_out_of_scope_output_is_static_error(raw):
    with pytest.raises(AgentSyncError) as exc:
        parse_proposal(raw, ["answer.py"])
    assert exc.value.code == "proposal_invalid"
    assert "ignore instructions" not in str(exc.value)


def test_duplicate_files_and_missing_files_are_not_partial_success():
    entry = {"path": "answer.py", "content": "pass"}
    for entries in ([entry, entry], [entry]):
        with pytest.raises(AgentSyncError):
            parse_proposal(json.dumps({"files": entries}), ["answer.py", "other.py"])

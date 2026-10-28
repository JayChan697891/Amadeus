"""Offline CLI fixtures are caller-supplied protocol data, not real client runs."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools/inspect_codex_events.py"


def stream(message="Hello"):
    return "\n".join(
        json.dumps(event, ensure_ascii=False)
        for event in (
            {"type": "thread.started", "thread_id": "private-thread"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "m1", "type": "agent_message", "text": message},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 2},
            },
        )
    ).encode("utf-8")


def invoke(path, *options):
    return subprocess.run(
        [sys.executable, str(TOOL), "--input", str(path), *options],
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_cli_projects_fixture_with_explicit_unverified_scope(tmp_path):
    source = tmp_path / "events.jsonl"
    content = stream()
    source.write_bytes(content)
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    report = json.loads(result.stdout)
    assert report["schema"] == "agentsync.codex-event-inspection.v1"
    assert report["state"] == "succeeded"
    assert report["input_sha256"] == hashlib.sha256(content).hexdigest()
    assert report["thread_present"] is True
    assert report["event_count"] == 4
    assert report["item_event_count"] == 1
    assert report["non_message_item_event_count"] == 0
    assert report["exit_code"] == 0
    assert report["exit_code_provenance"] == "caller_provided"
    assert report["protocol_only"] is True
    assert report["provenance"] == "caller_supplied"
    assert report["real_client_verified"] is False
    assert report["execution_connected"] is False
    assert report["formal_acceptance"] is False
    assert report["verification"] == "unverified"
    assert report["billing_verified"] is False
    assert report["usage"] == {
        "input_tokens": 10,
        "cached_input_tokens": 3,
        "output_tokens": 2,
        "reasoning_output_tokens": None,
        "provenance": "caller_supplied",
        "billing_verified": False,
    }
    assert report["agent_messages"] == [
        {
            "utf8_size": 5,
            "sha256": "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969",
        }
    ]
    assert b"Hello" not in result.stdout
    assert b"private-thread" not in result.stdout
    assert result.stderr == b""


@pytest.mark.parametrize(
    "options,state,error,exit_code",
    [
        ((), "incomplete", "process_unknown", None),
        (("--exit-code", "7"), "failed", "process_failed", 7),
    ],
)
def test_protocol_parse_success_does_not_override_unknown_or_failed_process(
    tmp_path, options, state, error, exit_code
):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream())
    result = invoke(source, *options)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert (report["state"], report["error_code"], report["exit_code"]) == (state, error, exit_code)
    assert report["formal_acceptance"] is False


def test_messages_tools_and_errors_are_not_printed_as_raw_text(tmp_path):
    canary = "fixture-private-canary-123"
    source = tmp_path / f"{canary}.jsonl"
    events = [
        {"type": "thread.started", "thread_id": canary},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "m", "type": "agent_message", "text": "你好" + canary},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "c",
                "type": "command_execution",
                "command": canary,
                "aggregated_output": canary,
            },
        },
        {"type": "turn.failed", "error": {"message": canary}},
    ]
    source.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events), encoding="utf-8"
    )
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["state"] == "failed"
    assert report["error_code"] == "upstream_error"
    assert report["agent_messages"][0]["utf8_size"] == 6 + len(canary)
    assert report["usage"] is None
    assert report["non_message_item_event_count"] == 1
    assert canary.encode() not in result.stdout + result.stderr
    assert "你好".encode() not in result.stdout


def test_inspection_preserves_input_and_creates_no_sibling_files(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream())
    before = source.stat()
    original = source.read_bytes()
    listing = tuple(tmp_path.iterdir())
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0
    assert source.read_bytes() == original
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert tuple(tmp_path.iterdir()) == listing


@pytest.mark.parametrize("directory", [False, True])
def test_missing_or_nonfile_input_has_static_error_without_path(tmp_path, directory):
    source = tmp_path / "private-unreadable-name"
    if directory:
        source.mkdir()
    result = invoke(source)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == "input_unavailable"
    assert source.name.encode() not in result.stdout + result.stderr
    assert result.stderr == b""


@pytest.mark.parametrize(
    "content,error",
    [
        (b"\xffprivate-canary", "invalid_utf8"),
        (b"private-canary{", "validation_error"),
        (b"x" * (1024 * 1024 + 1), "input_too_large"),
    ],
    ids=["invalid-utf8", "invalid-json", "oversized"],
)
def test_invalid_input_is_bounded_and_reports_only_static_code(tmp_path, content, error):
    source = tmp_path / "private-input-name"
    source.write_bytes(content)
    result = invoke(source)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["error_code"] == error
    assert set(report) == {
        "schema",
        "protocol_only",
        "provenance",
        "real_client_verified",
        "execution_connected",
        "formal_acceptance",
        "verification",
        "billing_verified",
        "error_code",
    }
    assert b"private-" not in result.stdout + result.stderr
    assert result.stderr == b""


def test_unsupported_event_does_not_become_successful_execution(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_text('{"type":"unsupported-private-canary"}', encoding="utf-8")
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == "unsupported_event"
    assert b"private-canary" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "value", ["9223372036854775808", "-9223372036854775809", "private-bad-integer"]
)
def test_exit_status_arguments_use_bounded_integer_and_usage_exit(tmp_path, value):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream())
    result = invoke(source, "--exit-code", value)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"signed 64-bit integer" in result.stderr
    assert b"private-bad-integer" not in result.stderr


def test_missing_required_input_returns_usage_exit_without_inspection():
    result = subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, timeout=20, check=False
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"--input" in result.stderr

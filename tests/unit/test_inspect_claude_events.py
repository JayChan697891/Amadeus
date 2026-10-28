"""Offline CLI fixtures only; no actual Claude client or provider calls."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools/inspect_claude_events.py"


def stream(*, result_changes=None, assistant_stop=None):
    events = [{"type": "system", "subtype": "init", "session_id": "private-session"}]
    if assistant_stop is not None:
        events.append(
            {
                "type": "assistant",
                "session_id": "private-session",
                "message": {"content": [], "stop_reason": assistant_stop},
            }
        )
    events.append(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "session_id": "private-session",
            "result": "Hello",
            "usage": {"input_tokens": 2, "output_tokens": 3},
            **(result_changes or {}),
        }
    )
    return "\n".join(json.dumps(event, ensure_ascii=False) for event in events).encode("utf-8")


def invoke(path, *options):
    return subprocess.run(
        [sys.executable, str(TOOL), "--input", str(path), *options],
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_cli_summarizes_explicit_fixture_with_no_raw_text_or_verified_claims(tmp_path):
    source = tmp_path / "events.jsonl"
    raw = stream()
    source.write_bytes(raw)
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    report = json.loads(result.stdout)
    assert report["schema"] == "agentsync.claude-event-inspection.v1"
    assert report["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["state"] == "succeeded"
    assert report["session_present"] is True
    assert report["event_count"] == 2
    assert report["assistant_message_count"] == report["tool_block_count"] == 0
    assert report["result_text"] == {
        "utf8_size": 5,
        "sha256": "185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969",
    }
    assert report["usage"] == {
        "input_tokens": 2,
        "output_tokens": 3,
        "cache_read_input_tokens": None,
        "cache_creation_input_tokens": None,
        "provenance": "caller_supplied",
        "verification": "unverified",
        "billing_verified": False,
    }
    assert report["exit_code"] == 0
    assert report["exit_code_provenance"] == "caller_provided"
    assert report["protocol_only"] is True
    assert report["provenance"] == "caller_supplied"
    assert report["real_client_verified"] is report["execution_connected"] is False
    assert report["formal_acceptance"] is report["billing_verified"] is False
    assert report["verification"] == report["core_authorization"] == "unverified"
    assert b"Hello" not in result.stdout
    assert b"private-session" not in result.stdout
    assert result.stderr == b""


@pytest.mark.parametrize("directory", [False, True])
def test_missing_or_directory_input_has_static_unavailable_error(tmp_path, directory):
    source = tmp_path / "private-unavailable-fixture"
    if directory:
        source.mkdir()
    result = invoke(source)
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["error_code"] == "input_unavailable"
    assert report["formal_acceptance"] is False
    assert b"private-unavailable-fixture" not in result.stdout + result.stderr
    assert result.stderr == b""


@pytest.mark.parametrize(
    "content,error",
    [(b"\xffprivate-input", "invalid_utf8"), (b"private-input{", "validation_error")],
    ids=["invalid-utf8", "invalid-json"],
)
def test_malformed_input_has_static_code_without_raw_data_or_traceback(tmp_path, content, error):
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
        "core_authorization",
        "billing_verified",
        "error_code",
    }
    assert b"private-input" not in result.stdout + result.stderr
    assert result.stderr == b""


def test_oversized_explicit_input_is_rejected_before_protocol_parsing(tmp_path):
    source = tmp_path / "oversized.jsonl"
    source.write_bytes(b"x" * (1024 * 1024 + 1))
    result = invoke(source)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == "input_too_large"
    assert result.stderr == b""


@pytest.mark.parametrize(
    "value", ["9223372036854775808", "-9223372036854775809", "private-bad-integer"]
)
def test_invalid_exit_status_uses_static_usage_error(tmp_path, value):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream())
    result = invoke(source, "--exit-code", value)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"signed 64-bit integer" in result.stderr
    assert b"private-bad-integer" not in result.stderr


@pytest.mark.parametrize(
    "options,changes,assistant_stop,state,error",
    [
        ((), {}, None, "incomplete", "process_unknown"),
        (("--exit-code", "7"), {}, None, "failed", "process_failed"),
        (("--exit-code", "0"), {"is_error": True}, None, "failed", "upstream_error"),
        (("--exit-code", "0"), {}, "max_tokens", "incomplete", "incomplete_response"),
        (("--exit-code", "0"), {}, "refusal", "incomplete", "incomplete_response"),
        (("--exit-code", "0"), {}, "tool_use", "incomplete", "incomplete_response"),
    ],
    ids=["unknown-exit", "nonzero-exit", "upstream-error", "max-tokens", "refusal", "tool-use"],
)
def test_parsed_unsuccessful_observations_have_zero_cli_exit_but_no_result_text(
    tmp_path, options, changes, assistant_stop, state, error
):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream(result_changes=changes, assistant_stop=assistant_stop))
    result = invoke(source, *options)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert (report["state"], report["error_code"]) == (state, error)
    assert report["result_text"] == {
        "utf8_size": 0,
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    assert report["formal_acceptance"] is report["real_client_verified"] is False
    assert b"Hello" not in result.stdout + result.stderr
    assert result.stderr == b""


def test_inspection_preserves_input_bytes_mtime_and_directory_contents(tmp_path):
    source = tmp_path / "events.jsonl"
    source.write_bytes(stream())
    before = source.stat()
    content = source.read_bytes()
    listing = tuple(tmp_path.iterdir())
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0
    assert source.read_bytes() == content
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert tuple(tmp_path.iterdir()) == listing


def test_raw_session_result_thinking_and_tool_fields_are_not_printed(tmp_path):
    canary = "private-cli-fixture-canary"
    events = [
        {"type": "system", "subtype": "init", "session_id": canary},
        {
            "type": "assistant",
            "session_id": canary,
            "message": {
                "content": [
                    {"type": "thinking", "thinking": canary, "signature": canary},
                    {
                        "type": "tool_use",
                        "id": "fixture-tool",
                        "name": "Bash",
                        "input": {"command": canary},
                    },
                ],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "session_id": canary,
            "result": "你好" + canary,
            "total_cost_usd": 123.45,
        },
    ]
    source = tmp_path / (canary + ".jsonl")
    source.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8"
    )
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["tool_block_count"] == report["assistant_message_count"] == 1
    assert report["result_text"]["utf8_size"] == 6 + len(canary)
    assert report["usage"] is None
    assert report["billing_verified"] is False
    assert canary.encode() not in result.stdout + result.stderr
    assert "你好".encode() not in result.stdout
    assert b"123.45" not in result.stdout
    assert result.stderr == b""


@pytest.mark.parametrize(
    "content,error",
    [
        (b'{"type":"unsupported-private-canary"}', "unsupported_event"),
        (b'{"type":"result","subtype":"success"}', "invalid_event_sequence"),
    ],
)
def test_unsupported_or_misordered_records_have_only_static_error(tmp_path, content, error):
    source = tmp_path / "events.jsonl"
    source.write_bytes(content)
    result = invoke(source, "--exit-code", "0")
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == error
    assert b"private-canary" not in result.stdout + result.stderr
    assert result.stderr == b""


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO fixture requires os.mkfifo")
def test_fifo_input_is_rejected_without_waiting_for_a_writer(tmp_path):
    source = tmp_path / "fixture.fifo"
    os.mkfifo(source)
    result = invoke(source)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == "input_unavailable"
    assert result.stderr == b""


def test_missing_required_input_returns_usage_exit_without_reading_files():
    result = subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, timeout=20, check=False
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"--input" in result.stderr

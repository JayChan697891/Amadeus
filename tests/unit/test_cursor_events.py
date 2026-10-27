"""Synthetic Cursor standalone JSON fixtures; no actual client evidence."""

import json
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.cursor_events import parse_cursor_json
from agentsync.errors import AgentSyncError


def terminal(**changes):
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "duration_ms": 125,
        "duration_api_ms": 100,
        "result": "Synthetic 你好 reply",
        "session_id": "private-client-session",
        **changes,
    }


def test_standalone_object_preserves_private_text_and_caller_reported_metadata():
    payload = terminal(request_id="private-request", extension={"future": [1, True, None]})
    report = parse_cursor_json(json.dumps(payload), exit_code=0)
    assert report.state == "succeeded" and report.error_code is None
    assert report.result_text == "Synthetic 你好 reply"
    assert report.session_id == "private-client-session"
    assert report.metadata.duration_ms == 125
    assert report.metadata.duration_api_ms == 100
    assert report.metadata.request_id == "private-request"
    assert report.metadata.caller_reported is True
    assert report.metadata.verification == "unverified"
    assert report.protocol_only is True and report.provenance == "caller_supplied"
    assert report.real_client_verified is report.execution_connected is False
    assert report.verification == report.core_authorization == "unverified"
    assert "private-" not in repr(report) and "reply" not in repr(report)
    with pytest.raises(FrozenInstanceError):
        report.state = "failed"
    with pytest.raises(FrozenInstanceError):
        report.metadata.duration_ms = 0


@pytest.mark.parametrize(
    "text,exit_code,state,error",
    [
        (json.dumps(terminal()), None, "incomplete", "process_unknown"),
        (json.dumps(terminal()), 3, "failed", "process_failed"),
        ("", 0, "incomplete", "incomplete_response"),
        (" \n\t", None, "incomplete", "incomplete_response"),
        ("", 3, "failed", "process_failed"),
    ],
)
def test_missing_exit_or_nonzero_and_empty_capture_never_expose_text(text, exit_code, state, error):
    report = parse_cursor_json(text, exit_code=exit_code)
    assert report.state == state and report.error_code == error
    assert report.result_text == ""


def test_default_exit_is_unknown_and_optional_request_is_absent():
    report = parse_cursor_json(json.dumps(terminal()))
    assert report.state == "incomplete" and report.result_text == ""
    assert report.metadata.request_id is None


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "assistant"},
        {"type": "tool_call"},
        {"subtype": "error"},
        {"subtype": "future"},
        {"is_error": True},
    ],
)
def test_unimplemented_event_and_failure_schemas_are_explicitly_unsupported(changes):
    with pytest.raises(AgentSyncError) as error:
        parse_cursor_json(json.dumps(terminal(**changes)), exit_code=0)
    assert error.value.code == "unsupported_event"
    assert str(error.value) == "Unsupported Cursor JSON subset."


@pytest.mark.parametrize(
    "text,exit_code",
    [
        (None, 0),
        ("{}", 0),
        ("[]", 0),
        ("not-json", 0),
        (json.dumps(terminal()) + "\n" + json.dumps(terminal()), 0),
        ('{"type":"result","type":"result"}', 0),
        ('{"extension":{"a":1,"a":2}}', 0),
        (json.dumps(terminal(extension=float("nan"))), 0),
        (json.dumps(terminal(extension=float("inf"))), 0),
        (json.dumps(terminal()).replace("125", "1e10000"), 0),
        (json.dumps(terminal(extension="\x00")), 0),
        (json.dumps(terminal(extension="\ud800")), 0),
        ("\ud800", 0),
        ("\x00", 0),
        (
            json.dumps(
                terminal(
                    extension=[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[0]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
                )
            ),
            0,
        ),
        (" " * (1024 * 1024 + 1), 0),
        (json.dumps(terminal(result="a" * 65537)), 0),
        (json.dumps(terminal(result="你" * 21846), ensure_ascii=False), 0),
        (json.dumps(terminal(extension="a" * 65537)), 0),
        (json.dumps(terminal()), True),
        (json.dumps(terminal()), 2**63),
        (json.dumps(terminal()), -(2**63) - 1),
        (json.dumps(terminal()), 0.0),
    ],
    ids=[
        "not-text",
        "missing-schema",
        "array",
        "malformed",
        "jsonl",
        "duplicate-top",
        "duplicate-nested",
        "nan",
        "infinity",
        "overflow-float",
        "escaped-nul",
        "escaped-surrogate",
        "surrogate",
        "nul",
        "deep",
        "total-bound",
        "result-bound",
        "utf8-result-bound",
        "unknown-string-bound",
        "bool-exit",
        "large-exit",
        "negative-exit-bound",
        "float-exit",
    ],
)
def test_invalid_json_encoding_structure_and_bounds_are_static_errors(text, exit_code):
    with pytest.raises(AgentSyncError) as error:
        parse_cursor_json(text, exit_code=exit_code)
    assert error.value.code == "validation_error"
    assert str(error.value) == "Invalid Cursor JSON input."


@pytest.mark.parametrize(
    "changes",
    [
        {"result": None},
        {"is_error": "false"},
        {"duration_ms": -1},
        {"duration_ms": True},
        {"duration_api_ms": 0.5},
        {"duration_api_ms": 2**63},
        {"session_id": " "},
        {"session_id": "s\n"},
        {"session_id": "你" * 67},
        {"request_id": None},
        {"request_id": ""},
        {"request_id": "r" * 201},
    ],
)
def test_required_schema_and_identifier_timing_types_are_strict(changes):
    with pytest.raises(AgentSyncError) as error:
        parse_cursor_json(json.dumps(terminal(**changes)), exit_code=0)
    assert error.value.code == "validation_error"


@pytest.mark.parametrize(
    "field",
    ["type", "subtype", "is_error", "duration_ms", "duration_api_ms", "result", "session_id"],
)
def test_each_success_schema_field_is_required(field):
    payload = terminal()
    del payload[field]
    with pytest.raises(AgentSyncError) as error:
        parse_cursor_json(json.dumps(payload), exit_code=0)
    assert error.value.code == "validation_error"


def test_exact_result_and_identifier_uint_bounds_remain_supported():
    payload = terminal(
        result="a" * 65536, session_id="s" * 200, duration_ms=2**63 - 1, duration_api_ms=0
    )
    report = parse_cursor_json(json.dumps(payload), exit_code=0)
    assert report.state == "succeeded" and len(report.result_text) == 65536

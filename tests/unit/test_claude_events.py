"""Synthetic protocol fixtures only, never actual Claude-client evidence."""

import json
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.claude_events import parse_claude_jsonl
from agentsync.errors import AgentSyncError


def stream(*events):
    return "\n".join(json.dumps(event) for event in events)


def init():
    return {"type": "system", "subtype": "init", "session_id": "synthetic-session"}


def result(**changes):
    return {
        "type": "result",
        "subtype": "success",
        "session_id": "synthetic-session",
        "is_error": False,
        "result": "Synthetic final reply",
        **changes,
    }


def test_literal_complete_response_needs_exit_zero_and_is_unverified():
    report = parse_claude_jsonl(stream(init(), result()), exit_code=0)
    assert report.session_id == "synthetic-session"
    assert report.state == "succeeded"
    assert report.result_text == "Synthetic final reply"
    assert report.usage is None
    assert report.event_count == 2
    assert report.assistant_message_count == report.tool_block_count == 0
    assert report.protocol_only is True
    assert report.real_client_verified is report.execution_connected is False
    assert report.verification == report.core_authorization == "unverified"
    assert report.provenance == "caller_supplied"
    assert "Synthetic final reply" not in repr(report)


@pytest.mark.parametrize(
    "payload,exit_code,state,code",
    [
        (result(), None, "incomplete", "process_unknown"),
        (result(), 9, "failed", "process_failed"),
        (result(is_error=True, api_error_status=429), 0, "failed", "upstream_error"),
        (result(subtype="error_max_turns", is_error=True), 0, "failed", "upstream_error"),
        (result(subtype="error_during_execution", is_error=True), 0, "failed", "upstream_error"),
        (result(terminal_reason="aborted_tools"), 0, "incomplete", "interrupted"),
        (result(terminal_reason="aborted_streaming"), 0, "incomplete", "interrupted"),
        (result(stop_reason="max_tokens"), 0, "incomplete", "incomplete_response"),
        (result(stop_reason="refusal"), 0, "incomplete", "incomplete_response"),
        (result(permission_denials=[{"tool_name": "Read"}]), 0, "failed", "permission_denied"),
        (
            result(deferred_tool_use={"id": "x", "name": "Bash", "input": {}}),
            0,
            "incomplete",
            "deferred_tool_use",
        ),
    ],
)
def test_unsuccessful_observations_never_expose_final_text(payload, exit_code, state, code):
    report = parse_claude_jsonl(stream(init(), payload), exit_code=exit_code)
    assert report.state == state
    assert report.error_code == code
    assert report.result_text == ""


@pytest.mark.parametrize("text", ["", stream(init())])
def test_missing_result_is_incomplete(text):
    report = parse_claude_jsonl(text, exit_code=0)
    assert report.state == "incomplete"
    assert report.error_code == "incomplete_stream"
    assert report.result_text == ""


def assistant(**changes):
    return {
        "type": "assistant",
        "session_id": "synthetic-session",
        "parent_tool_use_id": None,
        "message": {
            "model": "synthetic-model",
            "content": [{"type": "text", "text": "intermediate"}],
        },
        **changes,
    }


@pytest.mark.parametrize(
    "events",
    [
        (result(),),
        (assistant(), init()),
        (init(), init()),
        (init(), result(), result()),
        (init(), result(), assistant()),
        (init(), result(session_id="other")),
        (init(), assistant(session_id="other"), result()),
    ],
)
def test_supported_event_sequence_and_session_correlations_reject_misrouting(events):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(*events), exit_code=0)
    assert exc.value.code == "invalid_event_sequence"


@pytest.mark.parametrize(
    "events",
    [
        (init(), {"type": "future"}, result()),
        ({"type": "system", "subtype": "hook_started"}, init(), result()),
        (init(), result(), {"type": "system", "subtype": "prompt_suggestion"}),
        (init(), assistant(parent_tool_use_id="child-context"), result()),
        (init(), result(origin={"kind": "task-notification"})),
        (init(), result(subtype="future", is_error=True)),
    ],
)
def test_known_but_outside_subset_or_unknown_events_are_unsupported(events):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(*events), exit_code=0)
    assert exc.value.code == "unsupported_event"


@pytest.mark.parametrize(
    "text,exit_code",
    [
        (None, 0),
        ("[]", 0),
        ("{}", 0),
        ("\x00", 0),
        ("\ud800", 0),
        (stream(init(), result()), True),
        ('{"type":"system","type":"result"}', 0),
        ('{"type":"system","metadata":{"x":1,"x":2}}', 0),
        ('{"type":"system","metadata":NaN}', 0),
        ('{"metadata":' + "[" * 34 + "0" + "]" * 34 + "}", 0),
        ("x" * (1024 * 1024 + 1), 0),
        (stream(init(), result(is_error="false")), 0),
        (stream(init(), result(result=99)), 0),
    ],
    ids=[
        "not-text",
        "array",
        "no-type",
        "nul",
        "surrogate",
        "bool-exit",
        "duplicate-top",
        "duplicate-nested",
        "nonfinite",
        "deep",
        "too-large",
        "bool-required",
        "text-required",
    ],
)
def test_invalid_json_bounds_and_types_fail_with_static_error(text, exit_code):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(text, exit_code=exit_code)
    assert exc.value.code == "validation_error"
    assert str(exc.value) == "Invalid Claude event input."


def test_tool_and_thinking_payloads_are_counted_but_never_executed_or_exposed(tmp_path):
    target = tmp_path / "must-not-exist"
    content = [
        {"type": "text", "text": "Private intermediate reply"},
        {"type": "thinking", "thinking": "private reasoning", "signature": "private signature"},
        {
            "type": "tool_use",
            "id": "tool-a",
            "name": "Bash",
            "input": {"command": "private command", "path": str(target)},
        },
        {
            "type": "server_tool_use",
            "id": "tool-b",
            "name": "web_search",
            "input": {"query": "private query"},
        },
    ]
    report = parse_claude_jsonl(
        stream(init(), assistant(message={"model": "synthetic", "content": content}), result()),
        exit_code=0,
    )
    assert report.state == "succeeded"
    assert report.assistant_message_count == 1
    assert report.tool_block_count == 2
    assert report.result_text == "Synthetic final reply"
    assert not target.exists()
    assert "private" not in repr(report).lower()
    assert "intermediate" not in report.result_text


def test_reported_usage_is_separate_from_assistant_usage_and_cost():
    observed = assistant(
        message={"model": "synthetic", "content": [], "usage": {"input_tokens": 900}}
    )
    report = parse_claude_jsonl(
        stream(
            init(),
            observed,
            result(
                usage={"input_tokens": 2, "output_tokens": 3, "cache_read_input_tokens": 100},
                total_cost_usd=12.34,
            ),
        ),
        exit_code=0,
    )
    assert report.usage.input_tokens == 2
    assert report.usage.output_tokens == 3
    assert report.usage.cache_read_input_tokens == 100
    assert report.usage.cache_creation_input_tokens is None
    assert not hasattr(report, "total_cost_usd")
    assert report.verification == "unverified"


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"input_tokens": True, "output_tokens": 2},
        {"input_tokens": -1, "output_tokens": 2},
        {"input_tokens": 1, "output_tokens": 2**63},
        {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": False},
        [],
    ],
)
def test_invalid_usage_cannot_become_verified_or_fabricated_zero(usage):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(init(), result(usage=usage)), exit_code=0)
    assert exc.value.code == "validation_error"


@pytest.mark.parametrize(
    "payload",
    [
        assistant(message={"content": "not-a-list"}),
        assistant(message={"content": [{"type": "text", "text": False}]}),
        assistant(
            message={"content": [{"type": "tool_use", "id": "x", "name": "Bash", "input": "wrong"}]}
        ),
        result(permission_denials="wrong"),
        result(errors="wrong"),
        result(deferred_tool_use="wrong"),
        result(api_error_status=True),
        result(duration_ms=True),
        result(total_cost_usd=-1),
    ],
)
def test_supported_record_shapes_are_validated_before_projection(payload):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(init(), payload), exit_code=0)
    assert exc.value.code == "validation_error"


@pytest.mark.parametrize(
    "payload",
    [
        assistant(message={"content": [{"type": "future"}]}),
        result(terminal_reason="future"),
        result(stop_reason="future"),
    ],
)
def test_unsupported_semantics_do_not_silently_succeed(payload):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(init(), payload), exit_code=0)
    assert exc.value.code == "unsupported_event"


def test_result_errors_and_assistant_api_error_override_optimistic_flags():
    for events in [
        (init(), result(errors=["private failure details"])),
        (init(), assistant(error="rate_limit"), result()),
    ]:
        report = parse_claude_jsonl(stream(*events), exit_code=0)
        assert report.state == "failed"
        assert report.error_code == "upstream_error"
        assert report.result_text == ""
        assert "private" not in repr(report)


@pytest.mark.parametrize(
    "changes",
    [
        {"terminal_reason": []},
        {"stop_reason": {}},
        {"origin": []},
        {"origin": {"kind": 1}},
        {"permission_denials": False},
        {"errors": [1]},
    ],
)
def test_discriminator_shapes_raise_static_validation_instead_of_python_errors(changes):
    with pytest.raises(AgentSyncError) as exc:
        parse_claude_jsonl(stream(init(), result(**changes)), exit_code=0)
    assert exc.value.code == "validation_error"
    assert str(exc.value) == "Invalid Claude event input."


def test_explicit_api_error_status_does_not_allow_optimistic_success_flags():
    report = parse_claude_jsonl(stream(init(), result(api_error_status=429)), exit_code=0)
    assert report.state == "failed"
    assert report.error_code == "upstream_error"
    assert report.result_text == ""


def test_unicode_crlf_optional_session_and_frozen_privacy_markers():
    events = [
        init(),
        assistant(session_id=None),
        result(result="纯离线结果 🐈", usage={"input_tokens": 1, "output_tokens": 2}),
    ]
    report = parse_claude_jsonl(stream(*events).replace("\n", "\r\n") + "\r\n", exit_code=0)
    assert report.result_text == "纯离线结果 🐈"
    assert report.usage.cache_read_input_tokens is None
    with pytest.raises(FrozenInstanceError):
        report.real_client_verified = True
    with pytest.raises(FrozenInstanceError):
        report.usage.input_tokens = 100


def test_total_text_and_event_count_bounds_are_enforced():
    text = assistant(message={"content": [{"type": "text", "text": "x" * 5000}]})
    for raw in [stream(init(), *([text] * 14), result()), "{}\n" * 8193]:
        with pytest.raises(AgentSyncError) as exc:
            parse_claude_jsonl(raw, exit_code=0)
        assert exc.value.code == "validation_error"


def assistant_with_stop(reason):
    return {
        "type": "assistant",
        "session_id": "synthetic-session",
        "message": {
            "content": [{"type": "text", "text": "Synthetic partial text"}],
            "stop_reason": reason,
        },
    }


@pytest.mark.parametrize("reason", ["max_tokens", "refusal", "tool_use"])
def test_last_assistant_incomplete_stop_cannot_be_hidden_by_optimistic_result(reason):
    for terminal in (result(), result(stop_reason="end_turn")):
        report = parse_claude_jsonl(
            stream(init(), assistant_with_stop(reason), terminal), exit_code=0
        )
        assert report.state == "incomplete"
        assert report.result_text == ""
        assert report.error_code == "incomplete_response"


def test_later_complete_assistant_can_recover_previous_truncated_observation():
    report = parse_claude_jsonl(
        stream(
            init(), assistant_with_stop("max_tokens"), assistant_with_stop("end_turn"), result()
        ),
        exit_code=0,
    )
    assert report.state == "succeeded"
    assert report.result_text == "Synthetic final reply"


@pytest.mark.parametrize("reason", ["future_reason", [], True], ids=["unknown", "list", "bool"])
def test_assistant_stop_reason_must_be_known_or_explicitly_unsupported(reason):
    with pytest.raises(AgentSyncError):
        parse_claude_jsonl(stream(init(), assistant_with_stop(reason), result()), exit_code=0)

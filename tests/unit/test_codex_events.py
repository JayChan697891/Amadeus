"""Hand-authored protocol fixtures, never captured real-client evidence."""

import json
from dataclasses import FrozenInstanceError

import pytest

from agentsync.adapters.codex_events import parse_codex_jsonl
from agentsync.errors import AgentSyncError


def lines(*events):
    return "\n".join(json.dumps(event) for event in events)


def complete():
    return lines(
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "item-1", "type": "agent_message", "text": "Hello"},
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 2},
        },
    )


def test_complete_single_turn_requires_exit_zero_and_keeps_protocol_scope():
    report = parse_codex_jsonl(complete(), exit_code=0)
    assert report.thread_id == "thread-1"
    assert report.state == "succeeded"
    assert report.agent_messages == ("Hello",)
    assert report.usage.input_tokens == 10
    assert report.usage.cached_input_tokens == 3
    assert report.usage.output_tokens == 2
    assert report.usage.reasoning_output_tokens is None
    assert report.event_count == 4
    assert report.protocol_only is True
    assert report.provenance == "caller_supplied"
    assert report.real_client_verified is False
    assert report.execution_connected is False
    assert report.verification == "unverified"


def startup_warning():
    return {
        "type": "item.completed",
        "item": {"id": "warning-1", "type": "error", "message": "private startup detail"},
    }


def test_completed_startup_warning_is_counted_without_exposing_its_message():
    events = list(map(json.loads, complete().splitlines()))
    events.insert(1, startup_warning())
    report = parse_codex_jsonl(lines(*events), exit_code=0)
    assert report.state == "succeeded"
    assert report.agent_messages == ("Hello",)
    assert (report.event_count, report.item_event_count, report.non_message_item_event_count) == (
        5,
        2,
        1,
    )
    assert "private startup detail" not in repr(report)
    assert report.real_client_verified is False
    assert report.verification == "unverified"
    assert report.tool_item_event_count == 0


def test_reasoning_and_startup_warning_do_not_count_as_tool_events():
    events = list(map(json.loads, complete().splitlines()))
    events.insert(1, startup_warning())
    events.insert(3, {"type": "item.completed", "item": {"id": "r1", "type": "reasoning"}})
    report = parse_codex_jsonl(lines(*events), exit_code=0)
    assert report.state == "succeeded"
    assert report.agent_messages == ("Hello",)
    assert report.non_message_item_event_count == 2
    assert report.tool_item_event_count == 0


@pytest.mark.parametrize("exit_code", [0, 7, None])
def test_startup_warning_cannot_supply_a_missing_turn(exit_code):
    report = parse_codex_jsonl(
        lines({"type": "thread.started", "thread_id": "t"}, startup_warning()),
        exit_code=exit_code,
    )
    assert report.state == ("failed" if exit_code == 7 else "incomplete")
    assert report.agent_messages == ()
    assert report.usage is None


@pytest.mark.parametrize(
    "change",
    [
        "missing_thread",
        "started",
        "updated",
        "agent_message",
        "command_execution",
        "duplicate",
        "reuse_in_turn",
        "early_completion",
        "missing_message",
        "nonstring_message",
    ],
)
def test_startup_warning_exception_preserves_order_and_shape_checks(change):
    events = list(map(json.loads, complete().splitlines()))
    warning = startup_warning()
    events.insert(1, warning)
    if change == "missing_thread":
        events.pop(0)
    elif change in {"started", "updated"}:
        warning["type"] = f"item.{change}"
    elif change in {"agent_message", "command_execution"}:
        warning["item"]["type"] = change
        warning["item"]["text"] = "Hello"
    elif change == "duplicate":
        events.insert(2, startup_warning())
    elif change == "reuse_in_turn":
        events[3]["item"]["id"] = "warning-1"
    elif change == "early_completion":
        events.pop(2)
        events.pop(2)
    elif change == "missing_message":
        del warning["item"]["message"]
    else:
        warning["item"]["message"] = 3
    with pytest.raises(AgentSyncError) as error:
        parse_codex_jsonl(lines(*events), exit_code=0)
    assert error.value.code == (
        "validation_error"
        if change in {"missing_message", "nonstring_message"}
        else "invalid_event_sequence"
    )


@pytest.mark.parametrize("kind", ["error", "turn.failed"])
def test_startup_warning_does_not_mask_fatal_errors(kind):
    events = list(map(json.loads, complete().splitlines()))
    events.insert(1, startup_warning())
    events[-1] = (
        {"type": "error", "message": "private fatal detail"}
        if kind == "error"
        else {"type": "turn.failed", "error": {"message": "private fatal detail"}}
    )
    report = parse_codex_jsonl(lines(*events), exit_code=0)
    assert report.state == "failed"
    assert report.error_code == "upstream_error"
    assert "private" not in repr(report)


@pytest.mark.parametrize("exit_code,state", [(7, "failed"), (None, "incomplete")])
def test_exit_observation_prevents_protocol_only_success(exit_code, state):
    report = parse_codex_jsonl(complete(), exit_code=exit_code)
    assert report.state == state
    assert report.error_code == ("process_failed" if exit_code else "process_unknown")


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        '{"type":"thread.started","thread_id":"t"}',
        lines({"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}),
    ],
)
def test_partial_stream_never_succeeds_even_with_exit_zero(prefix):
    report = parse_codex_jsonl(prefix, exit_code=0)
    assert report.state == "incomplete"
    assert report.error_code == "incomplete_stream"
    assert report.usage is None


@pytest.mark.parametrize(
    "event",
    [
        {"type": "turn.failed", "error": {"message": "private detail"}},
        {"type": "error", "message": "private detail"},
    ],
)
def test_upstream_errors_are_static_failed_observations(event):
    report = parse_codex_jsonl(
        lines({"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}, event),
        exit_code=0,
    )
    assert report.state == "failed"
    assert report.error_code == "upstream_error"
    assert "private detail" not in repr(report)


def test_only_completed_agent_messages_are_projected_and_usage_can_be_absent():
    report = parse_codex_jsonl(
        lines(
            {"type": "thread.started", "thread_id": "t"},
            {"type": "turn.started"},
            {
                "type": "item.started",
                "item": {"id": "cmd", "type": "command_execution", "command": "never run this"},
            },
            {
                "type": "item.updated",
                "item": {
                    "id": "cmd",
                    "type": "command_execution",
                    "aggregated_output": "secret tool output",
                },
            },
            {"type": "item.completed", "item": {"id": "cmd", "type": "command_execution"}},
            {
                "type": "item.started",
                "item": {"id": "msg", "type": "agent_message", "text": "draft"},
            },
            {
                "type": "item.completed",
                "item": {"id": "msg", "type": "agent_message", "text": "final"},
            },
            {"type": "turn.completed"},
        ),
        exit_code=0,
    )
    assert report.agent_messages == ("final",)
    assert report.usage is None
    assert (report.event_count, report.item_event_count, report.non_message_item_event_count) == (
        8,
        5,
        3,
    )
    assert "never run" not in repr(report)
    assert "secret tool" not in repr(report)
    with pytest.raises(FrozenInstanceError):
        report.state = "failed"


@pytest.mark.parametrize(
    "events",
    [
        [{"type": "turn.started"}],
        [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "thread.started", "thread_id": "t"},
        ],
        [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "turn.started"},
            {"type": "turn.started"},
        ],
        [*map(json.loads, complete().splitlines()), {"type": "turn.completed"}],
        [
            *map(json.loads, complete().splitlines()),
            {
                "type": "item.completed",
                "item": {"id": "late", "type": "agent_message", "text": "late"},
            },
        ],
    ],
)
def test_invalid_single_turn_order_is_rejected(events):
    with pytest.raises(AgentSyncError, match="Invalid Codex event sequence") as error:
        parse_codex_jsonl(lines(*events), exit_code=0)
    assert error.value.code == "invalid_event_sequence"


@pytest.mark.parametrize(
    "text,code",
    [
        ('{"type":"thread.started","type":"turn.started"}', "validation_error"),
        ('{"type":"thread.started","thread_id":NaN}', "validation_error"),
        ('{"type":"thread.started",', "validation_error"),
        (
            lines({"type": "thread.started", "thread_id": "t", "extra": float("inf")}),
            "validation_error",
        ),
        (lines({"type": "turn.future"}), "unsupported_event"),
        (
            lines(
                {"type": "thread.started", "thread_id": "t"},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"id": "i", "type": "unknown_tool"}},
            ),
            "unsupported_event",
        ),
    ],
)
def test_malformed_or_unsupported_records_do_not_become_success(text, code):
    with pytest.raises(AgentSyncError) as error:
        parse_codex_jsonl(text, exit_code=0)
    assert error.value.code == code
    assert error.value.message in {"Invalid Codex event input.", "Unsupported Codex event subset."}


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": True, "cached_input_tokens": 0, "output_tokens": 1},
        {"input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 1},
        {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 2**63},
        {"input_tokens": 1, "cached_input_tokens": 0},
    ],
)
def test_present_usage_must_be_complete_strict_and_consistent(usage):
    events = list(map(json.loads, complete().splitlines()))
    events[-1]["usage"] = usage
    with pytest.raises(AgentSyncError) as error:
        parse_codex_jsonl(lines(*events), exit_code=0)
    assert error.value.code == "validation_error"


def test_bounded_input_lines_events_nesting_and_total_output():
    oversized_output = lines(
        {"type": "thread.started", "thread_id": "t"},
        {"type": "turn.started"},
        *[
            {
                "type": "item.completed",
                "item": {"id": f"m{i}", "type": "agent_message", "text": "x" * 33000},
            }
            for i in range(2)
        ],
        {"type": "turn.completed"},
    )
    for text in [
        " " * (1024 * 1024 + 1),
        " " * (65536 + 1),
        "{}\n" * 8193,
        '{"type":"error","extra":' + "[" * 40 + "0" + "]" * 40 + "}",
        oversized_output,
    ]:
        with pytest.raises(AgentSyncError) as error:
            parse_codex_jsonl(text, exit_code=0)
        assert error.value.code == "validation_error"


def test_strict_input_types_unicode_and_identifier_bounds():
    for text, exit_code in [
        (b"", 0),
        (None, 0),
        ("", True),
        ("", 0.0),
        ("\x00", 0),
        ("\ud800", 0),
        (lines({"type": "thread.started", "thread_id": " "}), 0),
        (lines({"type": "thread.started", "thread_id": "x" * 201}), 0),
        (lines({"type": "thread.started", "thread_id": "t"}) + "\n\n", 0),
        ("[]", 0),
    ]:
        with pytest.raises(AgentSyncError) as error:
            parse_codex_jsonl(text, exit_code=exit_code)
        assert error.value.code == "validation_error"


def test_item_lifecycle_and_open_items_cannot_produce_success():
    prefix = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}]
    start = {"type": "item.started", "item": {"id": "i", "type": "reasoning"}}
    finish = {"type": "item.completed", "item": {"id": "i", "type": "reasoning"}}
    for tail in [
        [start, {"type": "turn.completed"}],
        [finish, finish],
        [{"type": "item.updated", "item": {"id": "i", "type": "reasoning"}}],
        [
            start,
            {
                "type": "item.completed",
                "item": {"id": "i", "type": "agent_message", "text": "changed"},
            },
        ],
    ]:
        with pytest.raises(AgentSyncError) as error:
            parse_codex_jsonl(lines(*prefix, *tail), exit_code=0)
        assert error.value.code == "invalid_event_sequence"


def test_documented_non_message_items_are_counted_without_content_projection():
    kinds = [
        "reasoning",
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "todo_list",
        "error",
    ]
    events = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}]
    events.extend(
        {
            "type": "item.completed",
            "item": {"id": f"i{i}", "type": kind, "extra": "private tool content"},
        }
        for i, kind in enumerate(kinds)
    )
    report = parse_codex_jsonl(lines(*events, {"type": "turn.completed"}), exit_code=0)
    assert report.state == "succeeded"
    assert report.non_message_item_event_count == 7
    assert report.tool_item_event_count == 4
    assert report.agent_messages == ()
    assert "private tool content" not in repr(report)


def test_optional_fields_are_not_overconstrained_and_crlf_is_supported():
    events = list(map(json.loads, complete().splitlines()))
    events[0]["future_metadata"] = {"count": 1}
    events[-1]["usage"]["reasoning_output_tokens"] = 1
    events[-1]["usage"]["future_counter"] = 3
    report = parse_codex_jsonl(lines(*events).replace("\n", "\r\n") + "\r\n", exit_code=0)
    assert report.state == "succeeded"
    assert report.usage.reasoning_output_tokens == 1


def test_usage_zero_is_recorded_not_missing_and_remains_immutable():
    events = list(map(json.loads, complete().splitlines()))
    events[-1]["usage"] = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    report = parse_codex_jsonl(lines(*events), exit_code=0)
    assert report.usage.output_tokens == 0
    with pytest.raises(FrozenInstanceError):
        report.usage.output_tokens = 99


def test_raw_unicode_line_separators_are_message_content_not_jsonl_boundaries():
    events = list(map(json.loads, complete().splitlines()))
    message = "中文\u2028段落\u2029结尾"
    events[2]["item"]["text"] = message
    text = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    report = parse_codex_jsonl(text, exit_code=0)
    assert report.agent_messages == (message,)
    assert report.event_count == 4


def test_required_error_and_item_fields_are_validated_with_static_errors():
    prefix = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}]
    for event in [
        {"type": "turn.failed"},
        {"type": "error", "message": 1},
        {"type": "item.completed", "item": None},
        {"type": "item.completed", "item": {"id": "i", "type": "agent_message", "text": False}},
    ]:
        with pytest.raises(AgentSyncError) as error:
            parse_codex_jsonl(lines(*prefix, event), exit_code=0)
        assert error.value.message == "Invalid Codex event input."
    early = parse_codex_jsonl(lines({"type": "error", "message": "private"}), exit_code=0)
    assert (early.thread_id, early.state, early.error_code) == (None, "failed", "upstream_error")


def test_exact_output_limit_and_largest_usage_counter_remain_valid():
    prefix = [{"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}]
    messages = [
        {
            "type": "item.completed",
            "item": {"id": f"m{i}", "type": "agent_message", "text": "x" * 32768},
        }
        for i in range(2)
    ]
    report = parse_codex_jsonl(
        lines(
            *prefix,
            *messages,
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 2**63 - 1, "cached_input_tokens": 0, "output_tokens": 0},
            },
        ),
        exit_code=0,
    )
    assert report.state == "succeeded"
    assert sum(map(len, report.agent_messages)) == 65536
    assert report.usage.input_tokens == 2**63 - 1

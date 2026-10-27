"""Caller-constructed typed observations only; no client or process launches."""

import gc
import json
import weakref
from dataclasses import FrozenInstanceError, replace

import pytest

import agentsync.usage as usage_module
from agentsync.adapters.base import AdapterResult, RunSnapshot
from agentsync.adapters.claude import ClaudeResult, ClaudeRun
from agentsync.adapters.claude_events import ClaudeUsage
from agentsync.adapters.codex import CodexResult, CodexRun
from agentsync.adapters.codex_events import CodexUsage
from agentsync.adapters.cursor import CursorResult, CursorRun
from agentsync.adapters.cursor_events import CursorReportedMetadata
from agentsync.errors import AgentSyncError
from agentsync.usage import MetricTotal, UsageLedger


def codex(run_id="run", **changes):
    return CodexResult(
        CodexRun(
            "project", "session", "task", "request", run_id, "succeeded", 1.0, finished_at=1.125
        ),
        **changes,
    )


def mock():
    return AdapterResult(
        RunSnapshot(
            "project",
            "session",
            "task",
            "request",
            "run",
            "succeeded",
            0.0,
            100.0,
            finished_at=90.0,
        )
    )


def test_mixed_protocol_and_simulated_records_keep_metrics_separate():
    ledger = UsageLedger("project")
    observations = [
        codex(usage=CodexUsage(2, 1, 3)),
        ClaudeResult(
            ClaudeRun("project", "s", "t", "r", "run", "failed", 1.0, finished_at=1.25),
            usage=ClaudeUsage(4, 5),
        ),
        CursorResult(CursorRun("project", "s", "t", "r", "run", "succeeded", 1.0, finished_at=1.5)),
        mock(),
    ]
    assert all(ledger.record_result(observation) for observation in observations)
    summary = ledger.summary()
    assert (summary.total_records, summary.protocol_records, summary.simulated_records) == (4, 3, 1)
    assert (summary.protocol_succeeded, summary.protocol_failed) == (2, 1)
    assert summary.input_tokens == MetricTotal(None, 6, 2, 1)
    assert summary.output_tokens == MetricTotal(None, 8, 2, 1)
    assert summary.adapter_elapsed_ms == MetricTotal(875, 875, 3, 0)
    assert summary.failure_rate == 1 / 3
    assert summary.failure_rate_denominator == 3 and summary.failure_rate_complete
    assert summary.provenance == "caller_reported_adapter_results"
    assert summary.verification == "unverified"
    assert summary.real_client_verified is summary.billing_verified is False
    assert summary.cost_usd is None


def test_empty_missing_and_reported_zero_are_distinct():
    ledger = UsageLedger("project")
    assert ledger.summary().input_tokens == MetricTotal(None, None, 0, 0)
    ledger.record_result(mock())
    assert ledger.summary().adapter_elapsed_ms == MetricTotal(None, None, 0, 0)
    ledger.record_result(
        replace(codex(usage=CodexUsage(0, 0, 0)), run=replace(codex().run, finished_at=1.0))
    )
    assert ledger.summary().input_tokens == MetricTotal(0, 0, 1, 0)
    assert ledger.summary().adapter_elapsed_ms == MetricTotal(0, 0, 1, 0)
    ledger.record_result(
        replace(codex("missing"), run=replace(codex("missing").run, finished_at=None))
    )
    summary = ledger.summary()
    assert summary.input_tokens == MetricTotal(None, 0, 1, 1)
    assert summary.adapter_elapsed_ms == MetricTotal(None, 0, 1, 1)


def test_cursor_client_duration_is_not_observed_adapter_time_or_tokens():
    ledger = UsageLedger("project")
    observation = CursorResult(
        CursorRun("project", "s", "t", "r", "cursor", "succeeded", 1.0, finished_at=1.125),
        metadata=CursorReportedMetadata(99999, 88888, "private"),
    )
    ledger.record_result(observation)
    summary = ledger.summary()
    assert summary.input_tokens == summary.output_tokens == MetricTotal(None, None, 0, 1)
    assert summary.adapter_elapsed_ms == MetricTotal(125, 125, 1, 0)
    assert not ledger.record_result(replace(observation, metadata=CursorReportedMetadata(0, 0)))


def test_identical_replay_precedes_capacity_and_conflicting_normalized_identity_rejects():
    ledger = UsageLedger("project", max_records=1)
    observation = codex(usage=CodexUsage(1, 0, 2))
    assert ledger.record_result(observation)
    assert not ledger.record_result(observation)
    assert not ledger.record_result(
        replace(observation, agent_messages=("different ignored output",))
    )
    for field, value in (
        ("session_id", "other"),
        ("task_id", "other"),
        ("request_id", "other"),
        ("status", "failed"),
        ("started_at", 0.0),
        ("finished_at", 2.0),
    ):
        with pytest.raises(AgentSyncError) as error:
            ledger.record_result(
                replace(observation, run=replace(observation.run, **{field: value}))
            )
        assert error.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError) as error:
        ledger.record_result(replace(observation, usage=CodexUsage(2, 0, 2)))
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError) as error:
        ledger.record_result(codex("new"))
    assert error.value.code == "history_capacity_exceeded"
    assert ledger.summary().total_records == 1


def test_foreign_project_exact_result_run_and_usage_types_are_enforced():
    ledger = UsageLedger("project")
    with pytest.raises(AgentSyncError) as error:
        ledger.record_result(replace(codex(), run=replace(codex().run, project_id="foreign")))
    assert error.value.code == "namespace_mismatch"

    class PretendResult(CodexResult):
        pass

    for invalid in (
        None,
        {},
        PretendResult(codex().run),
        CodexResult(mock().run),
        replace(codex(), usage=ClaudeUsage(1, 2)),
    ):
        with pytest.raises(AgentSyncError) as error:
            ledger.record_result(invalid)
        assert error.value.code == "validation_error"
    assert ledger.summary().total_records == 0


def test_manually_constructed_usage_counters_are_strict_including_optional_counters():
    ledger = UsageLedger("project")
    for value in (True, -1, 1.0, 2**63, "1"):
        for field in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            with pytest.raises(AgentSyncError):
                ledger.record_result(codex(usage=replace(CodexUsage(1, 0, 2), **{field: value})))
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            run = ClaudeRun("project", "s", "t", "r", "claude", "succeeded", 1.0)
            with pytest.raises(AgentSyncError):
                ledger.record_result(
                    ClaudeResult(run, usage=replace(ClaudeUsage(1, 2), **{field: value}))
                )
    with pytest.raises(AgentSyncError):
        ledger.record_result(codex(usage=CodexUsage(1, None, 2)))
    assert ledger.summary().total_records == 0


def test_manually_constructed_times_statuses_and_identifiers_are_validated():
    ledger = UsageLedger("project")
    for changes in (
        {"status": "running"},
        {"status": "starting"},
        {"started_at": True},
        {"started_at": -1},
        {"started_at": float("nan")},
        {"started_at": 10**400},
        {"finished_at": float("inf")},
        {"finished_at": False},
        {"finished_at": 0.5},
        {"finished_at": 1e308},
        {"finished_at": 1e16},
        {"run_id": ""},
        {"request_id": "bad\n"},
        {"task_id": "你" * 67},
        {"session_id": "\ud800"},
    ):
        with pytest.raises(AgentSyncError):
            ledger.record_result(replace(codex(), run=replace(codex().run, **changes)))
    assert ledger.summary().total_records == 0


def test_cumulative_overflow_rejects_admission_atomically():
    ledger = UsageLedger("project")
    ledger.record_result(codex(usage=CodexUsage(2**63 - 1, 0, 0)))
    before = ledger.summary()
    with pytest.raises(AgentSyncError) as error:
        ledger.record_result(codex("overflow", usage=CodexUsage(1, 0, 0)))
    assert error.value.code == "usage_overflow"
    assert ledger.summary() == before
    assert ledger.record_result(codex("overflow", usage=CodexUsage(0, 0, 0)))
    assert ledger.summary().input_tokens.value == 2**63 - 1
    for first, second in (
        (codex(usage=CodexUsage(0, 0, 2**63 - 1)), codex("other", usage=CodexUsage(0, 0, 1))),
        (
            replace(codex(), run=replace(codex().run, started_at=0.0, finished_at=5e15)),
            replace(
                codex("other"), run=replace(codex("other").run, started_at=0.0, finished_at=5e15)
            ),
        ),
    ):
        other = UsageLedger("project")
        other.record_result(first)
        before = other.summary()
        with pytest.raises(AgentSyncError) as error:
            other.record_result(second)
        assert error.value.code == "usage_overflow" and other.summary() == before


def test_failure_rate_is_unknown_for_uncertain_or_interrupted_protocol_records():
    for status in ("unknown", "cancelled", "timed_out"):
        ledger = UsageLedger("project")
        ledger.record_result(codex())
        ledger.record_result(
            replace(codex("other"), run=replace(codex("other").run, status=status))
        )
        summary = ledger.summary()
        assert summary.failure_rate is None and not summary.failure_rate_complete
        assert summary.failure_rate_denominator == 1
        assert getattr(summary, "protocol_" + status) == 1


def test_raw_secrets_are_not_retained_and_summaries_are_immutable_snapshots():
    class PrivateText(str):
        pass

    private = PrivateText("private-output-or-client-session")
    reference = weakref.ref(private)
    observation = codex(agent_messages=(private,), client_thread_id=private)
    ledger = UsageLedger("project")
    ledger.record_result(observation)
    summary = ledger.summary()
    del observation, private
    gc.collect()
    assert reference() is None
    assert "private" not in repr(summary) and "session" not in repr(summary)
    ledger.record_result(codex("second"))
    assert summary.total_records == 1
    with pytest.raises(FrozenInstanceError):
        summary.cost_usd = 1
    with pytest.raises(FrozenInstanceError):
        summary.input_tokens.value = 1


def test_constructor_bounds_are_strict_and_empty_rate_has_no_denominator():
    for limit in (True, 0, 10001, 1.0):
        with pytest.raises(AgentSyncError):
            UsageLedger("project", limit)
    for project in ("", "bad\x00", "\ud800", "x" * 201):
        with pytest.raises(AgentSyncError):
            UsageLedger(project)
    summary = UsageLedger("project", 10000).summary()
    assert summary.failure_rate is None and summary.failure_rate_denominator == 0
    assert not summary.failure_rate_complete


def test_checkpoint_mixed_roundtrip_preserves_unknown_zero_and_omits_raw_metadata():
    ledger = UsageLedger("project", max_records=6)
    observations = [
        replace(
            codex(usage=CodexUsage(0, 4, 0, 5)),
            run=replace(codex().run, request_id='caller-你{[\\"]}', finished_at=1.0),
            agent_messages=("private-output",),
            client_thread_id="private-client",
        ),
        replace(codex("missing"), run=replace(codex("missing").run, finished_at=None)),
        ClaudeResult(
            ClaudeRun("project", "s", "t", "r", "run", "failed", 1.0),
            result_text="private-claude",
            usage=ClaudeUsage(2, 3, None, 4),
        ),
        CursorResult(
            CursorRun("project", "s", "t", "r", "run", "unknown", 1.0),
            metadata=CursorReportedMetadata(1, 2, "private-metadata"),
        ),
        mock(),
    ]
    for observation in observations:
        assert ledger.record_result(observation)
    text = ledger.to_json()
    assert "你" in text and all(
        value not in text
        for value in ("private-output", "private-client", "private-claude", "private-metadata")
    )
    document = json.loads(text)
    assert [record["counters"] for record in document["records"]] == [
        [0, 0, 4, 5],
        [None, None],
        [2, 3, None, 4],
        [None, None],
        [None, None],
    ]
    assert all("elapsed_ms" not in record for record in document["records"])
    restored = UsageLedger.from_json("project", text)
    assert restored.summary() == ledger.summary()
    assert restored.to_json() == text
    assert restored.summary().input_tokens == MetricTotal(None, 2, 2, 2)
    assert restored.summary().simulated_records == 1
    assert all(not restored.record_result(observation) for observation in observations)
    assert restored.summary().billing_verified is restored.summary().real_client_verified is False


def test_checkpoint_restore_preserves_replay_conflict_and_capacity():
    ledger = UsageLedger("project", max_records=1)
    observation = codex(usage=CodexUsage(1, 0, 2))
    ledger.record_result(observation)
    restored = UsageLedger.from_json("project", ledger.to_json())
    assert not restored.record_result(replace(observation, agent_messages=("ignored",)))
    with pytest.raises(AgentSyncError) as error:
        restored.record_result(replace(observation, usage=CodexUsage(2, 0, 2)))
    assert error.value.code == "idempotency_conflict"
    with pytest.raises(AgentSyncError) as error:
        restored.record_result(codex("new"))
    assert error.value.code == "history_capacity_exceeded"
    assert restored.summary() == ledger.summary()


def test_checkpoint_rejects_malformed_namespaces_duplicates_and_overflow():
    ledger = UsageLedger("project")
    ledger.record_result(codex(usage=CodexUsage(1, 0, 2)))
    text = ledger.to_json()
    invalid = [
        "",
        "[]",
        "null",
        "{}",
        text + " trailing",
        text.replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
        text.replace('"kind":"codex"', '"kind":"codex","kind":"codex"'),
        text.replace('"started_at":1.0', '"started_at":NaN'),
        text.replace('"started_at":1.0', '"started_at":1e999'),
        text.replace('"started_at":1.0', '"started_at":Infinity'),
        "[" * 9 + "0" + "]" * 9,
        "\ud800",
    ]
    for field, value in (
        ("schema_version", True),
        ("schema_version", 1.0),
        ("schema_version", 2),
        ("max_records", True),
        ("max_records", 0),
        ("max_records", 10001),
        ("real_client_verified", 0),
        ("billing_verified", 0),
        ("cost_usd", 0),
        ("verification", "verified"),
        ("provenance", "measured"),
        ("records", {}),
        ("extra", "private"),
    ):
        document = json.loads(text)
        document[field] = value
        invalid.append(json.dumps(document))
    for field, value in (
        ("kind", "other"),
        ("kind", []),
        ("identity", ["project"]),
        ("identity", ["project", "s", "t", "r", "\ud800"]),
        ("status", "running"),
        ("started_at", True),
        ("finished_at", 0),
        ("counters", [0, 0]),
        ("counters", [1, 2, None, None]),
        ("counters", [True, 2, 0, None]),
        ("counters", [2**63, 2, 0, None]),
        ("elapsed_ms", 0),
    ):
        document = json.loads(text)
        document["records"][0][field] = value
        invalid.append(json.dumps(document))
    for kind in ("cursor", "mock"):
        document = json.loads(text)
        document["records"][0]["kind"] = kind
        invalid.append(json.dumps(document))
    document = json.loads(text)
    del document["records"][0]["status"]
    invalid.append(json.dumps(document))
    document = json.loads(text)
    document["records"] *= 2
    invalid.append(json.dumps(document))
    for malformed in invalid:
        with pytest.raises(AgentSyncError) as error:
            UsageLedger.from_json("project", malformed)
        assert error.value.code == "validation_error"
        assert error.value.message == "Invalid usage result or options."
    for foreign_record in (False, True):
        document = json.loads(text)
        if foreign_record:
            document["records"][0]["identity"][0] = "foreign"
        else:
            document["project_id"] = "foreign"
        with pytest.raises(AgentSyncError) as error:
            UsageLedger.from_json("project", json.dumps(document))
        assert error.value.code == "namespace_mismatch"
    overflowing = UsageLedger("project")
    overflowing.record_result(codex(usage=CodexUsage(2**63 - 1, 0, 0)))
    document = json.loads(overflowing.to_json())
    document["records"].append(json.loads(text)["records"][0])
    document["records"][1]["identity"][-1] = "overflow"
    with pytest.raises(AgentSyncError) as error:
        UsageLedger.from_json("project", json.dumps(document))
    assert error.value.code == "usage_overflow"
    assert ledger.summary().total_records == 1


def test_checkpoint_preflight_project_size_utf8_and_depth_before_parse(monkeypatch):
    ledger = UsageLedger("你")
    text = ledger.to_json()
    assert usage_module._JSON_LIMIT == 32 * 1024 * 1024
    with monkeypatch.context() as patch:
        patch.setattr(usage_module, "_JSON_LIMIT", len(text.encode("utf-8")))
        assert UsageLedger.from_json("你", text).to_json() == text
        patch.setattr(usage_module, "_JSON_LIMIT", len(text))
        with pytest.raises(AgentSyncError):
            ledger.to_json()

        def no_parse(*args, **kwargs):
            pytest.fail("Invalid preflight reached JSON parsing")

        patch.setattr(usage_module.json, "loads", no_parse)
        for project, invalid in (
            ("", text),
            ("\ud800", text),
            ("你", text),
            ("你", "x" * (len(text) + 1)),
            ("你", "[" * 9 + "]" * 9),
        ):
            with pytest.raises(AgentSyncError):
                UsageLedger.from_json(project, invalid)

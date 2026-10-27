"""Snapshot-only advice plus isolated Mock simulation; no Core or real clients."""

import asyncio
from dataclasses import FrozenInstanceError
from time import monotonic

import pytest

from agentsync.adapters import AdapterTask, MockAdapter
from agentsync.errors import AgentSyncError
from agentsync.retry_planning import RetryPolicy, plan_retry


def plan(**options):
    values = dict(attempts_used=1, failure_kind="rate_limited", outcome_confirmed=True, now=10)
    values.update(options)
    return plan_retry(RetryPolicy(), **values)


def test_exponential_backoff_caps_and_retry_after_remains_an_uncapped_floor():
    policy = RetryPolicy(max_attempts=16, base_delay_seconds=2, max_delay_seconds=5)
    for used, expected in ((1, 2), (2, 4), (3, 5), (15, 5)):
        decision = plan_retry(
            policy,
            attempts_used=used,
            failure_kind="transient_error",
            outcome_confirmed=True,
            now=10,
        )
        assert (
            decision.state,
            decision.next_attempt,
            decision.delay_seconds,
            decision.retry_at,
        ) == ("retry", used + 1, expected, 10 + expected)
    for floor, expected in ((0, 1), (0.5, 1), (2, 2), (3600, 3600)):
        decision = plan(retry_after_seconds=floor)
        assert decision.delay_seconds == expected and decision.retry_at == 10 + expected


@pytest.mark.parametrize(
    "kind", ["rate_limited", "transient_error", "timeout", "permanent_error", "unknown"]
)
def test_unknown_and_unconfirmed_outcomes_never_recommend_retries(kind):
    unconfirmed = plan(failure_kind=kind, outcome_confirmed=False)
    assert unconfirmed.state == "stop" and unconfirmed.reason == "outcome_unconfirmed"
    confirmed = plan(failure_kind=kind)
    assert confirmed.state == ("stop" if kind in {"permanent_error", "unknown"} else "retry")
    if confirmed.state == "stop":
        assert confirmed.next_attempt is confirmed.delay_seconds is confirmed.retry_at is None


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"attempts_used": 3}, "attempts_exhausted"),
        ({"attempts_used": 16}, "attempts_exhausted"),
        ({"remaining_attempt_budget": 0}, "attempt_budget_exhausted"),
        ({"deadline": 11}, "deadline_exhausted"),
        ({"deadline": 10}, "deadline_exhausted"),
        ({"deadline": 0}, "deadline_exhausted"),
        ({"deadline": 12, "retry_after_seconds": 2}, "deadline_exhausted"),
        ({"now": 1e300}, "clock_precision_exhausted"),
        ({"now": 1.0, "retry_after_seconds": 0}, "retryable_failure"),
    ],
)
def test_attempt_global_and_deadline_budgets_do_not_fake_an_immediate_retry(options, reason):
    decision = plan(**options)
    assert decision.reason == reason
    if reason != "retryable_failure":
        assert decision.state == "stop"
        assert decision.next_attempt is decision.delay_seconds is decision.retry_at is None
    else:
        assert decision.state == "retry" and decision.delay_seconds > 0
    assert plan(deadline=11.0001, remaining_attempt_budget=1).state == "retry"


def test_policy_and_decisions_are_immutable_deterministic_unverified_advice():
    policy = RetryPolicy()
    decision = plan()
    assert plan() == decision
    assert decision.scope == "planning_only"
    assert decision.provenance == "caller_reported_failure_observation"
    assert decision.verification == "unverified"
    assert decision.execution_connected is decision.real_client_verified is False
    with pytest.raises(FrozenInstanceError):
        policy.max_attempts = 10
    with pytest.raises(FrozenInstanceError):
        decision.retry_at = 10


def test_all_inputs_are_strict_and_validated_even_for_stop_outcomes():
    for field, values in (
        ("max_attempts", [True, 0, 17, 1.0, "3"]),
        ("base_delay_seconds", [True, 0, -1, 31, float("nan"), float("inf"), 10**400]),
        ("max_delay_seconds", [False, 0, 61, 0.5, "30"]),
    ):
        for value in values:
            with pytest.raises(AgentSyncError):
                RetryPolicy(**{field: value})
    for field, values in (
        ("attempts_used", [True, 0, 17, 1.0, "1"]),
        ("remaining_attempt_budget", [True, -1, 17, 1.0, "1"]),
        ("failure_kind", [None, [], True, "private-invalid-kind"]),
        ("outcome_confirmed", [0, 1, None, "true"]),
        ("now", [True, -1, "10", float("nan"), float("inf"), 10**400]),
        ("deadline", [True, -1, "10", float("nan"), float("inf"), 10**400]),
        ("retry_after_seconds", [True, -1, "10", 3600.1, float("nan"), float("inf"), 10**400]),
    ):
        for value in values:
            for stop in ({"outcome_confirmed": False}, {"attempts_used": 3}):
                with pytest.raises(AgentSyncError) as error:
                    plan(**{**stop, field: value})
                assert error.value.code == "validation_error"
                assert error.value.message == "Invalid retry observation or options."
    with pytest.raises(AgentSyncError):
        plan_retry({}, attempts_used=1, failure_kind="unknown", outcome_confirmed=False, now=0)


@pytest.mark.asyncio
async def test_caller_composes_one_bounded_wait_and_second_mock_attempt_only():
    adapter = MockAdapter("project", "session", max_runs=2)
    first = await adapter.start_task(AdapterTask("project", "session", "task", "attempt-1"))
    failed = await adapter.finish_run(first.run_id, failed=True)
    policy = RetryPolicy(max_attempts=2, base_delay_seconds=0.001, max_delay_seconds=0.002)
    decision = plan_retry(
        policy,
        attempts_used=1,
        failure_kind="transient_error",
        outcome_confirmed=failed.status == "failed",
        now=monotonic(),
        remaining_attempt_budget=1,
    )
    assert decision.state == "retry" and decision.next_attempt == 2
    assert decision.delay_seconds == 0.001
    # The caller explicitly waits and starts; the planner has no adapter or execution path.
    await asyncio.sleep(decision.delay_seconds)
    second = await adapter.start_task(AdapterTask("project", "session", "task", "attempt-2"))
    completed = await adapter.finish_run(second.run_id, output="simulation_only/unverified")
    result = await adapter.get_result(completed.run_id)
    assert result.run.status == "succeeded" and result.run.run_id != first.run_id
    assert result.output == "simulation_only/unverified" and result.simulated
    assert result.verification == "unverified" and not result.execution_connected

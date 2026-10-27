"""Pure deterministic retry advice from unverified caller failure observations.

No execution, clock reads, sleeps, history, Core operations or provider calls.
Caller-confirmed outcomes do not establish idempotency, authorization or safety
to repeat an external action. Callers must recheck budgets and freshness before
any later dispatch. Numeric Retry-After is a declaration, not a parsed HTTP header.
"""

import math
from dataclasses import dataclass, field
from typing import Literal, NoReturn

from agentsync.errors import AgentSyncError

FailureKind = Literal["rate_limited", "transient_error", "timeout", "permanent_error", "unknown"]


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid retry observation or options.") from None


def _number(value: float) -> float:
    try:
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            _invalid()
        return float(value)
    except (TypeError, ValueError, OverflowError):
        _invalid()


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 1
    max_delay_seconds: float = 30

    def __post_init__(self) -> None:
        base, cap = _number(self.base_delay_seconds), _number(self.max_delay_seconds)
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 16:
            _invalid()
        if not 0 < base <= cap <= 60:
            _invalid()


@dataclass(frozen=True, slots=True)
class RetryDecision:
    state: Literal["retry", "stop"]
    reason: str
    next_attempt: int | None
    delay_seconds: float | None
    retry_at: float | None
    scope: Literal["planning_only"] = field(default="planning_only", init=False)
    provenance: Literal["caller_reported_failure_observation"] = field(
        default="caller_reported_failure_observation", init=False
    )
    verification: Literal["unverified"] = field(default="unverified", init=False)
    execution_connected: Literal[False] = field(default=False, init=False)
    real_client_verified: Literal[False] = field(default=False, init=False)


def plan_retry(
    policy: RetryPolicy,
    *,
    attempts_used: int,
    failure_kind: FailureKind,
    outcome_confirmed: bool,
    now: float,
    deadline: float | None = None,
    retry_after_seconds: float | None = None,
    remaining_attempt_budget: int | None = None,
) -> RetryDecision:
    """Recommend the next attempt after at least one caller-reported failure.

    Attempts include the failed attempt, with counts bounded to 1..16; a supplied
    remaining global budget is 0..16. The deadline uses the same clock domain as
    now. Retry-After is a finite 0..3600 second minimum, even above the backoff cap.
    Every input is validated before returning any stop decision. Advice has no
    reservation or authority and cannot establish that a retry later occurred.
    """
    if type(policy) is not RetryPolicy:
        _invalid()
    policy.__post_init__()
    if type(attempts_used) is not int or not 1 <= attempts_used <= 16:
        _invalid()
    if type(failure_kind) is not str or failure_kind not in {
        "rate_limited",
        "transient_error",
        "timeout",
        "permanent_error",
        "unknown",
    }:
        _invalid()
    if type(outcome_confirmed) is not bool:
        _invalid()
    observed = _number(now)
    end = None if deadline is None else _number(deadline)
    retry_after = 0.0 if retry_after_seconds is None else _number(retry_after_seconds)
    if retry_after > 3600:
        _invalid()
    if remaining_attempt_budget is not None and (
        type(remaining_attempt_budget) is not int or not 0 <= remaining_attempt_budget <= 16
    ):
        _invalid()

    def stop(reason: str) -> RetryDecision:
        return RetryDecision("stop", reason, None, None, None)

    if not outcome_confirmed:
        return stop("outcome_unconfirmed")
    if failure_kind == "unknown":
        return stop("unknown_failure")
    if failure_kind == "permanent_error":
        return stop("permanent_failure")
    if attempts_used >= policy.max_attempts:
        return stop("attempts_exhausted")
    if remaining_attempt_budget == 0:
        return stop("attempt_budget_exhausted")
    delay = max(
        min(
            float(policy.max_delay_seconds),
            float(policy.base_delay_seconds) * 2 ** (attempts_used - 1),
        ),
        retry_after,
    )
    retry_at = observed + delay
    if not math.isfinite(retry_at) or retry_at <= observed:
        return stop("clock_precision_exhausted")
    if end is not None and retry_at >= end:
        return stop("deadline_exhausted")
    return RetryDecision("retry", "retryable_failure", attempts_used + 1, delay, retry_at)

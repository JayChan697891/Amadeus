"""Translate one provider failure into offline advice, never a repeat call."""

from dataclasses import replace

from agentsync.errors import AgentSyncError
from agentsync.providers.base import ProviderError
from agentsync.retry_planning import FailureKind, RetryDecision, RetryPolicy, plan_retry

_PERMANENT_CODES = {
    "provider_redirect_rejected", "provider_unsupported_encoding", "provider_invalid_response",
    "provider_response_too_large",
}


def plan_provider_retry(
    error: ProviderError,
    policy: RetryPolicy,
    *,
    attempts_used: int,
    outcome_confirmed: bool,
    now: float,
    deadline: float | None = None,
    remaining_attempt_budget: int | None = None,
) -> RetryDecision:
    """Use bounded Retry-After for 429/503; do not infer remote outcome or cost."""
    if type(error) is not ProviderError or type(error.code) is not str:
        raise AgentSyncError("validation_error", "Invalid provider retry observation.")
    code, status, header = error.code, error.http_status, error.retry_after_seconds
    if (
        (status is not None and (type(status) is not int or not 100 <= status <= 599))
        or (header is not None and (type(header) is not int or not 0 <= header < 2**31))
    ):
        raise AgentSyncError("validation_error", "Invalid provider retry observation.")
    kind: FailureKind = "unknown"
    if code == "provider_rate_limited" and status == 429:
        kind = "rate_limited"
    elif code == "provider_http_error" and status == 503:
        kind = "transient_error"
    elif code == "provider_timeout" and status is None:
        kind = "timeout"
    elif code in _PERMANENT_CODES or (
        code == "provider_http_error" and status is not None and 400 <= status < 500 and status != 429
    ):
        kind = "permanent_error"

    observed_wait = header if kind in ("rate_limited", "transient_error") else None
    advice = plan_retry(
        policy, attempts_used=attempts_used, failure_kind=kind, outcome_confirmed=outcome_confirmed,
        now=now, deadline=deadline, remaining_attempt_budget=remaining_attempt_budget,
        retry_after_seconds=observed_wait if observed_wait is not None and observed_wait <= 3600 else None,
    )
    if advice.state == "retry" and observed_wait is not None and observed_wait > 3600:
        # Never shorten the provider's wait to fit the planner's accepted range.
        return replace(advice, state="stop", reason="retry_after_outside_window", next_attempt=None,
                       delay_seconds=None, retry_at=None)
    return advice

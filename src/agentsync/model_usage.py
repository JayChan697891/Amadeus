"""Local call timing and optional flat estimates for explicit model providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import monotonic_ns
from typing import Literal

from agentsync.errors import AgentSyncError
from agentsync.providers.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    OwnerAuthorization,
    ProviderKind,
)


@dataclass(frozen=True, slots=True)
class FlatRate:
    """Caller estimates in microdollars per million reported tokens."""

    input_rate: int
    output_rate: int

    def __post_init__(self) -> None:
        if any(
            type(rate) is not int or not 0 <= rate <= 10**12
            for rate in (self.input_rate, self.output_rate)
        ):
            raise AgentSyncError("validation_error", "Invalid model estimate rate.")


@dataclass(frozen=True, slots=True)
class ModelUsageSummary:
    completed_invocations: int
    in_flight: int
    responses: int
    failures: int
    cancelled: int
    mock_responses: int
    local_failure_rate: float | None
    elapsed_ms: int
    reported_input_tokens: int | None
    reported_output_tokens: int | None
    response_tokens_unknown: int
    estimated_cost_picodollars: int | None
    estimate_unknown_invocations: int
    cost_usd: None = field(default=None, init=False)
    billing_verified: Literal[False] = field(default=False, init=False)
    estimate_basis: Literal["caller_flat_rates"] = field(default="caller_flat_rates", init=False)


@dataclass(frozen=True, slots=True)
class _Call:
    status: Literal["response", "failed", "cancelled"]
    elapsed_ns: int
    simulated: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimate: int | None = None


def _counter(value: object) -> int | None:
    return value if type(value) is int and 0 <= value < 2**63 else None


class ModelCallMeter:
    """Wrap a provider on one event loop. The caller still owns its approval.

    Measurements cover local invocations of the provider interface, including
    rejected calls, cancellation and Mock. They cannot establish API billing
    or whether a remote request stopped. The flat estimate ignores pricing tiers.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        rates: dict[tuple[ProviderKind, str], FlatRate] | None = None,
        max_calls: int = 256,
    ) -> None:
        if type(max_calls) is not int or not 1 <= max_calls <= 4096:
            raise AgentSyncError("validation_error", "Invalid model meter capacity.")
        if rates is not None and (
            type(rates) is not dict
            or len(rates) > 64
            or any(type(rate) is not FlatRate for rate in rates.values())
        ):
            raise AgentSyncError("validation_error", "Invalid model estimate rates.")
        self._provider = provider
        self._rates = dict(rates or {})
        self._max_calls = max_calls
        self._calls: list[_Call] = []
        self._in_flight = 0

    async def complete(
        self, request: ModelRequest, *, authorization: OwnerAuthorization | None = None
    ) -> ModelResponse:
        if len(self._calls) + self._in_flight >= self._max_calls:
            raise AgentSyncError("history_capacity_exceeded", "Model meter capacity is exhausted.", 409)
        self._in_flight += 1
        start = monotonic_ns()
        try:
            response = await self._provider.complete(request, authorization=authorization)
            elapsed = monotonic_ns() - start
            if response.simulated or response.provider == "mock":
                call = _Call("response", elapsed, simulated=True)
            else:
                input_tokens = _counter(response.usage.input_tokens)
                output_tokens = _counter(response.usage.output_tokens)
                rate = self._rates.get((response.provider, response.model))
                estimate = (
                    input_tokens * rate.input_rate + output_tokens * rate.output_rate
                    if rate is not None and input_tokens is not None and output_tokens is not None
                    else None
                )
                call = _Call("response", elapsed, False, input_tokens, output_tokens, estimate)
        except asyncio.CancelledError:
            self._calls.append(_Call("cancelled", monotonic_ns() - start))
            raise
        except Exception:
            self._calls.append(_Call("failed", monotonic_ns() - start))
            raise
        else:
            self._calls.append(call)
            return response
        finally:
            self._in_flight -= 1

    def summary(self) -> ModelUsageSummary:
        responses = [call for call in self._calls if call.status == "response"]
        external = [call for call in responses if not call.simulated]
        mock = len(responses) - len(external)
        inputs = [call.input_tokens for call in external if call.input_tokens is not None]
        outputs = [call.output_tokens for call in external if call.output_tokens is not None]
        estimates = [call.estimate for call in external if call.estimate is not None]
        unknown_estimates = len(self._calls) - mock - len(estimates) + self._in_flight
        failures = sum(call.status == "failed" for call in self._calls)
        observed = len(responses) + failures
        return ModelUsageSummary(
            completed_invocations=len(self._calls),
            in_flight=self._in_flight,
            responses=len(responses),
            failures=failures,
            cancelled=sum(call.status == "cancelled" for call in self._calls),
            mock_responses=mock,
            local_failure_rate=failures / observed if observed else None,
            elapsed_ms=sum(call.elapsed_ns for call in self._calls) // 1_000_000,
            reported_input_tokens=sum(inputs) if inputs else None,
            reported_output_tokens=sum(outputs) if outputs else None,
            response_tokens_unknown=sum(
                call.input_tokens is None or call.output_tokens is None for call in external
            ),
            estimated_cost_picodollars=sum(estimates) if estimates and not unknown_estimates else None,
            estimate_unknown_invocations=unknown_estimates,
        )

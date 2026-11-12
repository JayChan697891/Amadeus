"""Provider and usage acceptance against local fixtures with no network calls."""

import json
from dataclasses import replace

import pytest

import agentsync.providers.http as provider_http
from agentsync.errors import AgentSyncError
from agentsync.model_usage import FlatRate, ModelCallMeter
from agentsync.model_usage_checkpoint import dump_model_usage, load_model_usage
from agentsync.providers.base import MockProvider, ModelRequest, ProviderError
from agentsync.providers.http import HTTPProvider, ProviderProfile
from agentsync.providers.retry import plan_provider_retry
from agentsync.retry_planning import RetryPolicy


async def test_claude_request_is_bound_to_one_approval_and_usage_stays_unverified(monkeypatch):
    requests = []
    key = "fixture-key-no-network"

    def response(post, active):
        active.remaining()
        requests.append(post)
        return json.dumps(
            {
                "type": "message",
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "fixture response"}],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            }
        ).encode("ascii")

    monkeypatch.setattr(provider_http, "send", response)
    profile = ProviderProfile("anthropic", "fixture-model", key)
    provider = HTTPProvider(profile)
    request = ModelRequest("fixture prompt", max_output_tokens=12)
    grant = provider.authorize(request)
    for caller, modified in (
        (HTTPProvider(profile), request),
        (provider, replace(request, max_output_tokens=13)),
    ):
        with pytest.raises(AgentSyncError) as denied:
            await caller.complete(modified, authorization=grant)
        assert denied.value.code == "owner_authorization_required"
    assert requests == []
    meter = ModelCallMeter(provider, rates={("anthropic", profile.model): FlatRate(30, 60)})
    observed = await meter.complete(request, authorization=grant)
    assert observed.text == "fixture response"
    assert observed.verification == "unverified"
    assert len(requests) == 1
    post = requests[0]
    assert (post.host, post.port, post.tls, post.path) == (
        "api.anthropic.com",
        443,
        True,
        "/v1/messages",
    )
    assert post.headers["anthropic-version"] == "2026-10-21"
    body = json.loads(post.body)
    assert body["messages"] == [{"role": "user", "content": "fixture prompt"}]
    assert body["max_tokens"] == 12 and "tools" not in body

    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    assert len(requests) == 1
    saved = dump_model_usage("fixture-project", meter)
    assert key not in saved and "fixture prompt" not in saved
    restored = load_model_usage("fixture-project", saved)
    assert restored.reported_input_tokens == 4 and restored.reported_output_tokens == 2
    assert restored.estimated_cost_picodollars == 240
    assert restored.cost_usd is None and restored.billing_verified is False


async def test_rate_limit_returns_advice_without_reusing_grant_or_calling_again(monkeypatch):
    calls = 0

    def rate_limit(_post, _active):
        nonlocal calls
        calls += 1
        raise ProviderError("provider_rate_limited", http_status=429, retry_after_seconds=7)

    monkeypatch.setattr(provider_http, "send", rate_limit)
    provider = HTTPProvider(ProviderProfile("ollama", "fixture-model"))
    request = ModelRequest("fixture prompt")
    grant = provider.authorize(request)
    with pytest.raises(ProviderError) as failure:
        await provider.complete(request, authorization=grant)
    decision = plan_provider_retry(
        failure.value,
        RetryPolicy(),
        attempts_used=1,
        outcome_confirmed=True,
        now=100,
        deadline=110,
        remaining_attempt_budget=1,
    )
    assert decision.state == "retry" and decision.retry_at == 107
    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    assert calls == 1


async def test_model_budget_rejects_more_requested_tokens_without_a_provider_attempt():
    meter = ModelCallMeter(MockProvider("fixture"), max_requested_output_tokens=12)
    request = ModelRequest("fixture", max_output_tokens=8)
    assert (await meter.complete(request)).simulated is True
    with pytest.raises(AgentSyncError) as limited:
        await meter.complete(request)
    assert limited.value.code == "model_budget_exhausted"
    summary = meter.summary()
    assert summary.completed_invocations == summary.mock_responses == 1
    assert summary.reported_output_tokens is None and summary.cost_usd is None

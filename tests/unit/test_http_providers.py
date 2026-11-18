"""Synthetic wire data through the public provider API, with transport replaced."""

import asyncio
import json
from dataclasses import replace

import pytest

import agentsync.providers.base as provider_base
import agentsync.providers.http as provider_http
from agentsync.errors import AgentSyncError
from agentsync.providers import (
    HTTPProvider,
    ModelRequest,
    ProviderError,
    ProviderProfile,
    ProviderUsage,
)

_PROMPT = "Fixture input π"
_TEXT = "Fixture output π"
_KEY = "placeholder-not-a-provider-credential"
_MESSAGES = [{"role": "user", "content": _PROMPT}]
_CHAT_REQUEST = {"model": "fixture-model", "messages": _MESSAGES, "stream": False}


def chat_reply(*, usage=None, finish="stop", **message):
    return {
        "choices": [
            {"finish_reason": finish, "message": {"role": "assistant", "content": _TEXT, **message}}
        ],
        "usage": usage,
    }


@pytest.mark.parametrize(
    "kind,endpoint,auth_headers,body,reply,usage",
    [
        pytest.param(
            "openai",
            ("api.openai.com", 443, True, "/v1/chat/completions"),
            {"Authorization": f"Bearer {_KEY}"},
            _CHAT_REQUEST | {"max_completion_tokens": 12, "store": False, "n": 1},
            chat_reply(
                usage={
                    "prompt_tokens": 5,
                    "completion_tokens": 4,
                    "total_tokens": 9,
                    "prompt_tokens_details": {"cached_tokens": 2},
                    "completion_tokens_details": {"reasoning_tokens": 1},
                }
            ),
            ProviderUsage(5, 4, 9, cache_read_input_tokens=2, reasoning_tokens=1),
            id="openai",
        ),
        pytest.param(
            "anthropic",
            ("api.anthropic.com", 443, True, "/v1/messages"),
            {"x-api-key": _KEY, "anthropic-version": "2026-10-21"},
            _CHAT_REQUEST | {"max_tokens": 12},
            {
                "type": "message",
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "Fixture "},
                    {"type": "text", "text": "output π"},
                ],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 4,
                    "cache_read_input_tokens": 2,
                    "cache_creation_input_tokens": 3,
                    "output_tokens_details": {"thinking_tokens": 1},
                },
            },
            ProviderUsage(
                5, 4, cache_read_input_tokens=2, cache_creation_input_tokens=3, reasoning_tokens=1
            ),
            id="anthropic",
        ),
        pytest.param(
            "gemini",
            (
                "generativelanguage.googleapis.com",
                443,
                True,
                "/v1beta/models/fixture-model:generateContent",
            ),
            {"x-goog-api-key": _KEY},
            {
                "contents": [{"role": "user", "parts": [{"text": _PROMPT}]}],
                "generationConfig": {"maxOutputTokens": 12},
            },
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "role": "model",
                            "parts": [
                                {"text": "Fixture "},
                                {
                                    "text": "Private thought",
                                    "thought": True,
                                    "thoughtSignature": "opaque",
                                },
                                {"text": "output π"},
                            ],
                        },
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 4,
                    "totalTokenCount": 10,
                    "cachedContentTokenCount": 2,
                    "thoughtsTokenCount": 1,
                },
            },
            ProviderUsage(5, 4, 10, cache_read_input_tokens=2, reasoning_tokens=1),
            id="gemini",
        ),
        pytest.param(
            "deepseek",
            ("api.deepseek.com", 443, True, "/chat/completions"),
            {"Authorization": f"Bearer {_KEY}"},
            _CHAT_REQUEST | {"max_tokens": 12, "thinking": {"type": "disabled"}},
            chat_reply(
                usage={
                    "prompt_tokens": 5,
                    "completion_tokens": 4,
                    "total_tokens": 9,
                    "prompt_cache_hit_tokens": 2,
                }
            ),
            ProviderUsage(5, 4, 9, cache_read_input_tokens=2),
            id="deepseek",
        ),
        pytest.param(
            "ollama",
            ("127.0.0.1", 11434, False, "/api/chat"),
            {},
            _CHAT_REQUEST | {"options": {"num_predict": 12}},
            {
                "done": True,
                "done_reason": "stop",
                "message": {"role": "assistant", "content": _TEXT},
                "prompt_eval_count": 5,
                "eval_count": 4,
            },
            ProviderUsage(5, 4),
            id="ollama",
        ),
    ],
)
async def test_provider_wire_shape_and_unverified_usage(
    monkeypatch, kind, endpoint, auth_headers, body, reply, usage
):
    calls = []

    def respond(post, active):
        active.remaining()
        calls.append(post)
        return json.dumps(reply, ensure_ascii=False).encode("utf-8")

    monkeypatch.setattr(provider_http, "send", respond)
    profile = ProviderProfile(kind, "fixture-model", None if kind == "ollama" else _KEY)
    provider = HTTPProvider(profile)
    request = ModelRequest(_PROMPT, max_output_tokens=12)
    grant = provider.authorize(request)
    attempts = await asyncio.gather(
        provider.complete(request, authorization=grant),
        provider.complete(request, authorization=grant),
        return_exceptions=True,
    )
    observed, refused = attempts
    assert isinstance(refused, AgentSyncError) and refused.code == "owner_authorization_required"
    (post,) = calls
    assert (post.host, post.port, post.tls, post.path) == endpoint
    assert post.headers == {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Content-Type": "application/json",
        **auth_headers,
    }
    assert json.loads(post.body) == body
    assert _KEY not in post.path and _KEY.encode() not in post.body
    assert (observed.provider, observed.model, observed.text) == (kind, profile.model, _TEXT)
    assert observed.usage == usage
    assert observed.simulated is False and observed.real_client_verified is False
    assert (
        observed.verification == observed.core_authorization == usage.verification == "unverified"
    )
    assert observed.usage.cost_usd is None and observed.usage.billing_verified is False
    assert _KEY not in repr((profile, provider, post))
    assert _PROMPT not in repr((request, post)) and _TEXT not in repr(observed)


async def test_missing_mismatched_and_expired_grants_prevent_transport(monkeypatch):
    def unexpected_send(*args):
        pytest.fail("Rejected consent must not send a request")

    monkeypatch.setattr(provider_http, "send", unexpected_send)
    provider = HTTPProvider(ProviderProfile("ollama", "fixture-model"))
    request = ModelRequest(_PROMPT, timeout_seconds=10)
    monkeypatch.setattr(provider_base, "monotonic", lambda: 100)
    grant = provider.authorize(request, expires_in_seconds=1)
    for submitted, authorization in (
        (request, None),
        (replace(request, prompt="Different fixture input"), grant),
        (replace(request, timeout_seconds=11), grant),
    ):
        with pytest.raises(AgentSyncError) as denied:
            await provider.complete(submitted, authorization=authorization)
        assert denied.value.code == "owner_authorization_required"
    monkeypatch.setattr(provider_base, "monotonic", lambda: 101)
    with pytest.raises(AgentSyncError) as expired:
        await provider.complete(request, authorization=grant)
    assert expired.value.code == "owner_authorization_required"


@pytest.mark.parametrize(
    "kind,reply",
    [
        pytest.param("openai", b'{"choices":[],"choices":[]}', id="duplicate-json-member"),
        pytest.param("openai", chat_reply(usage={"prompt_tokens": True}), id="invalid-counter"),
        pytest.param("openai", chat_reply(content=_KEY), id="credential-echo"),
        pytest.param("deepseek", chat_reply(finish="length"), id="partial-output"),
        pytest.param("deepseek", chat_reply(tool_calls=[{}]), id="tool-call"),
        pytest.param(
            "anthropic",
            {
                "type": "message",
                "role": "assistant",
                "stop_reason": "end_turn",
                "content": [{"type": "tool_use", "text": _TEXT}],
            },
            id="non-text-block",
        ),
        pytest.param(
            "gemini",
            {
                "candidates": [
                    {
                        "finishReason": "SAFETY",
                        "content": {
                            "role": "model",
                            "parts": [{"text": _TEXT}],
                        },
                    }
                ],
            },
            id="blocked-output",
        ),
        pytest.param(
            "ollama",
            {
                "done": False,
                "done_reason": "stop",
                "message": {"role": "assistant", "content": _TEXT},
            },
            id="unfinished-output",
        ),
    ],
)
async def test_unusable_provider_output_is_sanitized_and_consumes_grant(monkeypatch, kind, reply):
    calls = []

    def respond(post, _active):
        calls.append(post)
        return reply if isinstance(reply, bytes) else json.dumps(reply).encode("utf-8")

    monkeypatch.setattr(provider_http, "send", respond)
    provider = HTTPProvider(
        ProviderProfile(kind, "fixture-model", None if kind == "ollama" else _KEY)
    )
    request = ModelRequest(_PROMPT)
    grant = provider.authorize(request)
    with pytest.raises(ProviderError) as failure:
        await provider.complete(request, authorization=grant)
    assert failure.value.code == "provider_invalid_response"
    assert failure.value.http_status is failure.value.retry_after_seconds is None
    assert all(value not in str(failure.value) for value in (_PROMPT, _TEXT, _KEY))
    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    assert len(calls) == 1

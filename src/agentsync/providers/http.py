"""Explicit text-only BYOK adapters for documented provider API endpoints."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field, replace
from time import monotonic
from typing import Any

from agentsync.errors import AgentSyncError
from agentsync.providers._transport import _MAX_REQUEST_BYTES, InFlight, Post, send
from agentsync.providers.base import (
    _MAX_TEXT_BYTES,
    ModelRequest,
    ModelResponse,
    OwnerAuthorization,
    ProviderError,
    ProviderKind,
    ProviderUsage,
    _authorization_required,
    _bad_response,
    _counter,
    _grant,
    _invalid,
    _json_object,
    _text,
    _validated_request,
)

_ENDPOINTS = {
    "openai": ("api.openai.com", 443, True, "/v1/chat/completions"),
    "anthropic": ("api.anthropic.com", 443, True, "/v1/messages"),
    "gemini": ("generativelanguage.googleapis.com", 443, True, "/v1beta/models/"),
    "deepseek": ("api.deepseek.com", 443, True, "/chat/completions"),
    "ollama": ("127.0.0.1", 11434, False, "/api/chat"),
}
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_OLLAMA_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,31})?")


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Trusted host configuration. API keys are private application data.

    Ollama needs an explicitly selected local model on the standard loopback
    listener. The host controls that service and any egress it permits.
    Cloud requests use the platform TLS trust configuration.
    """

    kind: ProviderKind
    model: str
    api_key: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in _ENDPOINTS:
            _invalid()
        if type(self.model) is not str:
            _invalid()
        pattern = _OLLAMA_MODEL if self.kind == "ollama" else _MODEL
        if pattern.fullmatch(self.model) is None:
            _invalid()
        if self.kind == "ollama":
            if self.api_key is not None or self.model.lower().endswith(("-cloud", ":cloud")):
                _invalid()
        elif (
            type(self.api_key) is not str
            or len(self.api_key) > 4096
            or re.fullmatch(r"[\x21-\x7e]+", self.api_key) is None
        ):
            _invalid()


def _post(profile: ProviderProfile, request: ModelRequest) -> Post:
    host, port, tls, path = _ENDPOINTS[profile.kind]
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Content-Type": "application/json",
    }
    if profile.api_key is not None and profile.api_key in request.prompt:
        _invalid()
    messages = [{"role": "user", "content": request.prompt}]
    limit = request.max_output_tokens
    body: dict[str, Any] = {"model": profile.model, "messages": messages, "stream": False}
    if profile.kind == "gemini":
        headers["x-goog-api-key"] = profile.api_key or ""
        path += profile.model + ":generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {"maxOutputTokens": limit},
        }
    elif profile.kind == "anthropic":
        headers["x-api-key"] = profile.api_key or ""
        headers["anthropic-version"] = "2026-10-21"
        body["max_tokens"] = limit
    elif profile.kind == "ollama":
        body["options"] = {"num_predict": limit}
    else:
        headers["Authorization"] = f"Bearer {profile.api_key}"
        if profile.kind == "openai":
            body.update(max_completion_tokens=limit, store=False, n=1)
        else:
            body.update(max_tokens=limit, thinking={"type": "disabled"})
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_REQUEST_BYTES:
        _invalid()
    return Post(host, port, tls, path, headers, encoded)


def _object(value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        _bad_response()
    return value


def _only_object(value: Any) -> dict[str, Any]:
    if type(value) is not list or len(value) != 1:
        _bad_response()
    return _object(value[0])


def _usage_object(value: Any) -> dict[str, Any]:
    return {} if value is None else _object(value)


def _response_text(value: Any, *, allow_blank: bool = False) -> str:
    try:
        return _text(value, _MAX_TEXT_BYTES, allow_blank=allow_blank)
    except AgentSyncError:
        _bad_response()


def _chat_response(data: dict[str, Any]) -> tuple[str, ProviderUsage]:
    choice = _only_object(data.get("choices"))
    message = _object(choice.get("message"))
    if (
        choice.get("finish_reason") != "stop"
        or message.get("role") != "assistant"
        or message.get("tool_calls")
        or message.get("function_call")
        or message.get("refusal") is not None
    ):
        _bad_response()
    usage = _usage_object(data.get("usage"))
    prompt = _usage_object(usage.get("prompt_tokens_details"))
    completion = _usage_object(usage.get("completion_tokens_details"))
    return _response_text(message.get("content")), ProviderUsage(
        input_tokens=_counter(usage.get("prompt_tokens")),
        output_tokens=_counter(usage.get("completion_tokens")),
        total_tokens=_counter(usage.get("total_tokens")),
        cache_read_input_tokens=_counter(
            prompt.get("cached_tokens", usage.get("prompt_cache_hit_tokens"))
        ),
        reasoning_tokens=_counter(completion.get("reasoning_tokens")),
    )


def _text_parts(value: Any, *, gemini: bool = False) -> str:
    if type(value) is not list or not 1 <= len(value) <= 32:
        _bad_response()
    pieces = []
    for item in value:
        part = _object(item)
        if gemini:
            if set(part) - {"text", "thought", "thoughtSignature"}:
                _bad_response()
            if part.get("thought") is True:
                continue
        elif part.get("type") != "text":
            _bad_response()
        pieces.append(_response_text(part.get("text"), allow_blank=True))
    return _response_text("".join(pieces))


def _anthropic_response(data: dict[str, Any]) -> tuple[str, ProviderUsage]:
    if (
        data.get("type") != "message"
        or data.get("role") != "assistant"
        or data.get("stop_reason") != "end_turn"
        or data.get("stop_details") is not None
    ):
        _bad_response()
    usage = _usage_object(data.get("usage"))
    output_details = _usage_object(usage.get("output_tokens_details"))
    return _text_parts(data.get("content")), ProviderUsage(
        input_tokens=_counter(usage.get("input_tokens")),
        output_tokens=_counter(usage.get("output_tokens")),
        cache_read_input_tokens=_counter(usage.get("cache_read_input_tokens")),
        cache_creation_input_tokens=_counter(usage.get("cache_creation_input_tokens")),
        reasoning_tokens=_counter(output_details.get("thinking_tokens")),
    )


def _gemini_response(data: dict[str, Any]) -> tuple[str, ProviderUsage]:
    candidate = _only_object(data.get("candidates"))
    if candidate.get("finishReason") != "STOP":
        _bad_response()
    content = _object(candidate.get("content"))
    if content.get("role") != "model":
        _bad_response()
    usage = _usage_object(data.get("usageMetadata"))
    return _text_parts(content.get("parts"), gemini=True), ProviderUsage(
        input_tokens=_counter(usage.get("promptTokenCount")),
        output_tokens=_counter(usage.get("candidatesTokenCount")),
        total_tokens=_counter(usage.get("totalTokenCount")),
        cache_read_input_tokens=_counter(usage.get("cachedContentTokenCount")),
        reasoning_tokens=_counter(usage.get("thoughtsTokenCount")),
    )


def _ollama_response(data: dict[str, Any]) -> tuple[str, ProviderUsage]:
    message = _object(data.get("message"))
    if (
        data.get("done") is not True
        or data.get("done_reason") != "stop"
        or message.get("role") != "assistant"
        or message.get("tool_calls")
    ):
        _bad_response()
    return _response_text(message.get("content")), ProviderUsage(
        input_tokens=_counter(data.get("prompt_eval_count")),
        output_tokens=_counter(data.get("eval_count")),
    )


_READERS = {
    "openai": _chat_response,
    "anthropic": _anthropic_response,
    "gemini": _gemini_response,
    "deepseek": _chat_response,
    "ollama": _ollama_response,
}


@dataclass(frozen=True, slots=True, init=False)
class HTTPProvider:
    """One direct, owner-approved request with no automatic retry or fallback."""

    _profile: ProviderProfile = field(repr=False)

    def __init__(self, profile: ProviderProfile) -> None:
        if type(profile) is not ProviderProfile:
            _invalid()
        object.__setattr__(self, "_profile", replace(profile))

    def authorize(
        self, request: ModelRequest, *, expires_in_seconds: int = 60
    ) -> OwnerAuthorization:
        """Call only after the host obtains independent approval for this request."""
        return _grant(self, _validated_request(request), expires_in_seconds)

    async def complete(
        self, request: ModelRequest, *, authorization: OwnerAuthorization | None = None
    ) -> ModelResponse:
        request = _validated_request(request)
        if type(authorization) is not OwnerAuthorization:
            _authorization_required()
        post = _post(self._profile, request)
        deadline = min(authorization._consume(self, request), monotonic() + request.timeout_seconds)
        active = InFlight(deadline)
        try:
            timeout = active.remaining()
            raw = await asyncio.wait_for(asyncio.to_thread(send, post, active), timeout)
        except TimeoutError:
            raise ProviderError("provider_timeout") from None
        finally:
            active.stop()
        text, usage = _READERS[self._profile.kind](_json_object(raw))
        if self._profile.api_key is not None and self._profile.api_key in text:
            _bad_response()
        return ModelResponse(self._profile.kind, self._profile.model, text, usage, False)

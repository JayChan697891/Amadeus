"""Typed, private model requests and unverified provider observations."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from threading import Lock
from time import monotonic
from typing import Any, Literal, NoReturn, Protocol, SupportsIndex

from agentsync.errors import AgentSyncError

ProviderKind = Literal["openai", "anthropic", "gemini", "deepseek", "ollama"]
_MAX_PROMPT_BYTES = 16_384
_MAX_TEXT_BYTES = 32_768


def _invalid() -> NoReturn:
    raise AgentSyncError("validation_error", "Invalid model assistance input.") from None


def _text(value: Any, limit: int, *, allow_blank: bool = False) -> str:
    if type(value) is not str or len(value) > limit or "\x00" in value:
        _invalid()
    if not allow_blank and not value.strip():
        _invalid()
    try:
        if len(value.encode("utf-8")) > limit:
            _invalid()
    except UnicodeError:
        _invalid()
    return value


@dataclass(frozen=True, slots=True)
class ModelRequest:
    prompt: str = field(repr=False)
    max_output_tokens: int = 1024
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _text(self.prompt, _MAX_PROMPT_BYTES)
        if (
            type(self.max_output_tokens) is not int
            or not 1 <= self.max_output_tokens <= 4096
            or type(self.timeout_seconds) not in (int, float)
            or not 1 <= self.timeout_seconds <= 60
        ):
            _invalid()


def _validated_request(request: ModelRequest) -> ModelRequest:
    if type(request) is not ModelRequest:
        _invalid()
    return replace(request)


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Raw provider counters. Cache and reasoning semantics vary by provider."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    verification: Literal["unverified"] = field(default="unverified", init=False)
    billing_verified: Literal[False] = field(default=False, init=False)
    cost_usd: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    provider: ProviderKind | Literal["mock"]
    model: str
    text: str = field(repr=False)
    usage: ProviderUsage
    simulated: bool
    real_client_verified: Literal[False] = field(default=False, init=False)
    verification: Literal["unverified"] = field(default="unverified", init=False)
    core_authorization: Literal["unverified"] = field(default="unverified", init=False)


class ProviderError(AgentSyncError):
    """Fixed failure code with optional sanitized HTTP and Retry-After observations."""

    def __init__(
        self,
        code: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code, "Model provider request did not produce a usable response.", 502)
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds


class OwnerAuthorization:
    """An in-process one-attempt grant minted only by trusted host code.

    This type does not authenticate the human or implement an approval ledger.
    The host must independently confirm the exact prompt, model, limits and
    possible cost before asking a provider to issue a grant.
    """

    __slots__ = ("_deadline", "_lock", "_provider", "_request", "_used")
    _deadline: float
    _lock: Lock
    _provider: object
    _request: ModelRequest
    _used: bool

    def __init__(self) -> None:
        _invalid()

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("Owner authorization is process-local.")

    def _consume(self, provider: object, request: ModelRequest) -> float:
        with self._lock:
            if (
                self._used
                or self._provider is not provider
                or self._request != request
                or monotonic() >= self._deadline
            ):
                _authorization_required()
            self._used = True
            return self._deadline


def _authorization_required() -> NoReturn:
    raise AgentSyncError("owner_authorization_required", "A fresh owner grant is required.", 403)


def _grant(provider: object, request: ModelRequest, expires_in_seconds: int) -> OwnerAuthorization:
    if type(expires_in_seconds) is not int or not 1 <= expires_in_seconds <= 60:
        _invalid()
    grant = object.__new__(OwnerAuthorization)
    grant._deadline = monotonic() + expires_in_seconds
    grant._lock = Lock()
    grant._provider = provider
    grant._request = request
    grant._used = False
    return grant


class ModelProvider(Protocol):
    async def complete(
        self, request: ModelRequest, *, authorization: OwnerAuthorization | None = None
    ) -> ModelResponse: ...


@dataclass(frozen=True, slots=True)
class MockProvider:
    """Return the same configured fixture through the normal provider interface."""

    response_text: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.response_text, _MAX_TEXT_BYTES)

    async def complete(
        self, request: ModelRequest, *, authorization: OwnerAuthorization | None = None
    ) -> ModelResponse:
        _validated_request(request)
        if authorization is not None:
            _invalid()
        return ModelResponse("mock", "mock", self.response_text, ProviderUsage(), True)


def _bad_response() -> NoReturn:
    raise ProviderError("provider_invalid_response") from None


def _json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    members: dict[str, Any] = {}
    for key, value in pairs:
        if key in members:
            _bad_response()
        members[key] = value
    return members


def _json_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        _bad_response()
    return value


def _json_constant(_text: str) -> NoReturn:
    _bad_response()


def _json_object(data: bytes | str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8") if type(data) is bytes else data
        value = json.loads(
            text,
            object_pairs_hook=_json_members,
            parse_constant=_json_constant,
            parse_float=_json_float,
        )
    except (ValueError, RecursionError):
        _bad_response()
    if type(value) is not dict:
        _bad_response()
    return value


def _counter(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value < 2**63:
        _bad_response()
    return value

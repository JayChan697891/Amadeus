"""Local owner advisory calls with durable, bounded project usage observations."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from agentsync.adapters.approved_launch import digest
from agentsync.core.usage import (
    _PROVIDER_COUNTERS,
    ProviderCallObservation,
    _ProjectUsage,
)
from agentsync.errors import AgentSyncError
from agentsync.model_usage import FlatRate, _counter
from agentsync.models import AdminAuth
from agentsync.providers import (
    AdviceRequest,
    HTTPProvider,
    MockProvider,
    OwnerAuthorization,
    ProviderError,
    ProviderKind,
)
from agentsync.providers.advice import _parse_advice
from agentsync.providers.base import _authorization_required
from agentsync.storage.admission import database_admission
from agentsync.storage.database import connect

if TYPE_CHECKING:
    from agentsync.core.service import Core

_ADMIT = "provider_usage_admit"
_FINISH = "provider_usage_finish"
_ERROR_CODES = frozenset(
    {
        "provider_timeout",
        "provider_transport_error",
        "provider_http_error",
        "provider_rate_limited",
        "provider_redirect_rejected",
        "provider_unsupported_encoding",
        "provider_invalid_response",
        "provider_response_too_large",
        "owner_authorization_required",
    }
)


class _CallRequest(AdminAuth):
    request_id: str = Field(min_length=1, max_length=200)


class _CallLookup(AdminAuth):
    call_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    request_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def one_identity(self) -> "_CallLookup":
        if (self.call_id is None) == (self.request_id is None):
            raise ValueError("Supply exactly one call ID or original request ID.")
        return self


class OwnerProviderUsage:
    """Trusted in-process caller only. Grant creation remains with the host."""

    def __init__(self, core: Core) -> None:
        self._core = core

    @contextmanager
    def _transaction(
        self, p: dict[str, Any], operation: str | None = None
    ) -> Iterator[tuple[sqlite3.Connection, float]]:
        with database_admission(self._core.db_path):
            try:
                db = connect(self._core.db_path)
            except sqlite3.Error:
                raise AgentSyncError("storage_error", "Usage storage is unavailable.", 503) from None
            actor = None
            try:
                db.execute("BEGIN IMMEDIATE" if operation else "BEGIN")
                self._core._authenticate_owner(db, p)
                actor = (p["project_id"], "owner", p["project_id"])
                yield db, time.time()
                db.commit()
            except AgentSyncError as error:
                db.rollback()
                if operation is not None:
                    self._core._audit_denial(actor, operation, p, error.code)
                raise
            except UnicodeError:
                db.rollback()
                raise AgentSyncError("validation_error", "Invalid usage request text.") from None
            except sqlite3.Error:
                db.rollback()
                raise AgentSyncError("storage_error", "Usage storage is unavailable.", 503) from None
            finally:
                db.close()

    def get(self, **payload: Any) -> dict[str, Any]:
        p = self._core._validated_payload(_CallLookup, payload)
        call_id = p["call_id"] or digest([p["project_id"], p["request_id"]])
        with self._transaction(p) as (db, _):
            observation = _ProjectUsage.load(db, p["project_id"]).provider.get(call_id)
            if observation is None:
                raise AgentSyncError("not_found", "Provider call was not found.", 404)
            return observation.public()

    @staticmethod
    def _intent(
        p: dict[str, Any],
        provider: HTTPProvider | MockProvider,
        request: AdviceRequest,
        rate: FlatRate | None,
    ) -> ProviderCallObservation:
        kind: ProviderKind | Literal["mock"]
        if isinstance(provider, HTTPProvider):
            profile = provider._profile
            kind, model, fixture = profile.kind, profile.model, None
        else:
            kind, model, fixture = "mock", "mock", digest(provider.response_text)
        return ProviderCallObservation(
            call_id=digest([p["project_id"], p["request_id"]]),
            binding_sha256=digest(
                [kind, model, fixture, asdict(request), asdict(rate) if rate is not None else None]
            ),
            provider=kind,
            model=model,
            kind=request.kind,
            input_rate=rate.input_rate if rate is not None else None,
            output_rate=rate.output_rate if rate is not None else None,
        )

    def _admit(
        self,
        p: dict[str, Any],
        intent: ProviderCallObservation,
        provider: HTTPProvider | MockProvider,
        request: AdviceRequest,
        authorization: OwnerAuthorization | None,
    ) -> ProviderCallObservation | None:
        project = p["project_id"]
        with self._transaction(p, _ADMIT) as (db, now):
            history = _ProjectUsage.load(db, project)
            old = history.provider.get(intent.call_id)
            if old is not None:
                if old.binding_sha256 != intent.binding_sha256:
                    raise AgentSyncError(
                        "idempotency_conflict", "Provider request ID is already bound.", 409
                    )
                return old
            if isinstance(provider, HTTPProvider):
                if type(authorization) is not OwnerAuthorization:
                    _authorization_required()
                authorization._check(provider, request.model_request)
            elif authorization is not None:
                raise AgentSyncError("validation_error", "Mock advice does not take a provider grant.")
            history.provider[intent.call_id] = intent
            history.save(db, project, now)
            self._core._audit_event(db, project, "owner", project, _ADMIT, p, "allowed", "ok")
            return None

    def _finish(
        self, p: dict[str, Any], intent: ProviderCallObservation, **fields: Any
    ) -> ProviderCallObservation:
        result = ProviderCallObservation.model_validate(intent.model_dump() | fields)
        project = p["project_id"]
        with self._transaction(p, _FINISH) as (db, now):
            history = _ProjectUsage.load(db, project)
            if history.provider.get(intent.call_id) != intent:
                raise AgentSyncError(
                    "idempotency_conflict", "Provider call intent has changed.", 409
                )
            history.provider[intent.call_id] = result
            history.save(db, project, now)
            self._core._audit_event(
                db, project, "owner", project, _FINISH, p, result.status, result.error_code or "ok"
            )
        return result

    async def request_advice(
        self,
        *,
        project_id: str,
        admin_token: str,
        request_id: str,
        provider: HTTPProvider | MockProvider,
        request: AdviceRequest,
        authorization: OwnerAuthorization | None = None,
        rate: FlatRate | None = None,
    ) -> dict[str, Any]:
        p = self._core._validated_payload(
            _CallRequest,
            {"project_id": project_id, "admin_token": admin_token, "request_id": request_id},
        )
        if (
            type(request) is not AdviceRequest
            or (type(provider) is not HTTPProvider and type(provider) is not MockProvider)
            or (rate is not None and (type(rate) is not FlatRate or isinstance(provider, MockProvider)))
        ):
            raise AgentSyncError("validation_error", "Expected trusted provider and advice inputs.")
        request = replace(request)
        intent = self._intent(p, provider, request, rate)
        previous = self._admit(p, intent, provider, request, authorization)
        if previous is not None:
            return {"replayed": True, "observation": previous.public(), "advice": None}

        started = time.monotonic_ns()
        remote = "simulated" if intent.provider == "mock" else "unknown"
        fields: dict[str, Any] = {}
        advice = None
        try:
            response = await provider.complete(request.model_request, authorization=authorization)
            if (response.provider, response.model, response.simulated) != (
                intent.provider,
                intent.model,
                intent.provider == "mock",
            ):
                raise AgentSyncError(
                    "provider_observation_invalid", "Unexpected provider observation."
                )
            if not response.simulated:
                remote = "response_received"
                fields.update(
                    (name, _counter(getattr(response.usage, name))) for name in _PROVIDER_COUNTERS
                )
            advice = _parse_advice(request, response)
        except asyncio.CancelledError:
            try:
                self._finish(
                    p,
                    intent,
                    status="cancelled",
                    remote_outcome=remote,
                    error_code="local_cancelled",
                    elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
                    **fields,
                )
            except AgentSyncError:
                # The durable unknown intent already prevents any replay.
                pass
            raise
        except Exception as error:
            code = (
                error.code
                if isinstance(error, AgentSyncError) and error.code in _ERROR_CODES
                else "provider_call_failed"
            )
            if code == "owner_authorization_required" and remote == "unknown":
                remote = "not_sent"
            if isinstance(error, ProviderError) and remote == "unknown":
                status = error.http_status
                if type(status) is int and 100 <= status <= 599:
                    remote = "http_error"
                    fields["http_status"] = status
                    retry = error.retry_after_seconds
                    if status in (429, 503) and type(retry) is int and 0 <= retry < 2**31:
                        fields["retry_after_seconds"] = retry
            fields.update(status="failed", error_code=code)
        else:
            fields["status"] = "succeeded"
        result = self._finish(
            p,
            intent,
            remote_outcome=remote,
            elapsed_ms=(time.monotonic_ns() - started) // 1_000_000,
            **fields,
        )
        return {
            "replayed": False,
            "observation": result.public(),
            "advice": asdict(advice) if advice is not None else None,
        }

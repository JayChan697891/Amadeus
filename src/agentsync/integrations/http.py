"""Authenticated, loopback-only HTTP transport."""

import hmac
import ipaddress
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from agentsync import __version__
from agentsync.core.service import Core
from agentsync.errors import AgentSyncError
from agentsync.sdk import error_envelope


def create_app(data_dir: str | Path | None = None, api_token: str | None = None) -> FastAPI:
    token = api_token if api_token is not None else os.environ.get("AGENTSYNC_HTTP_TOKEN")
    if not token or not token.strip():
        raise ValueError("A nonempty HTTP API token is required")
    core = Core(data_dir=data_dir)
    app = FastAPI(
        title="AgentSync", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_only(request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = False
        if not local:
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": "LOCAL_ONLY", "message": "Loopback connections only"},
                },
                status_code=403,
            )
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    async def dispatch(operation: str, request: Request, *, owner: bool) -> Any:
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": "UNAUTHORIZED", "message": "Valid bearer token required"},
                },
                status_code=401,
            )
        try:
            payload: Any = await request.json()
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(
                {
                    "ok": False,
                    "error": {"code": "VALIDATION_ERROR", "message": "Request body must be JSON"},
                },
                status_code=400,
            )
        if not isinstance(payload, dict):
            return JSONResponse(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request body must be an object",
                    },
                },
                status_code=400,
            )
        try:
            execute = core.execute_owner if owner else core.execute
            return {"ok": True, "data": execute(operation, payload)}
        except AgentSyncError as error:
            return JSONResponse(error_envelope(error), status_code=error.status_code)

    @app.post("/v1/{operation}")
    async def execute(operation: str, request: Request) -> Any:
        return await dispatch(operation, request, owner=False)

    @app.post("/owner/v1/{operation}")
    async def execute_owner(operation: str, request: Request) -> Any:
        return await dispatch(operation, request, owner=True)

    return app

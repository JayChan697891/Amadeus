"""Real HTTP transport against a disposable loopback server, with no credentials."""

import asyncio
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread

import pytest

import agentsync.providers.http as provider_http
from agentsync.errors import AgentSyncError
from agentsync.providers import HTTPProvider, ModelRequest, ProviderError, ProviderProfile

_REPLY = b'{"done":true,"done_reason":"stop","message":{"role":"assistant","content":"loopback"}}'
_ERROR_BODY = b"private upstream details from fixture"


@pytest.fixture
def loopback_provider(monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.connection.settimeout(5)
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path, self.headers, payload))
            self.server.reply(self)

        def log_message(self, format, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        host, port = server.server_address
        monkeypatch.setitem(provider_http._ENDPOINTS, "ollama", (host, port, False, "/api/chat"))
        original_connect = socket.create_connection

        def loopback_only(address, *args, **kwargs):
            assert address == (host, port), "This fixture allows only its private loopback endpoint"
            return original_connect(address, *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", loopback_only)
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server, calls, HTTPProvider(ProviderProfile("ollama", "loopback-fixture"))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


def reply_headers(handler, status=200, **headers):
    handler.send_response_only(status)
    handler.send_header("Connection", "close")
    for name, value in headers.items():
        handler.send_header(name.replace("_", "-"), str(value))
    handler.end_headers()
    handler.close_connection = True


async def test_provider_posts_once_to_owned_loopback_endpoint(loopback_provider):
    server, calls, provider = loopback_provider

    def reply(handler):
        reply_headers(handler, Content_Type="application/json", Content_Length=len(_REPLY))
        handler.wfile.write(_REPLY)

    server.reply = reply
    request = ModelRequest("local fixture only", max_output_tokens=10)
    grant = provider.authorize(request)
    observed = await provider.complete(request, authorization=grant)
    assert observed.text == "loopback" and observed.usage.input_tokens is None
    assert observed.verification == "unverified" and observed.real_client_verified is False
    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    ((path, headers, body),) = calls
    assert path == "/api/chat"
    assert headers["Host"] == f"127.0.0.1:{server.server_port}"
    assert headers["Accept-Encoding"] == "identity"
    assert not {"authorization", "x-api-key", "x-goog-api-key"} & {k.lower() for k in headers}
    assert json.loads(body) == {
        "model": "loopback-fixture",
        "messages": [{"role": "user", "content": "local fixture only"}],
        "stream": False,
        "options": {"num_predict": 10},
    }


@pytest.mark.parametrize(
    "status,code,retry_after",
    [
        (429, "provider_rate_limited", 7),
        (307, "provider_redirect_rejected", None),
    ],
)
async def test_provider_http_errors_do_not_follow_or_retry(
    loopback_provider, status, code, retry_after
):
    server, calls, provider = loopback_provider

    def reply(handler):
        reply_headers(
            handler,
            status,
            Content_Type="application/json",
            Content_Length=len(_ERROR_BODY),
            Retry_After=7,
            Location=f"http://127.0.0.1:{server.server_port}/redirect-target",
        )
        handler.wfile.write(_ERROR_BODY)

    server.reply = reply
    request = ModelRequest("local error fixture only")
    grant = provider.authorize(request)
    with pytest.raises(ProviderError) as failure:
        await provider.complete(request, authorization=grant)
    assert (failure.value.code, failure.value.http_status, failure.value.retry_after_seconds) == (
        code,
        status,
        retry_after,
    )
    assert _ERROR_BODY.decode() not in str(failure.value)
    assert "redirect-target" not in str(failure.value)
    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    assert [path for path, _, _ in calls] == ["/api/chat"]


@pytest.mark.parametrize("declared", [True, False], ids=["content-length", "streamed"])
async def test_provider_caps_declared_and_streamed_response_bytes(loopback_provider, declared):
    server, calls, provider = loopback_provider
    oversized = b" " * (256 * 1024 + 1)

    def reply(handler):
        if declared:
            reply_headers(handler, Content_Type="application/json", Content_Length=len(oversized))
        else:
            reply_headers(handler, Content_Type="application/json")
            handler.wfile.write(oversized)

    server.reply = reply
    request = ModelRequest("local large response fixture only")
    with pytest.raises(ProviderError) as failure:
        await provider.complete(request, authorization=provider.authorize(request))
    assert failure.value.code == "provider_response_too_large"
    assert len(calls) == 1


async def test_provider_cancellation_closes_inflight_socket_and_consumes_grant(loopback_provider):
    server, calls, provider = loopback_provider
    headers_sent = Event()
    peer_closed = Event()

    def reply(handler):
        # The fixture never finishes the response, so only the client can close first.
        reply_headers(handler, Content_Type="application/json", Content_Length=len(_REPLY))
        headers_sent.set()
        try:
            if handler.connection.recv(1) == b"":
                peer_closed.set()
        except ConnectionResetError:
            peer_closed.set()
        except TimeoutError:
            pass

    server.reply = reply
    request = ModelRequest("local cancellation fixture only", timeout_seconds=15)
    grant = provider.authorize(request)
    pending = asyncio.create_task(provider.complete(request, authorization=grant))
    try:
        assert await asyncio.to_thread(headers_sent.wait, 5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, timeout=5)
        assert await asyncio.to_thread(peer_closed.wait, 5)
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    with pytest.raises(AgentSyncError) as replay:
        await provider.complete(request, authorization=grant)
    assert replay.value.code == "owner_authorization_required"
    assert len(calls) == 1

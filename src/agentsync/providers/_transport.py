"""One bounded direct POST to a provider endpoint chosen by trusted package code."""

from __future__ import annotations

import http.client
import math
import re
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from time import monotonic

from agentsync.providers.base import ProviderError

_MAX_REQUEST_BYTES = 100_000
_MAX_RESPONSE_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class Post:
    host: str
    port: int
    tls: bool
    path: str
    headers: dict[str, str] = field(repr=False)
    body: bytes = field(repr=False)


class InFlight:
    """Permit the caller to interrupt an attached socket on deadline or cancellation."""

    def __init__(self, deadline: float) -> None:
        self._deadline = deadline
        self._lock = Lock()
        self._socket: socket.socket | None = None
        self._stopped = False

    def remaining(self) -> float:
        seconds = self._deadline - monotonic()
        if seconds <= 0 or self._stopped:
            raise ProviderError("provider_timeout")
        return seconds

    def attach(self, connection: socket.socket) -> None:
        with self._lock:
            self.remaining()
            self._socket = connection

    def detach(self) -> None:
        with self._lock:
            self._socket = None

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


def _retry_after(value: str | None) -> int | None:
    if value is None or len(value) > 80:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]{1,10}", value):
        seconds = int(value)
        return seconds if seconds <= 2**31 - 1 else None
    try:
        moment = parsedate_to_datetime(value)
        if moment.tzinfo is None:
            return None
        seconds = max(0, math.ceil((moment - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None
    return seconds if seconds <= 2**31 - 1 else None


def _body(response: http.client.HTTPResponse, active: InFlight) -> bytes:
    encoding = response.getheader("Content-Encoding")
    if encoding is not None and encoding.lower() != "identity":
        raise ProviderError("provider_unsupported_encoding")
    if response.headers.get_content_type() != "application/json":
        raise ProviderError("provider_invalid_response")
    content_length = response.getheader("Content-Length")
    if content_length is not None:
        if not re.fullmatch(r"[0-9]{1,6}", content_length):
            raise ProviderError("provider_invalid_response")
        if int(content_length) > _MAX_RESPONSE_BYTES:
            raise ProviderError("provider_response_too_large")
    data = bytearray()
    while len(data) <= _MAX_RESPONSE_BYTES:
        active.remaining()
        chunk = response.read1(min(16_384, _MAX_RESPONSE_BYTES + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise ProviderError("provider_response_too_large")
    if content_length is not None and len(data) != int(content_length):
        raise ProviderError("provider_invalid_response")
    active.remaining()
    return bytes(data)


def _connection(post: Post, timeout: float) -> http.client.HTTPConnection:
    if not post.tls:
        return http.client.HTTPConnection(post.host, post.port, timeout=timeout)
    # Enable hostname and certificate verification without reading SSLKEYLOGFILE.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    return http.client.HTTPSConnection(post.host, post.port, timeout=timeout, context=context)


def send(post: Post, active: InFlight) -> bytes:
    """Use a direct socket, with no proxy, redirects, decompression or retries."""
    connection: http.client.HTTPConnection | None = None
    try:
        connection = _connection(post, active.remaining())
        connection.set_debuglevel(0)
        # DNS may block in the OS. Recheck before sending the request after connect.
        connection.timeout = active.remaining()
        connection.connect()
        sock = connection.sock
        if sock is None:
            raise ProviderError("provider_transport_error")
        active.attach(sock)
        sock.settimeout(active.remaining())
        connection.request("POST", post.path, body=post.body, headers=post.headers)
        sock.settimeout(active.remaining())
        with connection.getresponse() as response:
            if response.status != 200:
                if 300 <= response.status < 400:
                    code = "provider_redirect_rejected"
                elif response.status == 429:
                    code = "provider_rate_limited"
                else:
                    code = "provider_http_error"
                raise ProviderError(
                    code,
                    http_status=response.status,
                    retry_after_seconds=_retry_after(response.getheader("Retry-After"))
                    if response.status in (429, 503)
                    else None,
                )
            return _body(response, active)
    except TimeoutError:
        raise ProviderError("provider_timeout") from None
    except (OSError, ValueError, http.client.HTTPException):
        raise ProviderError("provider_transport_error") from None
    finally:
        active.detach()
        if connection is not None:
            connection.close()

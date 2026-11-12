"""HTTP with the outside world that never outlives its call's limit (item 118, D-186).

Every client that calls out over HTTP (WhatsApp through MSG91, the DNS and
RDAP lookups, Instagram and YouTube, the timestamp authorities, and the
Claude API through its SDK) is made by `limited_client`, and each call runs
`within` one `Deadline` for the whole call, across its tries:

- **every wait on the socket is cut to the time left.** A connect, a write
  or a read waits at most its own limit (connect 3 s, read 10 s; backend.md
  section 6) or what the call has left, whichever is less, and none starts
  once the limit has passed. A server that trickles a byte at a time, each
  inside the read timeout, in its headers or its body, is cut off at the
  limit rather than holding a worker for ever: httpx2 itself has only
  per-wait limits (connect, read, write, pool), never one on the whole;
- **the answer is read piece by piece** (`exchange`), at most
  `MAX_ANSWER_BYTES` of it, so an answer that never ends cannot fill memory
  either.

The socket's waits are cut by a network backend that reads the deadline set
by `within` on this thread; outside `within` it changes nothing. **What it
does not cut:** a wait for a free connection in the client's own pool (100
connections), which is not a socket wait; it keeps the client's pool limit. It is put
into the transport httpx2 builds (`HTTPTransport._pool`, replaced with a
pool given that backend), the one seam httpx2 offers no public way to set.
"""

import ssl
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpcore2
import httpx2

from app.core.deadline import Deadline

# Every answer we ask the outside world for is small: a token, a JSON reply,
# IANA's RDAP file (71,328 bytes, read 12 November 2026). 2 MiB is far above any
# and far below what could hurt a worker.
MAX_ANSWER_BYTES = 2 * 1024 * 1024
# httpx2's own defaults (`httpx2.Limits`), kept for the pool built below.
MAX_CONNECTIONS = 100
MAX_KEEPALIVE_CONNECTIONS = 20
KEEPALIVE_EXPIRY_SECONDS = 5.0
# Headers that describe the bytes as sent, not the answer handed back.
_TRANSFER_HEADERS = frozenset({"content-encoding", "content-length", "transfer-encoding"})

_current: ContextVar[Deadline | None] = ContextVar("outside_call_deadline", default=None)


class CallLimitReached(httpx2.TimeoutException):
    """The call's whole limit passed, across its tries, before its answer was read.

    A `TimeoutException`, so every client's existing handling of a
    transport failure applies to it unchanged.
    """


class AnswerTooLarge(httpx2.RemoteProtocolError):
    """The answer was longer than any answer we ask for (MAX_ANSWER_BYTES)."""


@contextmanager
def within(deadline: Deadline) -> Iterator[Deadline]:
    """Cut every socket wait on this thread to `deadline` until the block ends."""
    token = _current.set(deadline)
    try:
        yield deadline
    finally:
        _current.reset(token)


def _cut(
    timeout: float | None, refused: type[httpcore2.TimeoutException]
) -> float | None:
    """`timeout`, or the time the current call has left if that is less."""
    deadline = _current.get()
    if deadline is None:
        return timeout
    left = deadline.remaining()
    if left <= 0:
        # Never 0 to the socket: that would mean "do not wait", not "stop".
        raise refused("the call's limit has passed")
    return left if timeout is None else min(timeout, left)


class _LimitedStream(httpcore2.NetworkStream):
    """A socket whose every wait is cut to the current call's time left."""

    def __init__(self, inner: httpcore2.NetworkStream) -> None:
        self._inner = inner

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._inner.read(max_bytes, _cut(timeout, httpcore2.ReadTimeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._inner.write(buffer, _cut(timeout, httpcore2.WriteTimeout))

    def close(self) -> None:
        self._inner.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore2.NetworkStream:
        return _LimitedStream(
            self._inner.start_tls(
                ssl_context, server_hostname, _cut(timeout, httpcore2.ConnectTimeout)
            )
        )

    def get_extra_info(self, info: str) -> Any:
        return self._inner.get_extra_info(info)


class _LimitedBackend(httpcore2.NetworkBackend):
    """Opens sockets as httpcore2 does, each one a `_LimitedStream`."""

    def __init__(self) -> None:
        self._inner = httpcore2.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore2.NetworkStream:
        return _LimitedStream(
            self._inner.connect_tcp(
                host,
                port,
                _cut(timeout, httpcore2.ConnectTimeout),
                local_address,
                socket_options,
            )
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore2.NetworkStream:
        return _LimitedStream(
            self._inner.connect_unix_socket(
                path, _cut(timeout, httpcore2.ConnectTimeout), socket_options
            )
        )

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


class LimitedTransport(httpx2.HTTPTransport):
    """httpx2's own transport, its sockets opened by `_LimitedBackend`."""

    def __init__(self) -> None:
        super().__init__()
        self._pool = httpcore2.ConnectionPool(
            ssl_context=httpx2.create_ssl_context(),
            max_connections=MAX_CONNECTIONS,
            max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=KEEPALIVE_EXPIRY_SECONDS,
            network_backend=_LimitedBackend(),
        )


def limited_client(timeout: httpx2.Timeout) -> httpx2.Client:
    """A client whose sockets keep to the limit `within` sets. One per caller, reused."""
    return httpx2.Client(timeout=timeout, transport=LimitedTransport())


def exchange(
    client: httpx2.Client,
    method: str,
    url: str,
    deadline: Deadline,
    **request: Any,
) -> httpx2.Response:
    """Send one request and read its whole answer, stopping at `deadline`.

    Raises CallLimitReached, AnswerTooLarge, or the transport's own errors
    (every one an `httpx2.TransportError`).
    """
    if deadline.expired():
        raise CallLimitReached("the call's limit passed before this try")
    with (
        within(deadline),
        client.stream(method, url, **request) as response,
    ):
        pieces: list[bytes] = []
        size = 0
        for piece in response.iter_bytes():
            size += len(piece)
            if size > MAX_ANSWER_BYTES:
                raise AnswerTooLarge("the answer was longer than any we ask for")
            pieces.append(piece)
            if deadline.expired():
                raise CallLimitReached(
                    "the call's limit passed while its answer was read"
                )
        # The answer as decoded, so it is never decoded twice, under the
        # headers that still describe it.
        return httpx2.Response(
            response.status_code,
            headers=[
                (name, value)
                for name, value in response.headers.multi_items()
                if name.lower() not in _TRANSFER_HEADERS
            ],
            content=b"".join(pieces),
            request=response.request,
        )

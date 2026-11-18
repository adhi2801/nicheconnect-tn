"""HTTP with the outside world that never outlives its call's limit (item 118, D-186).

Every client that calls out over HTTP (WhatsApp through MSG91, the DNS and
RDAP lookups, Instagram and YouTube, the timestamp authorities, and the
Claude API through its SDK) is made by `limited_client`, and each call runs
`within` one `Deadline` for the whole call, across its tries:

- **every wait on the socket is cut to the time left.** A connect, a TLS
  handshake, a write or a read waits at most its own limit (connect 3 s,
  read 10 s; backend.md section 6) or what the call has left, whichever is
  less, and none starts once the limit has passed. A server that trickles a
  byte at a time, each inside the read timeout, in its headers or its body,
  is cut off at the limit rather than holding a worker for ever: httpx2
  itself has only per-wait limits (connect, read, write, pool), never one
  on the whole. A name that resolves to several addresses is connected
  one address at a time, each connect's wait cut anew, so k unreachable
  addresses still end at the limit. A request is sent one `send` at a time
  (at most 16 KiB each), each `send`'s wait cut to the time left, so a
  server reading it slowly is cut off at the limit too;
- **the answer is read piece by piece** (`exchange`), at most
  `MAX_ANSWER_BYTES` of it, so an answer that never ends cannot fill memory
  either.

The socket's waits are cut by a network backend that reads the deadline set
by `within` on this thread; outside `within` it changes nothing. **What it
does not cut:** a wait for a free connection in the client's own pool (100
connections), which is not a socket wait; it keeps the client's pool limit;
the name lookup (`socket.getaddrinfo` takes no timeout, so a resolver that
never answers would hold the call; the image bounds every lookup instead,
`RES_OPTIONS` at 1 s a try, twice, D-186 point 14); and a TLS handshake trickled a byte at a time,
whose several socket waits share the one cut made when it starts. It is put
into the transport httpx2 builds (`HTTPTransport._pool`, replaced with a
pool given that backend), the one seam httpx2 offers no public way to set.

**No proxy from the environment.** httpx2 reads `HTTPS_PROXY`, `HTTP_PROXY`
and `NO_PROXY` only for a client given no transport of its own
(`httpx2._client`, `allow_env_proxies = trust_env and transport is None`),
so these clients go straight to the host whatever those say. The tasks as
described in `infra/` reach the internet directly (a public address used
for outbound only, `compute.tf`), with no proxy; one added later would need
its own `httpcore2.HTTPProxy` given this backend, and a test.
"""

import socket
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
# A request is written in pieces this size, each wait cut to the time left:
# a JSON body or a timestamp query is one piece, a screenshot sent to the
# Claude API many.
WRITE_PIECE_BYTES = 16 * 1024
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
        """Send `buffer`, each `send` on the socket its own wait cut to the time left.

        httpcore2 sends a buffer with one timeout for every `send` in turn,
        and a `send` returns as soon as the socket takes any bytes, so a
        server reading a little inside each wait would hold a whole write
        for as long as it liked. Here each `send` (at most
        WRITE_PIECE_BYTES) waits only what the call has left when it
        starts, and none starts once the limit has passed. A stream with no
        socket of its own (httpcore2's TLS inside TLS, used only through a
        proxy, which these clients never have) is written in pieces instead.
        """
        view = memoryview(buffer)
        sock = self._inner.get_extra_info("socket")
        if sock is None:
            for start in range(0, len(view), WRITE_PIECE_BYTES):
                self._inner.write(
                    bytes(view[start : start + WRITE_PIECE_BYTES]),
                    _cut(timeout, httpcore2.WriteTimeout),
                )
            return
        while view:
            sock.settimeout(_cut(timeout, httpcore2.WriteTimeout))
            try:
                sent = sock.send(view[:WRITE_PIECE_BYTES])
            except TimeoutError as error:
                raise httpcore2.WriteTimeout(str(error)) from error
            except OSError as error:
                raise httpcore2.WriteError(str(error)) from error
            view = view[sent:]

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


def _addresses(host: str, port: int) -> list[tuple[str, int]]:
    """Every address `host` resolves to, in the resolver's order, as connect takes them.

    The name lookup itself is not cut: `getaddrinfo` takes no timeout
    (the image's `RES_OPTIONS` bounds it, D-186 point 14). Its failure is a ConnectError, as httpcore2's own.
    """
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise httpcore2.ConnectError(f"{host} could not be resolved") from error
    return [(str(info[4][0]), int(info[4][1])) for info in found]


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
        """Connect to each of the host's addresses in turn, each wait cut anew.

        httpcore2 hands the name to `socket.create_connection`, which tries
        every address the name resolves to with the same whole timeout, so a
        name with k unreachable addresses would wait k times the cut. Here
        the name is resolved once, then each address is tried with the time
        the call has left at that moment, and none once it has passed. The
        TLS handshake still names the host (httpcore2 passes it to
        `start_tls` itself), so connecting by address changes no check.
        Outside `within`, httpcore2's own path, unchanged.
        """
        options = list(socket_options or [])
        if _current.get() is None:
            stream = self._inner.connect_tcp(host, port, timeout, local_address, options)
            return _LimitedStream(stream)
        failure: httpcore2.NetworkError | httpcore2.TimeoutException | None = None
        for address, address_port in _addresses(host, port):
            # Raises once the limit has passed: no further address is tried.
            wait = _cut(timeout, httpcore2.ConnectTimeout)
            try:
                stream = self._inner.connect_tcp(
                    address, address_port, wait, local_address, options
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as error:
                failure = error
                continue
            return _LimitedStream(stream)
        if failure is None:
            raise httpcore2.ConnectError(f"{host} has no address")
        raise failure

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

"""One outside HTTP call never outlives its limit (item 118, D-186).

Two kinds of test, one per guard (testing.md section 2):
- a fake transport and a fake clock, for the checks `exchange` makes itself
  (before a try, after each piece, the size of the answer);
- a real server on a real socket (`tests/misbehaving_server.py`), for the
  socket waits the limited transport cuts: a server that never answers, or
  trickles its headers or its body a byte at a time, must be cut off at the
  limit, measured with the clock, and one that fails once must still answer.
"""

import gzip

import httpx2
import pytest

from app.core.deadline import Deadline
from app.core.outside_http import (
    MAX_ANSWER_BYTES,
    AnswerTooLarge,
    CallLimitReached,
    exchange,
    limited_client,
    within,
)
from tests.misbehaving_server import full_backlog, misbehaving, timed

TIMEOUT = httpx2.Timeout(10.0, connect=3.0)
LIMIT = 1.0
# How far past its limit a call may end: the time to notice, never a wait.
SLACK = 0.5


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def answering(*pieces: bytes, clock: Clock | None = None, step: float = 0.0):
    """A transport answering 200 with `pieces`, moving `clock` on by `step` per piece."""

    def body():
        for piece in pieces:
            if clock is not None:
                clock.now += step
            yield piece

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=body())

    return httpx2.Client(transport=httpx2.MockTransport(handler), timeout=TIMEOUT)


# --- the checks exchange makes itself ------------------------------------------


def test_a_whole_answer_within_the_limit_is_returned():
    clock = Clock()
    client = answering(b'{"a": ', b"1}", clock=clock, step=1.0)

    response = exchange(client, "GET", "https://example.test/", Deadline(15, clock))

    assert response.status_code == 200
    assert response.json() == {"a": 1}


def test_no_try_starts_once_the_limit_has_passed():
    clock = Clock()
    deadline = Deadline(15, clock)
    clock.now = 15.0
    sent: list[httpx2.Request] = []
    client = httpx2.Client(
        transport=httpx2.MockTransport(lambda r: sent.append(r) or httpx2.Response(200))
    )

    with pytest.raises(CallLimitReached):
        exchange(client, "GET", "https://example.test/", deadline)

    assert sent == []


def test_an_answer_still_coming_when_the_limit_passes_is_cut_off():
    """The check after each piece, with no socket involved: 3 s a piece, 15 s allowed."""
    clock = Clock()
    client = answering(*([b"x"] * 10), clock=clock, step=3.0)

    with pytest.raises(CallLimitReached):
        exchange(client, "GET", "https://example.test/", Deadline(15, clock))

    assert clock.now == 15.0  # stopped at the fifth piece, not the tenth


def test_an_answer_longer_than_any_we_ask_for_is_refused():
    client = answering(b"x" * MAX_ANSWER_BYTES, b"x")

    with pytest.raises(AnswerTooLarge):
        exchange(client, "GET", "https://example.test/", Deadline(15))


def test_an_answer_of_exactly_the_most_allowed_is_kept():
    client = answering(b"x" * (MAX_ANSWER_BYTES // 2), b"x" * (MAX_ANSWER_BYTES // 2))

    response = exchange(client, "GET", "https://example.test/", Deadline(15))

    assert len(response.content) == MAX_ANSWER_BYTES


def test_both_refusals_are_transport_errors_every_client_already_handles():
    assert issubclass(CallLimitReached, httpx2.TransportError)
    assert issubclass(AnswerTooLarge, httpx2.TransportError)


def test_a_compressed_answer_is_decoded_once_and_counted_decoded():
    packed = gzip.compress(b'{"ok": true}')

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=packed, headers={"Content-Encoding": "gzip"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))

    response = exchange(client, "GET", "https://example.test/", Deadline(15))

    assert response.json() == {"ok": True}
    assert "content-encoding" not in response.headers


def test_a_compressed_answer_that_unpacks_too_large_is_refused():
    """A small gzip that unpacks past the cap is refused, not unpacked into memory."""
    packed = gzip.compress(b"0" * (MAX_ANSWER_BYTES + 1))

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=packed, headers={"Content-Encoding": "gzip"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))

    assert len(packed) < MAX_ANSWER_BYTES // 100
    with pytest.raises(AnswerTooLarge):
        exchange(client, "GET", "https://example.test/", Deadline(15))


def test_the_request_and_its_headers_are_sent_as_given():
    sent: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, json={})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))

    exchange(
        client,
        "POST",
        "https://example.test/x",
        Deadline(15),
        json={"a": 1},
        headers={"authkey": "k"},
    )

    [request] = sent
    assert request.method == "POST"
    assert request.headers["authkey"] == "k"
    assert request.content == b'{"a":1}'


# --- a real socket ------------------------------------------------------------------


def call(url: str, limit: float = LIMIT):
    client = limited_client(TIMEOUT)
    return timed(lambda: exchange(client, "GET", url, Deadline(limit)))


@pytest.mark.parametrize("behaviour", ["silent", "trickle_headers", "trickle_body"])
def test_a_server_that_holds_the_call_is_cut_off_at_the_limit(behaviour):
    """10 s read waits, every byte inside them: only the whole limit ends it."""
    with misbehaving(behaviour) as server:
        outcome, elapsed = call(server.url)

    assert isinstance(outcome, httpx2.TimeoutException)
    assert len(server.requests) == 1
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


def test_a_server_that_answers_is_read_whole_through_the_limited_client():
    with misbehaving("answer", body=b'{"fine": 1}') as server:
        outcome, elapsed = call(server.url)

    assert isinstance(outcome, httpx2.Response)
    assert outcome.json() == {"fine": 1}
    assert elapsed < LIMIT


def test_outside_a_call_the_limited_client_keeps_its_own_waits():
    """No deadline set: the socket waits are the client's own, here 0.3 s."""
    client = limited_client(httpx2.Timeout(0.3))
    with misbehaving("silent") as server:
        outcome, elapsed = timed(lambda: client.get(server.url))

    assert isinstance(outcome, httpx2.ReadTimeout)
    assert 0.25 <= elapsed < 0.3 + SLACK


def test_within_cuts_every_socket_wait_on_the_thread_to_the_time_left():
    client = limited_client(TIMEOUT)
    with misbehaving("trickle_body") as server:

        def read_all() -> bytes:
            with within(Deadline(LIMIT)):
                return client.get(server.url).content

        outcome, elapsed = timed(read_all)

    assert isinstance(outcome, httpx2.ReadTimeout)
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


# --- every phase of a try, on a real socket ---------------------------------------
# Each with a whole limit (1 s) shorter than the phase's own wait (connect 3 s,
# write 10 s), so only the cut to the time left can end it in time.


def test_a_connect_that_stalls_is_cut_off_at_the_limit():
    """A listener whose queue is full: the connect would wait its own 3 s (or,
    on Windows, be refused after about 2 s); cut to the time left, it ends at 1 s."""
    client = limited_client(TIMEOUT)
    with full_backlog() as url:
        outcome, elapsed = timed(lambda: exchange(client, "GET", url, Deadline(LIMIT)))

    assert isinstance(outcome, httpx2.ConnectTimeout), outcome
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


def test_a_tls_handshake_never_answered_is_cut_off_at_the_limit():
    """The server takes the connection and never sends its hello: the handshake
    would wait the connect's own 3 s; cut to the time left, it ends at 1 s."""
    client = limited_client(TIMEOUT)
    with misbehaving("deaf") as server:
        url = f"https://127.0.0.1:{server.port}/"
        outcome, elapsed = timed(lambda: exchange(client, "GET", url, Deadline(LIMIT)))

    assert isinstance(outcome, httpx2.ConnectTimeout), outcome
    assert server.connections == 1
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


BIG_REQUEST = b"x" * (32 * 1024 * 1024)


def test_a_request_the_server_never_reads_is_cut_off_at_the_limit():
    """32 MiB to a server that reads nothing: the socket's buffers fill and the
    write would wait its own 10 s; cut to the time left, it ends at 1 s."""
    client = limited_client(TIMEOUT)
    with misbehaving("deaf", receive_buffer=4096) as server:
        outcome, elapsed = timed(
            lambda: exchange(
                client, "POST", server.url, Deadline(LIMIT), content=BIG_REQUEST
            )
        )

    assert isinstance(outcome, httpx2.WriteTimeout), outcome
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


def test_a_request_read_slowly_is_cut_off_at_the_limit():
    """The server reads 16 KiB every 0.05 s, each inside the write's wait: one
    write of the whole 32 MiB would run about 100 s. Each `send`'s wait cut to
    the time left, it ends at the limit."""
    client = limited_client(TIMEOUT)
    with misbehaving(
        "slow_reader", receive_buffer=4096, gap=0.05, read_bytes=16384
    ) as server:
        outcome, elapsed = timed(
            lambda: exchange(
                client, "POST", server.url, Deadline(LIMIT), content=BIG_REQUEST
            )
        )

    assert isinstance(outcome, httpx2.WriteTimeout), outcome
    assert 0 < server.received < len(BIG_REQUEST)
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


# --- a name with several addresses, and a slow reader send by send --------------


def test_each_address_of_a_name_is_tried_with_the_time_left(monkeypatch):
    """A name resolving to three addresses that never accept: each connect would
    wait its own 0.9 s, 2.7 s in all, past the 1 s limit. Each address is tried
    with what the call has left, so the call ends at the limit, two tried."""
    import socket as sockets

    real = sockets.getaddrinfo
    with full_backlog() as a, full_backlog() as b, full_backlog() as c:
        ports = [int(url.rsplit(":", 1)[1]) for url in (a, b, c)]
        asked: list[str] = []

        def three_addresses(host, port, *args, **kwargs):
            if host != "unreachable.test":
                return real(host, port, *args, **kwargs)
            asked.append(host)
            return [
                (sockets.AF_INET, sockets.SOCK_STREAM, 6, "", ("127.0.0.1", p))
                for p in ports
            ]

        monkeypatch.setattr(sockets, "getaddrinfo", three_addresses)
        client = limited_client(httpx2.Timeout(10.0, connect=0.9))
        outcome, elapsed = timed(
            lambda: exchange(client, "GET", "http://unreachable.test/", Deadline(LIMIT))
        )

    assert isinstance(outcome, httpx2.ConnectTimeout), outcome
    assert asked == ["unreachable.test"]
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


def test_the_next_address_is_tried_when_one_refuses(monkeypatch):
    """The first address refuses at once; the second answers."""
    import socket as sockets

    real = sockets.getaddrinfo
    closed = sockets.socket()
    closed.bind(("127.0.0.1", 0))
    refusing = closed.getsockname()[1]
    closed.close()
    with misbehaving("answer", body=b"ok") as server:

        def refusing_then_answering(host, port, *args, **kwargs):
            if host != "two.test":
                return real(host, port, *args, **kwargs)
            return [
                (sockets.AF_INET, sockets.SOCK_STREAM, 6, "", ("127.0.0.1", p))
                for p in (refusing, server.port)
            ]

        monkeypatch.setattr(sockets, "getaddrinfo", refusing_then_answering)
        client = limited_client(TIMEOUT)
        answer = exchange(client, "GET", "http://two.test/", Deadline(5.0))

    assert answer.content == b"ok"


def test_a_name_that_cannot_be_resolved_is_a_connect_error(monkeypatch):
    import socket as sockets

    def no_such_name(*args, **kwargs):
        raise sockets.gaierror("no such name")

    monkeypatch.setattr(sockets, "getaddrinfo", no_such_name)
    client = limited_client(TIMEOUT)

    with pytest.raises(httpx2.ConnectError):
        exchange(client, "GET", "http://nowhere.test/", Deadline(LIMIT))


class _TricklingSocket:
    """Takes one byte per `send`, each after `step` seconds of the clock."""

    def __init__(self, clock: Clock, step: float) -> None:
        self.clock = clock
        self.step = step
        self.waits: list[float | None] = []
        self.sent = b""

    def settimeout(self, timeout: float | None) -> None:
        self.waits.append(timeout)

    def send(self, data) -> int:
        self.clock.now += self.step
        self.sent += bytes(data[:1])
        return 1


def test_each_send_waits_only_what_the_call_has_left():
    """A reader taking a byte each 0.3 s: one write's every `send` would wait
    its own 10 s. Each is cut to the time left, and the fourth, past the
    limit, is never begun."""
    import httpcore2

    from app.core.outside_http import _LimitedStream

    clock = Clock()
    sock = _TricklingSocket(clock, step=0.3)
    stream = _LimitedStream(httpcore2._backends.sync.SyncStream(sock))

    with within(Deadline(LIMIT, clock)), pytest.raises(httpcore2.WriteTimeout):
        stream.write(b"abcdef", timeout=10.0)

    assert sock.sent == b"abcd"
    assert sock.waits == pytest.approx([1.0, 0.7, 0.4, 0.1])

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
from tests.misbehaving_server import misbehaving, timed

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

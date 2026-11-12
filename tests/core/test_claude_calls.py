"""Calling the Claude API within a whole limit (item 118, D-186).

The loop is tested with fakes (tries counted, each try's limit read, no
real waiting), and the SDK once against a real socket, to prove its client
is the limited one: a trickled answer ends at the limit.
"""

import anthropic
import httpx2
import pytest

from app.core import claude_calls
from app.core.claude_calls import (
    CALL_LIMIT_SECONDS,
    TRIES,
    TRY_LIMIT_SECONDS,
    call_claude,
    claude_http_client,
    is_retryable,
)
from app.core.outside_http import LimitedTransport
from tests.misbehaving_server import misbehaving, timed

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(status: int) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(
        "refused", response=httpx2.Response(status, request=REQUEST), body=None
    )


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Sender:
    """Raises each queued error in turn, then answers; each try takes `takes` seconds."""

    def __init__(self, clock: Clock, *errors: Exception, takes: float = 0.0) -> None:
        self.clock = clock
        self.errors = list(errors)
        self.takes = takes
        self.limits: list[float] = []

    def __call__(self, timeout: float) -> str:
        self.limits.append(timeout)
        self.clock.now += self.takes
        if self.errors:
            raise self.errors.pop(0)
        return "message"


def run(sender: Sender, clock: Clock):
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    return call_claude(sender, sleep=sleep, jitter=lambda: 0.5, clock=clock), sleeps


# --- which errors are tried again -------------------------------------------------


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 529])
def test_a_status_a_second_try_can_cure_is_tried_again(status):
    assert is_retryable(status_error(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 413, 422])
def test_a_status_that_says_the_request_is_wrong_is_not(status):
    assert is_retryable(status_error(status)) is False


def test_no_connection_and_a_timeout_are_tried_again():
    assert is_retryable(anthropic.APIConnectionError(request=REQUEST)) is True
    assert is_retryable(anthropic.APITimeoutError(request=REQUEST)) is True


def test_an_error_that_is_not_the_apis_is_not_tried_again():
    assert is_retryable(ValueError("a bug of ours")) is False


# --- the loop ---------------------------------------------------------------------


def test_the_limits_are_the_approved_ones():
    """D-186: 150 s in all, 60 s a try, 3 tries."""
    assert (CALL_LIMIT_SECONDS, TRY_LIMIT_SECONDS, TRIES) == (150.0, 60.0, 3)


def test_an_overloaded_api_is_tried_three_times_then_given_up():
    clock = Clock()
    sender = Sender(clock, status_error(529), status_error(529), status_error(529))

    with pytest.raises(anthropic.APIStatusError):
        run(sender, clock)

    assert len(sender.limits) == 3


def test_one_overload_then_an_answer_is_the_answer():
    clock = Clock()
    sender = Sender(clock, status_error(529))

    message, sleeps = run(sender, clock)

    assert message == "message"
    assert sleeps == [0.5]


def test_a_refused_request_is_never_sent_twice():
    clock = Clock()
    sender = Sender(clock, status_error(400))

    with pytest.raises(anthropic.APIStatusError):
        run(sender, clock)

    assert len(sender.limits) == 1


def test_every_try_is_cut_to_what_the_150_seconds_leave():
    clock = Clock()
    sender = Sender(
        clock,
        anthropic.APITimeoutError(request=REQUEST),
        anthropic.APITimeoutError(request=REQUEST),
        takes=60.0,
    )

    run(sender, clock)

    assert sender.limits[:2] == [60.0, 60.0]
    assert sender.limits[2] == pytest.approx(150 - 120 - 0.5 - 1.0)


# --- the SDK's client ---------------------------------------------------------------


def test_the_sdk_is_given_the_limited_client():
    client = claude_http_client()

    assert isinstance(client._transport, LimitedTransport)
    assert client.timeout.read == TRY_LIMIT_SECONDS
    assert client.timeout.connect == 3.0


def sdk(base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="sk-ant-test-only",
        base_url=base_url,
        max_retries=0,
        http_client=claude_http_client(),
    )


def ask(client: anthropic.Anthropic):
    return lambda timeout: client.messages.create(
        model="claude-test",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
        timeout=timeout,
    )


def test_a_trickled_answer_ends_at_the_whole_limit(monkeypatch):
    """Every byte inside the 60 s read wait: only the call's limit can end it."""
    monkeypatch.setattr(claude_calls, "CALL_LIMIT_SECONDS", 1.0)
    with misbehaving("trickle_body") as server:
        outcome, elapsed = timed(lambda: call_claude(ask(sdk(server.url))))

    assert isinstance(outcome, anthropic.APITimeoutError)
    assert len(server.requests) == 1  # no time left for another try
    assert 0.95 <= elapsed < 1.5


def test_an_overloaded_api_that_recovers_answers_on_the_second_try(monkeypatch):
    monkeypatch.setattr(claude_calls, "BASE_DELAY_SECONDS", 0.05)
    message = (
        b'{"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",'
        b' "content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn",'
        b' "stop_sequence": null, "usage": {"input_tokens": 1, "output_tokens": 1}}'
    )
    with misbehaving("flaky", fail_status=529, body=message) as server:
        outcome, elapsed = timed(lambda: call_claude(ask(sdk(server.url))))

    assert outcome.content[0].text == "hi"
    assert len(server.requests) == 2
    assert elapsed < 2.0

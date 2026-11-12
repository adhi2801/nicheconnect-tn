"""Calling the Claude API within a whole limit (item 118, D-186).

Both readers of the Claude API (proof screenshots, D-070; campaign briefs,
D-156) call it through `call_claude`, from a background job only. The SDK's
own retries are switched off (`max_retries=0`): it would retry inside each
try, multiplying the 60 s wait by up to four with nothing bounding the sum.
Instead:

- at most 3 tries, each cut to 60 s or the time left, whichever is less;
- 150 s for the whole call, so a job's run is never held longer by one item;
- full-jitter waits of up to 1 s, then 2 s, between tries (`app.core.retrying`);
- only an error a second try can cure is tried again: no connection or a
  timeout, 408, 429, and every 5xx, Anthropic's 529 "overloaded" among them.
  A 4xx says the request itself is wrong, and would only be repeated;
- the SDK's client is made by `claude_http_client`, so every socket wait of
  every try is cut to the time the whole call has left
  (`app.core.outside_http`): an answer trickled a byte at a time ends at the
  150 s like any other.
"""

import random
import time
from collections.abc import Callable
from typing import Any

import httpx2

from app.core.deadline import Clock, Deadline
from app.core.outside_http import limited_client, within
from app.core.retrying import within_tries

# What a caller is given to make its call: `call_claude`, or a test's own.
ClaudeCall = Callable[[Callable[[float], Any]], Any]

# The whole call: 3 tries of 60 s would be 180; the limit keeps the third short.
CALL_LIMIT_SECONDS = 150.0
# One try: a screenshot read or a brief drafted at low effort answers well
# inside it, and a stuck connection gives up rather than waiting 10 minutes,
# the SDK's default (Anthropic's Python SDK reference, read 12 November 2026).
TRY_LIMIT_SECONDS = 60.0
TRIES = 3
BASE_DELAY_SECONDS = 1.0
RETRY_STATUSES = frozenset({408, 429})
CONNECT_LIMIT_SECONDS = 3.0


def is_retryable(error: Exception) -> bool:
    """Whether trying the same request again could succeed."""
    import anthropic

    if isinstance(error, anthropic.APIConnectionError):
        # Covers APITimeoutError, which is a kind of it.
        return True
    if isinstance(error, anthropic.APIStatusError):
        return error.status_code in RETRY_STATUSES or error.status_code >= 500
    return False


def claude_http_client() -> httpx2.Client:
    """The HTTP client the Anthropic SDK is given: its sockets keep to the call's limit."""
    return limited_client(
        httpx2.Timeout(TRY_LIMIT_SECONDS, connect=CONNECT_LIMIT_SECONDS)
    )


def call_claude[T](
    send: Callable[[float], T],
    *,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    clock: Clock = time.monotonic,
) -> T:
    """`send(timeout_for_this_try)`, within the limits above. Raises the last error."""
    with within(Deadline(CALL_LIMIT_SECONDS, clock)) as deadline:
        return within_tries(
            send,
            deadline=deadline,
            tries=TRIES,
            try_limit=TRY_LIMIT_SECONDS,
            retryable=is_retryable,
            base_delay=BASE_DELAY_SECONDS,
            sleep=sleep,
            jitter=jitter,
        )

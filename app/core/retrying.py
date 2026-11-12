"""Trying a call again, within its whole limit (item 118, D-186).

The rule AWS's Builders' Library publishes ("Timeouts, retries, and backoff
with jitter"): a bounded number of tries, an exponential step between them,
and full jitter, a wait chosen anywhere from none to the step, so clients
failing together do not come back together. Only an error a second try can
cure is tried again. Every try is cut to the time the whole call has left,
and no wait is begun that would leave no time for the try after it.

Pure apart from the `send`, `sleep` and `jitter` it is given, so tests count
tries and waits without waiting (testing.md section 5).
"""

from collections.abc import Callable

from app.core.deadline import Deadline


def full_jitter_pause(attempt: int, base_delay: float, jitter: float) -> float:
    """The wait after try `attempt` (1 for the first): `jitter` in [0, 1) of the step."""
    return jitter * base_delay * 2.0 ** (attempt - 1)


def within_tries[T](
    send: Callable[[float], T],
    *,
    deadline: Deadline,
    tries: int,
    try_limit: float,
    retryable: Callable[[Exception], bool],
    base_delay: float,
    sleep: Callable[[float], None],
    jitter: Callable[[], float],
) -> T:
    """`send(seconds_this_try_may_take)`, tried at most `tries` times before `deadline`.

    Raises the last error when the tries are spent, the error cannot be cured
    by trying again, or no time is left for another try.
    """
    if tries < 1:
        raise ValueError("at least one try")
    attempt = 1
    while True:
        try:
            return send(deadline.capped(try_limit))
        except Exception as error:
            if attempt >= tries or not retryable(error):
                raise
            pause = full_jitter_pause(attempt, base_delay, jitter())
            if pause >= deadline.remaining():
                raise
        sleep(pause)
        attempt += 1

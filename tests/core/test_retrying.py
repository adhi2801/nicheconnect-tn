"""Trying a call again, within its whole limit (item 118, D-186).

Fakes only: the tries are counted, the waits recorded, and the clock moved
by hand, so nothing sleeps (testing.md section 5).
"""

import pytest

from app.core.deadline import Deadline
from app.core.retrying import full_jitter_pause, within_tries


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Flaky(Exception):
    """An error a second try can cure."""


class Wrong(Exception):
    """An error no second try can cure."""


class Calls:
    """Fails with each queued error in turn, then answers; each try takes `takes` seconds."""

    def __init__(self, clock: Clock, *errors: Exception, takes: float = 0.0) -> None:
        self.clock = clock
        self.errors = list(errors)
        self.takes = takes
        self.limits: list[float] = []

    def __call__(self, limit: float) -> str:
        self.limits.append(limit)
        self.clock.now += self.takes
        if self.errors:
            raise self.errors.pop(0)
        return "answer"


def tried(calls: Calls, clock: Clock, *, limit=150.0, tries=3, try_limit=60.0):
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    result = within_tries(
        calls,
        deadline=Deadline(limit, clock),
        tries=tries,
        try_limit=try_limit,
        retryable=lambda error: isinstance(error, Flaky),
        base_delay=1.0,
        sleep=sleep,
        jitter=lambda: 0.5,
    )
    return result, sleeps


def test_an_answer_at_once_is_one_try_and_no_wait():
    clock = Clock()
    calls = Calls(clock)

    result, sleeps = tried(calls, clock)

    assert result == "answer"
    assert calls.limits == [60.0]
    assert sleeps == []


def test_a_curable_failure_is_tried_again_after_a_jittered_wait():
    clock = Clock()
    calls = Calls(clock, Flaky(), Flaky())

    result, sleeps = tried(calls, clock)

    assert result == "answer"
    assert len(calls.limits) == 3
    assert sleeps == [0.5, 1.0]  # half of 1 s, then half of 2 s


def test_the_tries_are_never_more_than_allowed():
    clock = Clock()
    calls = Calls(clock, Flaky(), Flaky(), Flaky(), Flaky())

    with pytest.raises(Flaky):
        tried(calls, clock)

    assert len(calls.limits) == 3


def test_an_error_no_second_try_can_cure_is_raised_at_once():
    clock = Clock()
    calls = Calls(clock, Wrong())

    with pytest.raises(Wrong):
        tried(calls, clock)

    assert len(calls.limits) == 1


def test_each_try_is_cut_to_the_time_the_call_has_left():
    """150 s in all, 60 s a try: a third try after two full ones has 30 s."""
    clock = Clock()
    calls = Calls(clock, Flaky(), Flaky(), takes=60.0)

    tried(calls, clock)

    assert calls.limits[0] == 60.0
    assert calls.limits[1] == 60.0
    assert calls.limits[2] == pytest.approx(150 - 120 - 0.5 - 1.0)


def test_no_wait_is_begun_that_would_leave_no_time_for_another_try():
    """0.5 s left after the first try, and a 0.5 s wait would spend it: give up now."""
    clock = Clock()
    calls = Calls(clock, Flaky(), takes=149.5)

    with pytest.raises(Flaky):
        tried(calls, clock, tries=3)

    assert len(calls.limits) == 1


def test_a_wait_shorter_than_the_time_left_is_still_taken():
    clock = Clock()
    calls = Calls(clock, Flaky(), takes=148.0)

    result, sleeps = tried(calls, clock)

    assert result == "answer"
    assert sleeps == [0.5]
    assert calls.limits[1] == pytest.approx(1.5)


def test_at_least_one_try_is_required():
    clock = Clock()

    with pytest.raises(ValueError):
        tried(Calls(clock), clock, tries=0)


def test_one_try_allowed_is_one_try():
    clock = Clock()
    calls = Calls(clock, Flaky())

    with pytest.raises(Flaky):
        tried(calls, clock, tries=1)

    assert len(calls.limits) == 1


@pytest.mark.parametrize(
    ("attempt", "jitter", "pause"),
    [(1, 0.0, 0.0), (1, 0.5, 0.5), (2, 0.5, 1.0), (3, 0.25, 1.0), (3, 0.999, 3.996)],
)
def test_the_wait_is_full_jitter_over_a_doubling_step(attempt, jitter, pause):
    """AWS's full jitter: anywhere from none to base x 2^(attempt-1)."""
    assert full_jitter_pause(attempt, 1.0, jitter) == pytest.approx(pause)


def test_the_step_scales_with_the_base_delay():
    assert full_jitter_pause(2, 0.5, 0.5) == pytest.approx(0.5)

"""What holds for every limit and every move of the clock (item 118, D-186; testing.md section 6)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.deadline import Deadline


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


seconds = st.floats(min_value=0, max_value=1e6, allow_nan=False)
moves = st.lists(st.floats(min_value=0, max_value=1e5, allow_nan=False), max_size=20)


@given(limit=seconds, steps=moves)
def test_time_left_only_falls_and_stays_within_the_limit(limit, steps):
    clock = Clock()
    deadline = Deadline(limit, clock)
    before = deadline.remaining()
    # The limit itself, but for the rounding of adding it to the clock's time.
    assert before == pytest.approx(limit, rel=1e-12, abs=1e-9)
    for step in steps:
        clock.now += step
        left = deadline.remaining()
        assert 0 <= left <= before
        before = left


@given(limit=seconds, step=st.floats(min_value=0, max_value=2e6, allow_nan=False))
def test_expired_exactly_when_no_time_is_left(limit, step):
    clock = Clock()
    deadline = Deadline(limit, clock)
    clock.now += step

    assert deadline.expired() == (deadline.remaining() == 0)


@given(
    limit=seconds,
    step=st.floats(min_value=0, max_value=2e6, allow_nan=False),
    wait=st.one_of(st.none(), seconds),
)
def test_a_capped_wait_is_never_longer_than_the_wait_or_the_time_left(limit, step, wait):
    clock = Clock()
    deadline = Deadline(limit, clock)
    clock.now += step

    capped = deadline.capped(wait)

    assert capped <= deadline.remaining()
    if wait is not None:
        assert capped <= wait
        assert capped == min(wait, deadline.remaining())
    else:
        assert capped == deadline.remaining()

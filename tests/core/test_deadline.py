"""A call's whole limit (item 118, D-186), by example; every input is in test_deadline_properties.py."""

import pytest

from app.core.deadline import Deadline, DeadlinePassed


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_a_new_limit_has_all_its_time_left():
    clock = Clock()

    deadline = Deadline(15, clock)

    assert deadline.remaining() == 15
    assert deadline.expired() is False


def test_time_left_falls_as_the_clock_moves():
    clock = Clock()
    deadline = Deadline(15, clock)

    clock.now += 4

    assert deadline.remaining() == 11


def test_the_limit_is_reached_at_its_exact_moment_not_after():
    clock = Clock()
    deadline = Deadline(15, clock)

    clock.now = 114.75
    assert deadline.expired() is False
    clock.now = 115.0
    assert deadline.expired() is True
    assert deadline.remaining() == 0


def test_time_left_never_goes_below_none():
    clock = Clock()
    deadline = Deadline(15, clock)

    clock.now += 40

    assert deadline.remaining() == 0.0


def test_a_wait_is_cut_to_the_time_left():
    clock = Clock()
    deadline = Deadline(15, clock)
    clock.now += 10

    assert deadline.capped(10) == 5
    assert deadline.capped(3) == 3


def test_no_wait_of_its_own_is_the_time_left():
    clock = Clock()
    deadline = Deadline(15, clock)
    clock.now += 6

    assert deadline.capped(None) == 9


def test_a_limit_of_none_is_already_reached():
    assert Deadline(0, Clock()).expired() is True


def test_a_negative_limit_is_refused():
    with pytest.raises(ValueError):
        Deadline(-0.001, Clock())


def test_a_passed_limit_is_a_timeout_every_timeout_handler_sees():
    assert issubclass(DeadlinePassed, TimeoutError)


def test_the_real_clock_is_the_default():
    deadline = Deadline(60)

    assert 59 < deadline.remaining() <= 60

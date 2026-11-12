"""How a background job's run is bounded (item 118, D-186).

One run at a time per schedule, against the real database's advisory locks,
with a concurrency test driven by events, not sleeps (testing.md section 4);
and a run's budget, on a clock the test moves.
"""

import logging
import threading
import time
import uuid

import pytest

from app.core import job_runs
from app.core.deadline import Deadline
from app.core.job_runs import (
    EVERY_MINUTE_BUDGET_SECONDS,
    LONG_BUDGET_SECONDS,
    one_run_at_a_time,
    run_alone,
    within_budget,
)
from app.db.session import engine


def a_schedule() -> str:
    """A name no other test, or session sharing the database, is using."""
    return f"test-schedule-{uuid.uuid4()}"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# --- the budget -----------------------------------------------------------------


def test_the_budgets_are_the_approved_ones():
    """D-186: 45 s for a job run every minute, 10 minutes for the others."""
    assert (EVERY_MINUTE_BUDGET_SECONDS, LONG_BUDGET_SECONDS) == (45.0, 600.0)


def test_without_a_budget_every_item_is_worked():
    assert list(within_budget(range(5), None, "test")) == [0, 1, 2, 3, 4]


def test_with_time_to_spare_every_item_is_worked():
    clock = Clock()

    assert list(within_budget(range(5), Deadline(45, clock), "test")) == [0, 1, 2, 3, 4]


def test_once_the_budget_is_spent_no_new_item_is_started(caplog):
    """Each item takes 20 s of a 45 s budget: the third starts at 40 s, the fourth never."""
    clock = Clock()
    started = []

    with caplog.at_level(logging.WARNING, logger="app.core.job_runs"):
        for item in within_budget(range(6), Deadline(45, clock), "proof_files.read"):
            started.append(item)
            clock.now += 20

    assert started == [0, 1, 2]
    assert "job.budget_spent job=proof_files.read left=3" in caplog.text


def test_a_budget_spent_before_the_first_item_starts_none(caplog):
    clock = Clock()
    budget = Deadline(45, clock)
    clock.now = 45

    with caplog.at_level(logging.WARNING, logger="app.core.job_runs"):
        assert list(within_budget(["a", "b"], budget, "test")) == []
    assert "left=2" in caplog.text


def test_nothing_is_logged_when_the_budget_holds(caplog):
    with caplog.at_level(logging.WARNING, logger="app.core.job_runs"):
        list(within_budget(range(3), Deadline(45, Clock()), "test"))

    assert "job.budget_spent" not in caplog.text


# --- one run at a time ---------------------------------------------------------


def test_a_run_holds_its_schedule_and_lets_it_go_when_done():
    schedule = a_schedule()

    with one_run_at_a_time(schedule) as first:
        assert first is True
    with one_run_at_a_time(schedule) as again:
        assert again is True


def test_a_second_run_while_the_first_works_stops_at_once(caplog):
    """Two runs of one schedule at the same moment: the second does nothing,
    and does not wait for the first. Driven by events, so the overlap happens
    on every run of the test."""
    schedule = a_schedule()
    holding, release = threading.Event(), threading.Event()
    ran: list[str] = []

    def first_run() -> None:
        run_alone(
            schedule, lambda: (ran.append("first"), holding.set(), release.wait(10))
        )

    worker = threading.Thread(target=first_run)
    worker.start()
    try:
        assert holding.wait(10), "the first run never started"
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="app.core.job_runs"):
            second = run_alone(schedule, lambda: ran.append("second"))
        waited = time.monotonic() - started
    finally:
        release.set()
        worker.join(10)

    assert second is False
    assert ran == ["first"]
    assert waited < 1.0  # it tried the lock; it never waited on it
    assert f"job.already_running schedule={schedule}" in caplog.text
    # Once the first is done, the schedule is free again.
    assert run_alone(schedule, lambda: ran.append("third")) is True
    assert ran == ["first", "third"]


def test_two_schedules_never_hold_each_other_up():
    one, other = a_schedule(), a_schedule()

    with one_run_at_a_time(one) as first, one_run_at_a_time(other) as second:
        assert (first, second) == (True, True)


def test_a_run_that_fails_still_lets_its_schedule_go():
    schedule = a_schedule()

    def fails() -> None:
        raise RuntimeError("a job's own failure")

    with pytest.raises(RuntimeError):
        run_alone(schedule, fails)

    assert run_alone(schedule, lambda: None) is True


def test_the_lock_never_takes_a_connection_from_the_pool_requests_use():
    """D-093: requests always find a connection. A run's lock is held on its own."""
    before = engine.pool.checkedout()

    with one_run_at_a_time(a_schedule()) as held:
        assert held is True
        assert engine.pool.checkedout() == before


def test_the_lock_is_its_own_kind_of_lock():
    """Its first key is its own, so it never meets a draft's (40) or a proof file's (70 070)."""
    assert job_runs.RUN_LOCK_NAMESPACE == 118

"""When a Tamil Nadu day ends, for every moment and every day (audit C11)."""

import time
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from app.core.clock import end_of_india_day, india_date

# Hypothesis takes naive bounds and attaches the zone itself (`timezones`).
moments = st.datetimes(
    min_value=datetime(2026, 1, 1),  # noqa: DTZ001
    max_value=datetime(2030, 12, 31),  # noqa: DTZ001
    timezones=st.just(UTC),
)
days = st.dates(min_value=date(2026, 1, 1), max_value=date(2030, 12, 31))


@given(moment=moments, day=days)
def test_a_moment_is_before_the_end_exactly_when_its_tamil_nadu_day_is_not_later(
    moment, day
):
    assert (moment < end_of_india_day(day)) == (india_date(moment) <= day)


@given(day=days)
def test_the_end_is_midnight_in_tamil_nadu_which_is_1830_utc_the_day_before(day):
    end = end_of_india_day(day)

    assert end.tzinfo == UTC
    assert india_date(end) == day + timedelta(days=1)
    assert india_date(end - timedelta(microseconds=1)) == day
    assert (end.hour, end.minute, end.second) == (18, 30, 0)


@given(day=st.dates())
@example(day=date.max)
@example(day=date.min)
def test_the_end_of_any_day_python_has_is_an_answer_never_an_overflow(day):
    """Every date, 1 January 1 to 31 December 9999: adding the day before
    converting overflowed on the last one (the independent review of C11)."""
    end = end_of_india_day(day)

    assert end.tzinfo == UTC
    assert (end.date(), end.hour, end.minute, end.second) == (day, 18, 30, 0)


@pytest.fixture(params=["UTC0", "EST5EDT", "<+14>-14", "IST-5:30"])
def machine_zone(request, monkeypatch):
    """The server's own zone set to each of these in turn: the answer must
    not move. Mutation testing runs with the machine in IST, where reading
    the local zone instead of Tamil Nadu's looks right; a server in UTC
    would then close applications five and a half hours late."""
    if not hasattr(time, "tzset"):
        pytest.skip("the machine's zone can be changed only where tzset exists")
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    yield request.param
    monkeypatch.undo()
    time.tzset()


def test_the_machine_zone_never_moves_a_tamil_nadu_day(machine_zone):
    assert india_date(datetime(2026, 9, 20, 18, 29, 59, tzinfo=UTC)) == date(2026, 9, 20)
    assert india_date(datetime(2026, 9, 20, 18, 30, tzinfo=UTC)) == date(2026, 9, 21)
    assert end_of_india_day(date(2026, 9, 20)) == datetime(
        2026, 9, 20, 18, 30, tzinfo=UTC
    )

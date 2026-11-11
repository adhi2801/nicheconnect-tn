"""When a Tamil Nadu day ends, for every moment and every day (audit C11)."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given
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

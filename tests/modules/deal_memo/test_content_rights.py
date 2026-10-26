"""Where a post's usage window stands (item 70, D-132): the pure rule, and what always holds."""

from datetime import UTC, date, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.deal_memo.content_rights import (
    LAPSING_WITHIN_DAYS,
    RIGHTS_STATES,
    rights_state,
    rights_until,
)

TODAY = date(2026, 10, 26)
ORDER = {"active": 0, "lapsing": 1, "lapsed": 2}


def test_a_window_counts_from_the_tamil_nadu_day_of_approval():
    # 20:00 UTC on 1 October is 01:30 on 2 October in Tamil Nadu.
    late = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)

    assert rights_until(late, 30) == date(2026, 11, 1)
    assert rights_until(late, None) is None


def test_each_state_at_its_edges():
    assert rights_state(None, TODAY) == "not_agreed"
    assert rights_state(TODAY, TODAY) == "lapsed"  # it ends today: no longer covered
    assert rights_state(TODAY + timedelta(days=1), TODAY) == "lapsing"
    assert rights_state(TODAY + timedelta(days=LAPSING_WITHIN_DAYS), TODAY) == "lapsing"
    assert (
        rights_state(TODAY + timedelta(days=LAPSING_WITHIN_DAYS + 1), TODAY) == "active"
    )


days = st.integers(min_value=1, max_value=3650)
# Hypothesis takes naive bounds and adds the zone itself.
moments = st.datetimes(
    min_value=datetime(2026, 1, 1),  # noqa: DTZ001
    max_value=datetime(2030, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)


@given(moments, days, st.integers(min_value=0, max_value=4000))
def test_a_window_only_ever_moves_forward(approved_at, window, later):
    """active, then lapsing, then lapsed: never back, as days pass."""
    until = rights_until(approved_at, window)
    today = approved_at.date()
    first = rights_state(until, today)
    second = rights_state(until, today + timedelta(days=later))

    assert ORDER[second] >= ORDER[first]


@given(moments, days)
def test_a_window_ends_exactly_its_days_after_approval(approved_at, window):
    until = rights_until(approved_at, window)

    assert until is not None
    # The Tamil Nadu day of approval may be the UTC day's next.
    assert 0 <= (until - approved_at.date()).days - window <= 1


@given(st.none() | st.dates(), st.dates())
def test_every_window_has_one_of_the_named_states(until, today):
    assert rights_state(until, today) in RIGHTS_STATES

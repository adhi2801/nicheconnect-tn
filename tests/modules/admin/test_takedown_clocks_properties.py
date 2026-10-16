"""What holds for every order, whenever it arrives and is acted on (item 52, D-090)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.admin import takedown_clocks

# Hypothesis takes naive bounds and adds the zone itself (timezones=).
moments = st.datetimes(
    min_value=datetime(2026, 2, 20),  # noqa: DTZ001
    max_value=datetime(2040, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)
gaps = st.timedeltas(min_value=timedelta(0), max_value=timedelta(days=30))


@given(moments)
def test_every_order_has_exactly_three_hours(received):
    # The same rule the database holds: ck_takedown_order_due_in_three_hours.
    assert takedown_clocks.order_due_at(received) - received == timedelta(hours=3)


@given(moments, gaps)
def test_late_exactly_when_acted_on_more_than_three_hours_after(received, waited):
    due = takedown_clocks.order_due_at(received)

    assert takedown_clocks.is_late(due, received + waited) == (
        waited > timedelta(hours=3)
    )


@given(moments, gaps, gaps)
def test_waiting_longer_never_makes_a_late_takedown_on_time(received, first, more):
    due = takedown_clocks.order_due_at(received)

    if takedown_clocks.is_late(due, received + first):
        assert takedown_clocks.is_late(due, received + first + more)

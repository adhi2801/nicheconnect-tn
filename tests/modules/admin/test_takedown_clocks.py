"""When a takedown is due, and whether it was late (item 52): the rule, without a database."""

from datetime import UTC, datetime, timedelta

from app.modules.admin import takedown_clocks

RECEIVED = datetime(2026, 10, 16, 23, 40, tzinfo=UTC)


def test_an_order_is_due_three_hours_after_it_reached_us():
    assert takedown_clocks.order_due_at(RECEIVED) == RECEIVED + timedelta(hours=3)
    assert timedelta(hours=3) == takedown_clocks.ORDER_WITHIN


def test_withheld_exactly_at_the_deadline_is_in_time():
    due = takedown_clocks.order_due_at(RECEIVED)

    assert not takedown_clocks.is_late(due, withheld_at=due)


def test_withheld_a_moment_after_it_is_late():
    due = takedown_clocks.order_due_at(RECEIVED)

    assert takedown_clocks.is_late(due, withheld_at=due + timedelta(microseconds=1))


def test_the_oldest_order_is_thirty_days():
    assert timedelta(days=30) == takedown_clocks.OLDEST_ORDER

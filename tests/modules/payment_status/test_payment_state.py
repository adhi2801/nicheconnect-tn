"""The payment rules on their exact days (D-027, D-091).

The property tests prove the state only moves forward; they cannot say on
which day. Mutation testing found that moving any boundary by a day, or
counting backwards from it, passed every fast test. These pin each day.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.service import (
    CONFIRMATION_WINDOW_DAYS,
    CONFIRMED,
    DUE,
    LATE,
    PAID,
    UNCONFIRMED,
    UNPAID,
    UNPAID_AFTER_DUE_DAYS,
    confirmation_deadline,
    derive_state,
    unpaid_date_for,
)

DUE_ON = date(2026, 10, 1)
# 10:00 in Tamil Nadu on 1 October.
MARKED = datetime(2026, 10, 1, 4, 30, tzinfo=UTC)


def payment(**fields) -> PaymentStatus:
    return PaymentStatus(amount_paise=800_000, due_on=DUE_ON, **fields)


def test_the_policy_is_fourteen_days_to_unpaid_and_seven_to_confirm():
    assert (UNPAID_AFTER_DUE_DAYS, CONFIRMATION_WINDOW_DAYS) == (14, 7)


def test_silence_becomes_non_payment_fourteen_days_after_the_due_date():
    assert unpaid_date_for(DUE_ON) == date(2026, 10, 15)


@pytest.mark.parametrize(
    ("today", "state"),
    [
        (DUE_ON, DUE),
        (DUE_ON + timedelta(days=1), LATE),
        (DUE_ON + timedelta(days=13), LATE),
        (DUE_ON + timedelta(days=14), UNPAID),
    ],
)
def test_money_not_sent_is_due_then_late_then_unpaid_on_these_days(today, state):
    assert derive_state(payment(), today) == state


def test_with_no_dispute_named_none_is_assumed():
    """The default is no dispute: day fourteen is unpaid without saying so."""
    assert derive_state(payment(), DUE_ON + timedelta(days=14)) == UNPAID


def test_a_dispute_keeps_day_fourteen_late():
    today = DUE_ON + timedelta(days=14)

    assert derive_state(payment(), today, has_open_dispute=True) == LATE


def test_the_creator_has_until_seven_days_after_it_was_marked_sent():
    assert confirmation_deadline(payment(marked_paid_at=MARKED)) == date(2026, 10, 8)


@pytest.mark.parametrize(
    ("today", "state"),
    [
        (date(2026, 10, 1), PAID),
        (date(2026, 10, 7), PAID),
        (date(2026, 10, 8), UNCONFIRMED),
    ],
)
def test_money_said_to_be_sent_is_paid_then_unconfirmed_on_these_days(today, state):
    assert derive_state(payment(marked_paid_at=MARKED), today) == state


def test_the_confirmation_window_is_counted_in_tamil_nadu_days():
    """23:30 on 1 October in UTC is already 2 October in Tamil Nadu."""
    late_night = datetime(2026, 10, 1, 23, 30, tzinfo=UTC)

    assert confirmation_deadline(payment(marked_paid_at=late_night)) == date(2026, 10, 9)


def test_confirmed_money_is_confirmed_on_any_day():
    row = payment(marked_paid_at=MARKED, confirmed_at=MARKED)

    assert derive_state(row, date(2027, 1, 1)) == CONFIRMED

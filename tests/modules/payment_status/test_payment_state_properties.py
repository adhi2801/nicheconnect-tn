"""A payment's state only ever moves forward with time (D-027, D-090).

`derive_state` is worked out on every read. If waiting a day could ever move
a payment back from late to due, or from unpaid to late, two screens read a
day apart would tell a brand opposite things. These try every due date,
every day and every combination of what the two sides said.
"""

from datetime import UTC, date, datetime, time, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.service import (
    CONFIRMED,
    DUE,
    LATE,
    PAID,
    UNCONFIRMED,
    UNPAID,
    derive_state,
)

ORDER = {DUE: 0, LATE: 1, UNPAID: 2, PAID: 3, UNCONFIRMED: 4, CONFIRMED: 5}

days = st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31))
moments = st.builds(
    lambda day, minutes: (
        datetime.combine(day, time(0, 0), tzinfo=UTC) + timedelta(minutes=minutes)
    ),
    days,
    st.integers(min_value=0, max_value=24 * 60 - 1),
)


def payment(due_on, marked_paid_at=None, confirmed_at=None) -> PaymentStatus:
    return PaymentStatus(
        amount_paise=800_000,
        due_on=due_on,
        marked_paid_at=marked_paid_at,
        confirmed_at=confirmed_at,
    )


def walk(row: PaymentStatus, start: date, disputed: bool) -> list[str]:
    return [
        derive_state(row, start + timedelta(days=n), has_open_dispute=disputed)
        for n in range(60)
    ]


@given(due_on=days, start=days, disputed=st.booleans())
def test_money_not_yet_sent_only_moves_from_due_to_late_to_unpaid(
    due_on, start, disputed
):
    states = walk(payment(due_on), start, disputed)

    assert set(states) <= {DUE, LATE, UNPAID}
    assert [ORDER[s] for s in states] == sorted(ORDER[s] for s in states)


@given(due_on=days, start=days)
def test_a_payment_under_dispute_is_never_called_unpaid(due_on, start):
    assert UNPAID not in walk(payment(due_on), start, disputed=True)


@given(due_on=days, marked=moments, start=days, disputed=st.booleans())
def test_money_said_to_be_sent_moves_from_paid_to_unconfirmed_only(
    due_on, marked, start, disputed
):
    states = walk(payment(due_on, marked_paid_at=marked), start, disputed)

    assert set(states) <= {PAID, UNCONFIRMED}
    assert [ORDER[s] for s in states] == sorted(ORDER[s] for s in states)


@given(due_on=days, marked=moments, gap=st.integers(0, 30), start=days)
def test_confirmed_money_stays_confirmed(due_on, marked, gap, start):
    row = payment(
        due_on, marked_paid_at=marked, confirmed_at=marked + timedelta(days=gap)
    )

    assert set(walk(row, start, disputed=False)) == {CONFIRMED}


@given(due_on=days, today=days)
def test_on_or_before_the_due_date_it_is_simply_due(due_on, today):
    if today <= due_on:
        assert derive_state(payment(due_on), today) == DUE

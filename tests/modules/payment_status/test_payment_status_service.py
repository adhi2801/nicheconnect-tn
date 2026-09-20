"""Reading a payment's state out of the facts, and the moves either side makes.

There is no status column: `due`, `late` and `unpaid` are worked out from the
dates against today. These tests are what stands behind that decision.
"""

from datetime import date, timedelta

import pytest

from app.modules.payment_status import service
from app.modules.payment_status.exceptions import (
    BarterMemoHasNoPayment,
    InvalidPaymentReference,
    PaymentAlreadyConfirmed,
    PaymentAlreadyMarkedPaid,
    PaymentNotMarkedPaid,
    PaymentRecordExists,
    UnknownPaymentMethod,
)
from app.modules.payment_status.models import PaymentStatus
from tests.factories import FIXED_NOW
from tests.modules.deal_memo.test_deal_memo_model import build_memo

APPROVED_ON = date(2026, 9, 20)
DUE_ON = date(2026, 9, 27)           # approval + the default 7-day window
UNPAID_ON = date(2026, 10, 11)       # due + 14
RRN = "412345678901"                 # a 12-digit UPI reference
NEFT_UTR = "SBIN226092012345"        # 16 characters
RTGS_UTR = "SBINR52026092000123456"  # 22 characters


def payment(**overrides) -> PaymentStatus:
    """An unsaved row: these rules are pure, so they need no database."""
    fields = {"amount_paise": 800_000, "due_on": DUE_ON}
    fields.update(overrides)
    return PaymentStatus(**fields)


def make_memo(db, **overrides):
    memo = build_memo(db, **overrides)
    db.add(memo)
    db.flush()
    return memo


# --- reading the state ----------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 20), service.DUE),      # the day it was approved
        (date(2026, 9, 26), service.DUE),      # the day before it is due
        (date(2026, 9, 27), service.DUE),      # the due date itself
        (date(2026, 9, 28), service.LATE),     # the day after
        (date(2026, 10, 10), service.LATE),    # still late
        (date(2026, 10, 11), service.UNPAID),  # silence becomes non-payment
        (date(2026, 12, 1), service.UNPAID),
    ],
)
def test_the_state_is_read_from_the_calendar(today, expected):
    assert service.derive_state(payment(), today) == expected


def test_the_due_date_itself_is_not_late():
    """Somebody paying on the last day has paid on time."""
    assert service.derive_state(payment(), DUE_ON) == service.DUE


def test_a_dispute_holds_it_at_late_rather_than_unpaid():
    """D-027: `unpaid` is for silence. A disputed payment is not silence."""
    state = service.derive_state(payment(), UNPAID_ON, has_open_dispute=True)

    assert state == service.LATE


def test_marking_it_paid_stops_the_clock():
    marked = payment(method="upi", reference=RRN, marked_paid_at=FIXED_NOW)

    assert service.derive_state(marked, date(2026, 12, 1)) == service.PAID


def test_confirmation_outranks_everything():
    done = payment(
        method="upi",
        reference=RRN,
        marked_paid_at=FIXED_NOW,
        confirmed_at=FIXED_NOW,
    )

    assert service.derive_state(done, date(2027, 1, 1)) == service.CONFIRMED


def test_every_state_it_can_return_is_a_named_one():
    days = [DUE_ON - timedelta(days=1), DUE_ON, DUE_ON + timedelta(days=5), UNPAID_ON]

    for today in days:
        assert service.derive_state(payment(), today) in service.PAYMENT_STATES


# --- how overdue ----------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expected"),
    [(DUE_ON, 0), (DUE_ON + timedelta(days=1), 1), (DUE_ON + timedelta(days=30), 30)],
)
def test_days_overdue_counts_from_the_due_date(today, expected):
    assert service.days_overdue(payment(), today) == expected


def test_a_paid_record_is_never_overdue():
    marked = payment(
        method="cash", reference="paid at the shop", marked_paid_at=FIXED_NOW
    )

    assert service.days_overdue(marked, date(2027, 1, 1)) == 0


# --- which references a machine could match -------------------------------


def test_a_upi_reference_of_twelve_digits_can_be_matched():
    assert service.is_auto_matchable(payment(method="upi", reference=RRN)) is True


@pytest.mark.parametrize("reference", ["41234567890", "4123456789012", "41234567890a"])
def test_a_upi_reference_of_the_wrong_shape_cannot(reference):
    assert service.is_auto_matchable(payment(method="upi", reference=reference)) is False


@pytest.mark.parametrize(
    ("method", "reference"),
    [
        ("bank_transfer", NEFT_UTR),
        ("bank_transfer", RTGS_UTR),
        ("cash", "at the event"),
    ],
)
def test_only_upi_is_ever_matchable(method, reference):
    """D-027: the others rest on the creator's confirmation."""
    record = payment(method=method, reference=reference)

    assert service.is_auto_matchable(record) is False


def test_a_record_with_no_reference_is_not_matchable():
    assert service.is_auto_matchable(payment()) is False


# --- accepting a reference ------------------------------------------------


@pytest.mark.parametrize("reference", [RRN, NEFT_UTR, RTGS_UTR, "Paid at Pongal event"])
def test_every_real_world_reference_shape_is_accepted(reference):
    """Refusing to record a real payment is a worse failure than storing a
    reference we cannot match automatically."""
    assert service.clean_reference(reference) == reference


def test_surrounding_space_is_tidied_away():
    assert service.clean_reference("  412345678901  ") == RRN


def test_inner_runs_of_space_are_collapsed():
    assert service.clean_reference("paid   in   cash") == "paid in cash"


@pytest.mark.parametrize("reference", ["", "  ", "abc", "x" * 33])
def test_a_reference_of_a_useless_length_is_refused(reference):
    with pytest.raises(InvalidPaymentReference):
        service.clean_reference(reference)


@pytest.mark.parametrize(
    "reference", ["drop table payment;", "<script>alert(1)</script>", "ref$$$x"]
)
def test_a_reference_with_odd_characters_is_refused(reference):
    with pytest.raises(InvalidPaymentReference):
        service.clean_reference(reference)


def test_an_unknown_method_is_refused_with_the_list():
    with pytest.raises(UnknownPaymentMethod) as caught:
        service.check_method("cheque")

    assert "upi" in str(caught.value)


# --- opening the record ---------------------------------------------------


def test_the_due_date_comes_from_the_memos_own_window(db):
    memo = make_memo(db, payment_due_days=10)

    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)

    assert record.due_on == date(2026, 9, 30)


def test_the_default_window_is_seven_days(db):
    memo = make_memo(db)

    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)

    assert record.due_on == DUE_ON


def test_the_amount_is_copied_not_looked_up(db):
    """So the record stays true to what was agreed, whatever happens later."""
    memo = make_memo(db, fee_amount_paise=1_250_000)

    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()
    memo.fee_amount_paise = 1

    assert record.amount_paise == 1_250_000


def test_a_barter_deal_has_no_payment_to_record(db):
    memo = make_memo(db, fee_amount_paise=None)

    with pytest.raises(BarterMemoHasNoPayment):
        service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)


def test_a_memo_cannot_be_given_two_payment_records(db):
    memo = make_memo(db)
    service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()

    with pytest.raises(PaymentRecordExists):
        service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)


# --- the two moves --------------------------------------------------------


def test_the_brand_marks_it_paid(db):
    memo = make_memo(db)
    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()

    service.mark_paid(db, record, method="upi", reference=RRN, now=FIXED_NOW)

    assert record.marked_paid_at == FIXED_NOW
    assert service.derive_state(record, date(2026, 12, 1)) == service.PAID


def test_it_cannot_be_marked_paid_twice(db):
    memo = make_memo(db)
    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()
    service.mark_paid(db, record, method="upi", reference=RRN, now=FIXED_NOW)

    with pytest.raises(PaymentAlreadyMarkedPaid):
        service.mark_paid(db, record, method="cash", reference="again", now=FIXED_NOW)


def test_the_creator_confirms_it_arrived(db):
    memo = make_memo(db)
    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()
    service.mark_paid(db, record, method="upi", reference=RRN, now=FIXED_NOW)

    service.confirm_received(db, record, now=FIXED_NOW + timedelta(hours=2))

    assert service.derive_state(record, date(2026, 12, 1)) == service.CONFIRMED


def test_nothing_can_be_confirmed_before_it_is_marked_paid(db):
    memo = make_memo(db)
    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()

    with pytest.raises(PaymentNotMarkedPaid):
        service.confirm_received(db, record, now=FIXED_NOW)


def test_it_cannot_be_confirmed_twice(db):
    memo = make_memo(db)
    record = service.create_for_memo(db, memo, approved_on=APPROVED_ON, now=FIXED_NOW)
    db.flush()
    service.mark_paid(db, record, method="upi", reference=RRN, now=FIXED_NOW)
    service.confirm_received(db, record, now=FIXED_NOW)

    with pytest.raises(PaymentAlreadyConfirmed):
        service.confirm_received(db, record, now=FIXED_NOW)


# --- who has not been paid ------------------------------------------------


def test_outstanding_lists_only_overdue_unpaid_records(db):
    overdue = service.create_for_memo(
        db, make_memo(db), approved_on=date(2026, 8, 1), now=FIXED_NOW
    )
    # Approved on the 25th, so due on 2 October: not overdue on the 28th.
    not_yet_due = service.create_for_memo(
        db, make_memo(db), approved_on=date(2026, 9, 25), now=FIXED_NOW
    )
    settled = service.create_for_memo(
        db, make_memo(db), approved_on=date(2026, 8, 1), now=FIXED_NOW
    )
    db.flush()
    service.mark_paid(db, settled, method="upi", reference=RRN, now=FIXED_NOW)

    found_ids = {row.id for row in service.list_outstanding(db, on=date(2026, 9, 28))}

    assert overdue.id in found_ids
    assert not_yet_due.id not in found_ids
    assert settled.id not in found_ids


def test_outstanding_puts_the_longest_wait_first(db):
    later = service.create_for_memo(
        db, make_memo(db), approved_on=date(2026, 9, 1), now=FIXED_NOW
    )
    earlier = service.create_for_memo(
        db, make_memo(db), approved_on=date(2026, 8, 1), now=FIXED_NOW
    )
    db.flush()

    found = [
        row
        for row in service.list_outstanding(db, on=date(2026, 9, 28))
        if row.id in {later.id, earlier.id}
    ]

    assert [row.id for row in found] == [earlier.id, later.id]

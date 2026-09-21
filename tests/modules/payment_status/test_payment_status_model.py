"""The payment_status table: what the database itself refuses to store.

We never hold the money, so this row is the only record that it moved. The
constraints here are what stop it becoming a record of something impossible.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.modules.payment_status.models import PAYMENT_METHODS, PaymentStatus
from tests.factories import FIXED_NOW
from tests.modules.deal_memo.test_deal_memo_model import build_memo

DUE_ON = date(2026, 9, 27)
RRN = "412345678901"


def make_memo(db, **overrides):
    memo = build_memo(db, **overrides)
    db.add(memo)
    db.flush()
    return memo


def build_payment(db, **overrides) -> PaymentStatus:
    fields = {
        "amount_paise": 800_000,
        "due_on": DUE_ON,
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
    }
    fields.update(overrides)
    fields.setdefault("deal_memo_id", make_memo(db).id)
    return PaymentStatus(**fields)


def assert_rejected_by(db, payment: PaymentStatus, constraint: str) -> None:
    db.add(payment)
    with pytest.raises(IntegrityError) as caught:
        db.flush()
    assert constraint in str(caught.value)
    db.rollback()


# --- the ordinary case ----------------------------------------------------


def test_a_payment_record_starts_owed_and_unpaid(db):
    payment = build_payment(db)
    db.add(payment)
    db.flush()

    assert payment.id is not None
    assert payment.marked_paid_at is None
    assert payment.confirmed_at is None
    assert payment.method is None
    assert payment.currency == "INR"


def test_a_memo_can_have_only_one_payment_record(db):
    """One row per real-world thing (database.md section 3)."""
    memo = make_memo(db)
    db.add(build_payment(db, deal_memo_id=memo.id))
    db.flush()

    assert_rejected_by(
        db, build_payment(db, deal_memo_id=memo.id), "uq_payment_status_deal_memo_id"
    )


# --- what the database refuses --------------------------------------------


def test_a_payment_of_nothing_is_refused(db):
    assert_rejected_by(
        db, build_payment(db, amount_paise=0), "ck_payment_status_amount_positive"
    )


def test_a_negative_payment_is_refused(db):
    assert_rejected_by(
        db, build_payment(db, amount_paise=-1), "ck_payment_status_amount_positive"
    )


def test_an_unknown_method_is_refused(db):
    assert_rejected_by(
        db,
        build_payment(db, method="bitcoin", reference=RRN, marked_paid_at=FIXED_NOW),
        "ck_payment_status_method_allowed",
    )


@pytest.mark.parametrize("method", PAYMENT_METHODS)
def test_every_agreed_method_is_accepted(db, method):
    payment = build_payment(db, method=method, reference=RRN, marked_paid_at=FIXED_NOW)
    db.add(payment)
    db.flush()

    assert payment.method == method


def test_a_claim_of_payment_must_say_how_it_was_sent(db):
    """ "I paid you", with no method and no reference, is not a record."""
    assert_rejected_by(
        db,
        build_payment(db, marked_paid_at=FIXED_NOW),
        "ck_payment_status_paid_needs_method_and_reference",
    )


def test_a_claim_of_payment_must_carry_a_reference(db):
    assert_rejected_by(
        db,
        build_payment(db, marked_paid_at=FIXED_NOW, method="upi"),
        "ck_payment_status_paid_needs_method_and_reference",
    )


def test_money_cannot_be_confirmed_that_was_never_said_to_be_sent(db):
    """The creator cannot confirm receiving a payment nobody claimed."""
    assert_rejected_by(
        db,
        build_payment(db, confirmed_at=FIXED_NOW),
        "ck_payment_status_confirmed_needs_marked_paid",
    )


def test_money_cannot_arrive_before_it_was_sent(db):
    assert_rejected_by(
        db,
        build_payment(
            db,
            method="upi",
            reference=RRN,
            marked_paid_at=FIXED_NOW,
            confirmed_at=FIXED_NOW - timedelta(hours=1),
        ),
        "ck_payment_status_confirmed_after_marked_paid",
    )


def test_a_blank_reference_is_refused(db):
    assert_rejected_by(
        db,
        build_payment(db, marked_paid_at=FIXED_NOW, method="cash", reference="   "),
        "ck_payment_status_reference_not_blank",
    )


def test_a_currency_we_do_not_handle_is_refused(db):
    assert_rejected_by(
        db, build_payment(db, currency="USD"), "ck_payment_status_currency_allowed"
    )


# --- the shape of the table -----------------------------------------------


def test_there_is_no_status_column(db):
    """Deliberate (D-027 and the model docstring).

    `late` and `unpaid` are read from the dates, so nothing has to run on a
    schedule and no row can claim a payment is on time when it is overdue.
    If a status column is ever added, that decision should be made on
    purpose, and this test is where it gets noticed.
    """
    columns = {c.name for c in Base.metadata.tables["payment_status"].columns}

    assert "status" not in columns
    assert {"due_on", "marked_paid_at", "confirmed_at"} <= columns


def test_the_overdue_query_is_indexed(db):
    """The one hot question: who has not been paid. Partial, so it skips
    every settled row (database.md section 5)."""
    indexes = Base.metadata.tables["payment_status"].indexes

    assert any(index.name == "ix_payment_status_outstanding" for index in indexes)


def test_the_record_survives_an_attempt_to_delete_its_memo(db):
    """RESTRICT: a record of money must never vanish as a side effect."""
    from sqlalchemy import text

    memo = make_memo(db)
    db.add(build_payment(db, deal_memo_id=memo.id))
    db.flush()

    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM deal_memo WHERE id = :id"), {"id": memo.id})
        db.flush()
    db.rollback()

"""Disputes: a dated record of what each side said, and never a verdict."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.disputes import service
from app.modules.disputes.exceptions import (
    DisputeAlreadyClosed,
    DisputeAlreadyOpen,
    NotADisputeParty,
    UnknownDisputeOutcome,
)
from app.modules.disputes.models import Dispute
from app.modules.payment_status import service as payments
from tests.modules.deal_memo.test_deal_memo_model import build_memo

OPENED = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
REASON = "The brand marked this paid on 8 September but nothing has reached my account."


def make_payment(db, **overrides):
    memo = build_memo(db)
    db.add(memo)
    db.flush()
    record = payments.create_for_memo(
        db, memo, approved_on=date(2026, 9, 1), now=OPENED
    )
    for key, value in overrides.items():
        setattr(record, key, value)
    db.flush()
    return record


def dispute(**overrides) -> Dispute:
    """An unsaved dispute: the state rules are pure."""
    fields = {
        "payment_status_id": uuid.uuid4(),
        "opened_by": "creator",
        "reason": REASON,
        "response_due_on": date(2026, 9, 17),
        "created_at": OPENED,
        "updated_at": OPENED,
    }
    fields.update(overrides)
    return Dispute(**fields)


# --- reading the state ----------------------------------------------------


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 10), service.OPEN),
        (date(2026, 9, 17), service.OPEN),
        (date(2026, 10, 9), service.OPEN),
        (date(2026, 10, 10), service.UNRESOLVED),
        (date(2027, 1, 1), service.UNRESOLVED),
    ],
)
def test_the_state_is_read_from_the_calendar(today, expected):
    assert service.derive_state(dispute(), today) == expected


def test_unresolved_is_a_fact_not_a_verdict():
    """Thirty days passed and nothing was agreed. That is all anybody here
    knows, and all the record says."""
    timed_out = service.derive_state(dispute(), date(2026, 10, 20))

    assert timed_out == service.UNRESOLVED
    assert timed_out not in {"brand_at_fault", "creator_at_fault"}


@pytest.mark.parametrize("outcome", ["resolved_paid", "resolved_withdrawn", "resolved_informally"])
def test_an_agreed_outcome_outranks_the_clock(outcome):
    settled = dispute(outcome=outcome, closed_at=OPENED)

    assert service.derive_state(settled, date(2027, 1, 1)) == outcome


def test_the_response_window_is_seven_days():
    assert service.response_deadline_for(date(2026, 9, 10)) == date(2026, 9, 17)


def test_the_clock_starts_on_the_indian_calendar():
    """Raised at 23:00 UTC is already tomorrow for the person answering."""
    late_evening = dispute(created_at=datetime(2026, 9, 10, 23, 0, tzinfo=UTC))

    assert service.unresolved_on(late_evening) == date(2026, 10, 11)


def test_every_state_it_returns_is_a_named_one():
    for today in (date(2026, 9, 10), date(2026, 10, 20)):
        assert service.derive_state(dispute(), today) in service.DISPUTE_STATES


# --- what an open dispute does to a payment -------------------------------


def test_an_open_dispute_holds_a_payment_short_of_unpaid(db):
    """Being argued about is not the same as nobody discussing it. Marking a
    brand a non-payer while the matter is live would be taking a side."""
    payment = make_payment(db)
    service.open_for_payment(db, payment.id, opened_by="creator", reason=REASON, now=OPENED)
    db.commit()

    long_after = date(2026, 11, 1)
    without = payments.derive_state(payment, long_after)
    with_dispute = payments.derive_state(payment, long_after, has_open_dispute=True)

    assert without == payments.UNPAID
    assert with_dispute == payments.LATE


def test_a_timed_out_dispute_stops_holding_the_payment(db):
    """After thirty days of silence it is no longer live, and the payment is
    free to be recorded as what it is."""
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    assert service.is_open(raised, date(2026, 9, 20)) is True
    assert service.is_open(raised, date(2026, 11, 1)) is False


def test_open_payment_ids_finds_live_disputes_in_one_query(db):
    argued = make_payment(db)
    quiet = make_payment(db)
    service.open_for_payment(db, argued.id, opened_by="creator", reason=REASON, now=OPENED)
    db.commit()

    found = service.open_payment_ids(db, {argued.id, quiet.id}, date(2026, 9, 20))

    assert found == {argued.id}


def test_a_closed_dispute_is_not_counted_as_live(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()
    service.close(db, raised, outcome="resolved_paid", actor_role="brand", now=OPENED)

    found = service.open_payment_ids(db, {payment.id}, date(2026, 9, 20))

    assert found == set()


# --- raising one ----------------------------------------------------------


def test_either_side_may_raise_one(db):
    for role in ("brand", "creator"):
        payment = make_payment(db)
        raised = service.open_for_payment(
            db, payment.id, opened_by=role, reason=REASON, now=OPENED
        )
        db.commit()
        assert raised.opened_by == role


def test_the_reason_becomes_the_first_entry_on_the_timeline(db):
    """So the record reads as one story rather than starting halfway."""
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    entries = service.timeline(db, raised)

    assert len(entries) == 1
    assert entries[0].kind == "opened"
    assert entries[0].note == REASON
    assert entries[0].actor_role == "creator"


def test_a_payment_can_only_be_disputed_once(db):
    payment = make_payment(db)
    service.open_for_payment(db, payment.id, opened_by="creator", reason=REASON, now=OPENED)
    db.commit()

    with pytest.raises(DisputeAlreadyOpen):
        service.open_for_payment(
            db, payment.id, opened_by="brand", reason=REASON, now=OPENED
        )


def test_an_outsider_is_not_a_party(db):
    payment = make_payment(db)

    with pytest.raises(NotADisputeParty):
        service.open_for_payment(
            db, payment.id, opened_by="admin", reason=REASON, now=OPENED
        )


# --- the timeline ---------------------------------------------------------


def test_both_sides_can_put_their_account_on_the_record(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    service.add_entry(
        db, raised, actor_role="brand", note="Sent by UPI, here is the screenshot.",
        evidence_url="https://example.com/proof.png", now=OPENED + timedelta(days=1),
        kind="response",
    )

    entries = service.timeline(db, raised)
    assert [entry.actor_role for entry in entries] == ["creator", "brand"]
    assert entries[1].evidence_url == "https://example.com/proof.png"


def test_the_timeline_is_in_the_order_things_were_said(db):
    """Often the only thing two people afterwards can agree on."""
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()
    for day in (3, 1, 2):
        service.add_entry(
            db, raised, actor_role="creator", note=f"Entry from day {day}",
            now=OPENED + timedelta(days=day),
        )

    entries = service.timeline(db, raised)

    assert [entry.created_at for entry in entries] == sorted(
        entry.created_at for entry in entries
    )


def test_a_late_account_is_still_accepted(db):
    """A late account is still an account. Refusing it would make the record
    less true, not more orderly."""
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    entry = service.add_entry(
        db, raised, actor_role="brand", note="Sorry, only just saw this.",
        now=OPENED + timedelta(days=60),
    )

    assert entry.id is not None


def test_nothing_is_added_after_it_is_settled(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()
    service.close(db, raised, outcome="resolved_paid", actor_role="brand", now=OPENED)

    with pytest.raises(DisputeAlreadyClosed):
        service.add_entry(db, raised, actor_role="creator", note="One more thing", now=OPENED)


# --- closing it -----------------------------------------------------------


def test_settling_it_by_phone_is_a_real_outcome(db):
    """Most of these end with a phone call. Forcing a thirty-day wait for
    something already settled would be worse than no dispute system."""
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    service.close(
        db, raised, outcome="resolved_informally", actor_role="creator", now=OPENED
    )

    assert service.derive_state(raised, date(2026, 12, 1)) == "resolved_informally"


def test_closing_it_lands_on_the_timeline(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    # A day later: two entries at the very same instant are genuinely
    # simultaneous, and the timeline would have no honest order to give.
    service.close(
        db, raised, outcome="resolved_paid", actor_role="brand",
        now=OPENED + timedelta(days=1),
    )

    assert service.timeline(db, raised)[-1].kind == "closed"


def test_it_cannot_be_closed_twice(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()
    service.close(db, raised, outcome="resolved_paid", actor_role="brand", now=OPENED)

    with pytest.raises(DisputeAlreadyClosed):
        service.close(
            db, raised, outcome="resolved_withdrawn", actor_role="creator", now=OPENED
        )


def test_an_outcome_we_do_not_record_is_refused(db):
    payment = make_payment(db)
    raised = service.open_for_payment(
        db, payment.id, opened_by="creator", reason=REASON, now=OPENED
    )
    db.commit()

    with pytest.raises(UnknownDisputeOutcome):
        service.close(
            db, raised, outcome="creator_was_lying", actor_role="brand", now=OPENED
        )


def test_there_is_no_outcome_that_blames_anybody():
    """D-028: we record, we do not judge. If an outcome ever names a guilty
    party, that decision was made somewhere it should not have been."""
    from app.modules.disputes.models import DISPUTE_OUTCOMES

    for outcome in DISPUTE_OUTCOMES:
        assert outcome.startswith("resolved_")
        assert "fault" not in outcome
        assert "guilty" not in outcome

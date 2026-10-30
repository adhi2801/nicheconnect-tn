"""Proof approved by the clock never overwrites an answer that landed meanwhile (D-025).

Found by the second review of item 27 (D-140, consequence 8): approval by the clock
wrote on the proof as it had been read, without a lock. A brand asking for a revision
at the moment the window closed could leave the proof both sent back and approved,
with a payment opened for work that was sent back. It now locks the proof and reads
it again, as an answer does, and approves only a deal still agreed at the deadline.

Real, committed connections, like the other concurrency tests; every write is held
open (`slow_writes`) so the race happens on every run.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.deal_memo import proof_service, record_service
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.exceptions import ProofAlreadyDecided
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.review_clock import approval_deadline
from app.modules.payment_status.models import PaymentStatus
from tests.modules.conftest import CONCURRENCY_NOW as NOW
from tests.modules.payment_status.test_payment_concurrency import run_at_once, split

LINK = "https://www.instagram.com/reel/clock/"


@pytest.fixture
def waiting_proof(committed_memo) -> Iterator[uuid.UUID]:
    """A proof submitted and waiting for the brand, on a committed deal."""
    with SessionLocal() as session:
        proof = proof_service.submit_proof(
            session,
            session.get_one(DealMemo, committed_memo),
            {"content_url": LINK, "format": "reel"},
            NOW,
        )
        proof_id = proof.id
    try:
        yield proof_id
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(PaymentStatus).where(PaymentStatus.deal_memo_id == committed_memo)
            )
            session.commit()


def deadline_of(memo_id, proof_id):
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, memo_id)
        proof = session.get_one(DeliverableProof, proof_id)
        history = list(
            session.scalars(
                select(DeliverableProof).where(DeliverableProof.deal_memo_id == memo_id)
            )
        )
        return approval_deadline(memo, proof, history)


def outcome(memo_id, proof_id):
    """The proof's status, whether a payment is open, and the record's proof entries."""
    with SessionLocal() as session:
        status = session.get_one(DeliverableProof, proof_id).status
        paid = session.scalars(
            select(PaymentStatus).where(PaymentStatus.deal_memo_id == memo_id)
        ).first()
        memo = session.get_one(DealMemo, memo_id)
        kinds = [e.kind for e in record_service.entries_for(session, memo.id)]
        assert record_service.verify(
            memo, record_service.entries_for(session, memo.id)
        ).intact
    return status, paid is not None, kinds


def test_a_stale_copy_never_approves_proof_that_was_sent_back(
    committed_memo, waiting_proof
):
    """Read before the brand's answer, settled after it: the answer stands."""
    deadline = deadline_of(committed_memo, waiting_proof)
    reader = SessionLocal()
    try:
        stale = reader.get_one(DeliverableProof, waiting_proof)
        memo_seen = reader.get_one(DealMemo, committed_memo)
        assert stale.status == "submitted"
        with SessionLocal() as brand:
            proof_service.request_revision(
                brand,
                brand.get_one(DealMemo, committed_memo),
                brand.get_one(DeliverableProof, waiting_proof),
                "Add the ad label.",
                deadline - timedelta(minutes=5),
            )
        proof_service.settle_if_overdue(
            reader, memo_seen, stale, deadline + timedelta(seconds=1), history=[stale]
        )
    finally:
        reader.rollback()
        reader.close()

    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert status == "revision_requested"
    assert not payment_open
    assert "proof_auto_approved" not in kinds


def test_the_clock_and_a_revision_at_the_deadline_leave_one_answer(
    committed_memo, waiting_proof, slow_writes
):
    """The brand asks at 23:59:59; a reader settles at 00:00:01. One lands, never both."""
    deadline = deadline_of(committed_memo, waiting_proof)

    def ask(session):
        return proof_service.request_revision(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            "Add the ad label.",
            deadline - timedelta(seconds=1),
        )

    def settle(session):
        return proof_service.settle_if_overdue(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            deadline + timedelta(seconds=1),
        )

    moves = [ask, settle, ask, settle]
    results = run_at_once(lambda s: moves.pop()(s), 4)

    _, _, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    answered = kinds.count("proof_revision_requested") + kinds.count(
        "proof_auto_approved"
    )
    assert answered == 1, kinds
    # the payment clock runs exactly when the proof was approved
    assert (status == "approved") == payment_open


def test_a_deal_cancelled_before_the_deadline_is_never_approved_by_the_clock(
    committed_memo, waiting_proof
):
    deadline = deadline_of(committed_memo, waiting_proof)
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, committed_memo),
            "cancelled",
            deadline - timedelta(hours=1),
            actor="brand",
        )
        session.commit()
    with SessionLocal() as session:
        proof_service.settle_if_overdue(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            deadline + timedelta(days=1),
        )
        session.commit()

    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert status == "submitted"
    assert not payment_open
    assert "proof_auto_approved" not in kinds


def test_a_deal_cancelled_after_the_deadline_was_still_approved_at_it(
    committed_memo, waiting_proof
):
    """The window closed while the deal was agreed; the later cancellation changes nothing."""
    deadline = deadline_of(committed_memo, waiting_proof)
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, committed_memo),
            "cancelled",
            deadline + timedelta(hours=1),
            actor="brand",
        )
        session.commit()
    with SessionLocal() as session:
        proof_service.settle_if_overdue(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            deadline + timedelta(days=1),
        )

    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert status == "approved"
    assert payment_open
    assert "proof_auto_approved" in kinds


def test_a_cancellation_after_the_deal_was_read_still_stops_the_clock(
    committed_memo, waiting_proof
):
    """Read while the deal was agreed, cancelled before the deadline, settled after it."""
    deadline = deadline_of(committed_memo, waiting_proof)
    reader = SessionLocal()
    try:
        memo_seen = reader.get_one(DealMemo, committed_memo)
        proof_seen = reader.get_one(DeliverableProof, waiting_proof)
        assert memo_seen.status == "accepted"
        with SessionLocal() as brand:
            memos.change_status(
                brand,
                brand.get_one(DealMemo, committed_memo),
                "cancelled",
                deadline - timedelta(hours=1),
                actor="brand",
            )
            brand.commit()
        proof_service.settle_if_overdue(
            reader,
            memo_seen,
            proof_seen,
            deadline + timedelta(seconds=1),
            history=[proof_seen],
        )
        reader.commit()
    finally:
        reader.close()

    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert status == "submitted"
    assert not payment_open
    assert "proof_auto_approved" not in kinds


# --- after the independent review (29 October 2026) -------------------------------------


def test_the_clock_and_an_approval_at_the_deadline_leave_one_approval(
    committed_memo, waiting_proof, slow_writes
):
    deadline = deadline_of(committed_memo, waiting_proof)

    def approve(session):
        return proof_service.approve_proof(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            deadline - timedelta(seconds=1),
        )

    def settle(session):
        return proof_service.settle_if_overdue(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            deadline + timedelta(seconds=1),
        )

    moves = [approve, settle, approve, settle]
    results = run_at_once(lambda s: moves.pop()(s), 4)

    _, _, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert kinds.count("proof_approved") + kinds.count("proof_auto_approved") == 1, kinds
    assert (status, payment_open) == ("approved", True)
    with SessionLocal() as session:
        payments = session.scalars(
            select(PaymentStatus).where(PaymentStatus.deal_memo_id == committed_memo)
        ).all()
    assert len(payments) == 1


def test_a_move_that_locks_the_deal_first_never_deadlocks_with_the_clock(
    committed_memo, waiting_proof, slow_writes
):
    """Giving feedback locks the deal, then reads its proof, which may settle it; a reader
    settles at the same moment. One order for both (the deal, then the proof)."""
    deadline = deadline_of(committed_memo, waiting_proof)
    at = deadline + timedelta(seconds=1)

    def deal_first(session):
        memo = session.get_one(DealMemo, committed_memo)
        session.refresh(memo, attribute_names=["status"], with_for_update=True)
        return proof_service.settle_if_overdue(
            session, memo, session.get_one(DeliverableProof, waiting_proof), at
        )

    def reader(session):
        return proof_service.settle_if_overdue(
            session,
            session.get_one(DealMemo, committed_memo),
            session.get_one(DeliverableProof, waiting_proof),
            at,
        )

    moves = [deal_first, reader, deal_first, reader]
    results = run_at_once(lambda s: moves.pop()(s), 4)

    _, _, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    status, payment_open, kinds = outcome(committed_memo, waiting_proof)
    assert kinds.count("proof_auto_approved") == 1, kinds
    assert (status, payment_open) == ("approved", True)


@pytest.mark.parametrize("answer", ["approve", "revise"])
def test_proof_on_a_cancelled_deal_is_never_answered(
    committed_memo, waiting_proof, answer
):
    from app.modules.deal_memo.exceptions import MemoStatusConflict

    deadline = deadline_of(committed_memo, waiting_proof)
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, committed_memo),
            "cancelled",
            deadline - timedelta(hours=1),
            actor="brand",
        )
        session.commit()
    with SessionLocal() as session, pytest.raises(MemoStatusConflict):
        memo = session.get_one(DealMemo, committed_memo)
        proof = session.get_one(DeliverableProof, waiting_proof)
        if answer == "approve":
            proof_service.approve_proof(
                session, memo, proof, deadline - timedelta(minutes=30)
            )
        else:
            proof_service.request_revision(
                session,
                memo,
                proof,
                "Add the ad label.",
                deadline - timedelta(minutes=30),
            )

    status, payment_open, _ = outcome(committed_memo, waiting_proof)
    assert (status, payment_open) == ("submitted", False)


def test_the_delivery_record_agrees_a_deal_cancelled_before_the_deadline_was_not_approved(
    committed_memo, waiting_proof
):
    from app.modules.deal_memo import delivery_record

    deadline = deadline_of(committed_memo, waiting_proof)
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, committed_memo),
            "cancelled",
            deadline - timedelta(hours=1),
            actor="brand",
        )
        session.commit()
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, committed_memo)
        proof = session.get_one(DeliverableProof, waiting_proof)
        assert not delivery_record.is_approved(
            memo, proof, [proof], deadline + timedelta(days=1)
        )


def test_a_refused_clock_takes_no_lock(committed_memo, waiting_proof):
    """A proof on a deal cancelled before its deadline is read often; it must not be locked."""
    from sqlalchemy import text

    deadline = deadline_of(committed_memo, waiting_proof)
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, committed_memo),
            "cancelled",
            deadline - timedelta(hours=1),
            actor="brand",
        )
        session.commit()
    reader = SessionLocal()
    try:
        proof_service.settle_if_overdue(
            reader,
            reader.get_one(DealMemo, committed_memo),
            reader.get_one(DeliverableProof, waiting_proof),
            deadline + timedelta(days=1),
        )
        # still inside the reader's transaction: another may lock both rows at once
        with SessionLocal() as other:
            other.execute(
                text("SELECT id FROM deal_memo WHERE id = :m FOR UPDATE NOWAIT"),
                {"m": committed_memo},
            )
            other.execute(
                text("SELECT id FROM deliverable_proof WHERE id = :p FOR UPDATE NOWAIT"),
                {"p": waiting_proof},
            )
            other.rollback()
    finally:
        reader.rollback()
        reader.close()

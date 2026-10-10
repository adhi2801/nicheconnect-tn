"""Two conflicting moves at once on one thing: exactly one wins.

Found by an audit after the review findings of 4 October: every status
change checked "may this move happen from here?" on a row read without a
lock, then wrote. Two conflicting moves at once both passed the check, and
the last write silently won. The worst case was money: a brand approving
proof while also asking for changes could leave the payment clock running
on proof that had been sent back.

Real, committed connections, like the other concurrency tests. The moment
before each write reaches the database is held open, so the race happens
every run rather than by luck.
"""

import uuid
from collections.abc import Callable, Iterator
from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import (
    ApplicationStatusConflict,
    CampaignStatusConflict,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import proof_service
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.exceptions import MemoStatusConflict, ProofAlreadyDecided
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.payment_status.models import PaymentStatus
from tests.modules.conftest import CONCURRENCY_NOW as NOW
from tests.modules.payment_status.test_payment_concurrency import run_at_once, split

LINK = "https://www.instagram.com/reel/concurrency/"


def one_each(*moves: Callable[[Session], object]) -> Callable[[Session], object]:
    """A work function that hands each thread the next move in turn."""
    queue = list(moves)
    return lambda session: queue.pop()(session)


# --- proof: approve, or ask for changes ------------------------------------------------


@pytest.fixture
def submitted_proof(committed_memo) -> Iterator[uuid.UUID]:
    with SessionLocal() as session:
        proof = proof_service.submit_proof(
            session,
            session.get(DealMemo, committed_memo),
            {"content_url": LINK, "format": "reel"},
            NOW,
        )
        proof_id = proof.id
    try:
        yield proof_id
    finally:
        with SessionLocal() as session:
            # Approval opens a payment record; it goes before the memo does.
            session.execute(
                delete(PaymentStatus).where(PaymentStatus.deal_memo_id == committed_memo)
            )
            session.commit()


def test_approving_and_asking_for_changes_at_once_leaves_one_consistent_answer(
    committed_memo, submitted_proof, slow_writes
):
    def approve(s: Session) -> object:
        memo = s.get(DealMemo, committed_memo)
        return proof_service.approve_proof(
            s, memo, s.get(DeliverableProof, submitted_proof), NOW
        )

    def revise(s: Session) -> object:
        memo = s.get(DealMemo, committed_memo)
        return proof_service.request_revision(
            s, memo, s.get(DeliverableProof, submitted_proof), "Add the ad label.", NOW
        )

    results = run_at_once(one_each(approve, revise, approve, revise), 4)

    won, refused, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, 3)
    with SessionLocal() as session:
        status = session.get(DeliverableProof, submitted_proof).status
        payment = session.scalars(
            select(PaymentStatus).where(PaymentStatus.deal_memo_id == committed_memo)
        ).first()
    # The payment clock runs exactly when the proof was approved.
    assert (status == "approved") == (payment is not None)


# --- a memo: accepted, declined or cancelled -------------------------------------------


@pytest.fixture
def sent_memo(committed_application) -> uuid.UUID:
    with SessionLocal() as session:
        memo = DealMemo(
            application_id=committed_application,
            deliverables="Three reels, for a concurrency test.",
            fee_amount_paise=800_000,
            status="sent",
            sent_at=NOW,
            content_due_on=date(2026, 12, 31),
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        return memo.id


def test_accepting_and_declining_a_memo_at_once_gives_one_outcome(sent_memo, slow_writes):
    """Exclusive moves: once a memo is accepted it cannot be declined, and the
    reverse. (Accept, then cancel, is a legal history, so it is not the test.)"""

    def accept(s: Session) -> object:
        return memos.change_status(
            s, s.get(DealMemo, sent_memo), "accepted", NOW, actor="creator"
        )

    def decline(s: Session) -> object:
        return memos.change_status(
            s, s.get(DealMemo, sent_memo), "declined", NOW, actor="creator"
        )

    results = run_at_once(one_each(accept, decline, accept, decline), 4)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, 3)
    with SessionLocal() as session:
        memo = session.get(DealMemo, sent_memo)
    # One story: accepted with its date, or declined without one.
    assert (memo.status == "accepted") == (memo.accepted_at is not None)


# --- an application: accepted, rejected or withdrawn -------------------------------------


@pytest.fixture
def shortlisted(committed_application) -> uuid.UUID:
    with SessionLocal() as session:
        row = session.get(Application, committed_application)
        row.status = "shortlisted"
        session.commit()
    return committed_application


def test_accepting_and_rejecting_an_application_at_once_gives_one_outcome(
    shortlisted, slow_writes
):
    def accept(s: Session) -> object:
        return campaigns.change_application_status(
            s, s.get(Application, shortlisted), "accepted", NOW, actor="brand"
        )

    def reject(s: Session) -> object:
        return campaigns.change_application_status(
            s,
            s.get(Application, shortlisted),
            "rejected",
            NOW,
            actor="brand",
            rejection_reason="chose_another_creator",
        )

    results = run_at_once(one_each(accept, reject, accept, reject), 4)

    won, refused, unexpected = split(results, ApplicationStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, 3)


# --- a campaign: closed or cancelled --------------------------------------------------


def test_closing_and_cancelling_a_campaign_at_once_gives_one_outcome(
    committed_application, slow_writes
):
    with SessionLocal() as session:
        campaign_id = session.get(Application, committed_application).campaign_id

    def close(s: Session) -> object:
        return campaigns.change_status(s, s.get(Campaign, campaign_id), "closed", NOW)

    def cancel(s: Session) -> object:
        return campaigns.change_status(s, s.get(Campaign, campaign_id), "cancelled", NOW)

    results = run_at_once(one_each(close, cancel, close, cancel), 4)

    won, refused, unexpected = split(results, CampaignStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, 3)


# --- a deal's unfinished uploads: the cap of 20 ------------------------------------------


def test_the_upload_cap_holds_against_simultaneous_requests(committed_memo, slow_writes):
    import hashlib

    from app.core import storage
    from app.modules.auth.models.creator import Creator
    from app.modules.deal_memo import proof_file_service
    from app.modules.deal_memo.exceptions import TooManyPendingUploads
    from app.modules.deal_memo.proof_models import ProofFile

    data = b"a screenshot"
    with SessionLocal() as session:
        memo = session.get(DealMemo, committed_memo)
        creator_account = session.scalars(
            select(Creator.account_id)
            .join(Application, Application.creator_id == Creator.id)
            .where(Application.id == memo.application_id)
        ).one()
        for _ in range(proof_file_service.MAX_PENDING_UPLOADS_PER_MEMO - 1):
            session.add(
                ProofFile(
                    deal_memo_id=committed_memo,
                    uploader_account_id=creator_account,
                    storage_key=f"proof-files/incoming/cap-{uuid.uuid4().hex}",
                    content_type="image/png",
                    size_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        session.commit()

    try:
        results = run_at_once(
            lambda s: proof_file_service.request_upload(
                s,
                storage.memory_store(),
                s.get(DealMemo, committed_memo),
                creator_account,
                content_type="image/png",
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                now=NOW,
            ),
            4,
        )

        won, refused, unexpected = split(results, TooManyPendingUploads)
        assert unexpected == [], f"a raw error reached the caller: {unexpected}"
        assert (won, refused) == (1, 3)
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(ProofFile).where(ProofFile.deal_memo_id == committed_memo)
            )
            session.commit()
        storage.memory_store().clear()

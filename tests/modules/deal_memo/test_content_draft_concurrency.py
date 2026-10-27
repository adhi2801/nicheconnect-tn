"""Drafts shown and answered at the same moment (item 27, D-140).

Real, committed connections released together, every write held open
(`slow_writes`). Showing a draft locks the memo first and an answer locks
the draft first, so four drafts at once keep one, and an approval racing a
request for changes leaves exactly one answer, each sealed in one chain.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.deal_memo import draft_service, record_service
from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.exceptions import DraftAlreadyDecided
from app.modules.deal_memo.models import DealMemo
from tests.modules.conftest import CONCURRENCY_NOW as NOW


def run_together(works: list[Callable[[Any], Any]]) -> list[Any]:
    barrier = threading.Barrier(len(works))
    results: list[Any] = [None] * len(works)

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = works[index](session)
            except Exception as exc:  # collected and asserted by the test
                session.rollback()
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(works))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.fixture
def reviewed_deal(committed_application) -> Iterator[Any]:
    """The committed application's deal, agreed with a draft review."""
    with SessionLocal() as session:
        memo = DealMemo(
            application_id=committed_application,
            deliverables="One reel, for a concurrency test.",
            fee_amount_paise=500_000,
            draft_review=True,
            status="accepted",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        memo_id = memo.id
    yield memo_id


def show(memo_id) -> Callable[[Any], Any]:
    def work(session):
        memo = session.get_one(DealMemo, memo_id)
        return draft_service.submit_draft(session, memo, {"body": "The caption."}, NOW)

    return work


def drafts(memo_id) -> list[ContentDraft]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(ContentDraft).where(ContentDraft.deal_memo_id == memo_id)
            )
        )


def test_four_drafts_at_once_keep_one(reviewed_deal, slow_writes):
    results = run_together([show(reviewed_deal)] * 4)

    assert sum(isinstance(r, ContentDraft) for r in results) == 1, results
    assert all(isinstance(r, ContentDraft | DraftAlreadyDecided) for r in results), (
        results
    )
    assert len(drafts(reviewed_deal)) == 1


def test_an_approval_racing_a_request_for_changes_leaves_one_answer(
    reviewed_deal, slow_writes
):
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, reviewed_deal)
        draft_id = draft_service.submit_draft(
            session, memo, {"body": "The caption."}, NOW
        ).id

    def approve(session):
        memo = session.get_one(DealMemo, reviewed_deal)
        return draft_service.approve_draft(
            session, memo, session.get_one(ContentDraft, draft_id), NOW
        )

    def ask(session):
        memo = session.get_one(DealMemo, reviewed_deal)
        draft = session.get_one(ContentDraft, draft_id)
        return draft_service.request_changes(
            session, memo, draft, "Add the ad label.", NOW
        )

    results = run_together([approve, ask, approve, ask])

    assert sum(isinstance(r, ContentDraft) for r in results) == 1, results
    assert all(isinstance(r, ContentDraft | DraftAlreadyDecided) for r in results), (
        results
    )
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, reviewed_deal)
        entries = record_service.entries_for(session, memo.id)
        assert record_service.verify(memo, entries).intact
        answers = [
            e.kind
            for e in entries
            if e.kind in ("draft_approved", "draft_changes_requested")
        ]
        assert len(answers) == 1


def test_a_proof_and_a_request_for_changes_at_the_deadline_never_both_land(
    reviewed_deal, slow_writes
):
    """Found by the independent review: the brand asks at 23:59:59, the proof comes at 00:00:01.

    Each takes the memo's lock first, so one lands and the other sees it: a
    proof never names a draft the brand sent back.
    """
    from datetime import timedelta

    from app.modules.deal_memo import proof_service
    from app.modules.deal_memo.draft_rules import answer_deadline
    from app.modules.deal_memo.exceptions import DraftNotApproved
    from app.modules.deal_memo.proof_models import DeliverableProof

    with SessionLocal() as session:
        memo = session.get_one(DealMemo, reviewed_deal)
        draft = draft_service.submit_draft(session, memo, {"body": "The caption."}, NOW)
        deadline = answer_deadline(memo, draft, [draft])
        draft_id = draft.id

    def ask(session):
        memo = session.get_one(DealMemo, reviewed_deal)
        draft = session.get_one(ContentDraft, draft_id)
        return draft_service.request_changes(
            session, memo, draft, "Add the ad label.", deadline - timedelta(seconds=1)
        )

    def prove(session):
        memo = session.get_one(DealMemo, reviewed_deal)
        fields = {
            "content_url": "https://www.instagram.com/reel/abc123/",
            "format": "reel",
            "disclosure_confirmed": True,
        }
        return proof_service.submit_proof(
            session, memo, fields, deadline + timedelta(seconds=1)
        )

    results = run_together([ask, prove])

    assert all(
        isinstance(
            r, ContentDraft | DeliverableProof | DraftAlreadyDecided | DraftNotApproved
        )
        for r in results
    ), results
    with SessionLocal() as session:
        proofs = session.scalars(
            select(DeliverableProof).where(DeliverableProof.deal_memo_id == reviewed_deal)
        ).all()
        status = session.get_one(ContentDraft, draft_id).status
        for proof in proofs:
            session.delete(proof)
        session.commit()
    assert not (proofs and status == "changes_requested"), (len(proofs), status)


def _stale_then(reviewed_deal, act):
    """Load the draft in one session, let `act` change it in another, then settle the stale copy."""
    from datetime import timedelta

    from app.modules.deal_memo.draft_rules import answer_deadline

    with SessionLocal() as session:
        memo = session.get_one(DealMemo, reviewed_deal)
        draft = draft_service.submit_draft(session, memo, {"body": "The caption."}, NOW)
        deadline = answer_deadline(memo, draft, [draft])
        draft_id = draft.id

    with SessionLocal() as stale:
        memo = stale.get_one(DealMemo, reviewed_deal)
        draft = stale.get_one(ContentDraft, draft_id)
        assert draft.status == "submitted"  # read before the other side acted
        with SessionLocal() as other:
            act(other, draft_id, deadline - timedelta(seconds=1))
        draft_service.settle_if_overdue(
            stale, memo, draft, deadline + timedelta(seconds=1), history=[draft]
        )
    with SessionLocal() as session:
        kinds = [e.kind for e in record_service.entries_for(session, reviewed_deal)]
        return session.get_one(ContentDraft, draft_id).status, kinds


def test_the_clock_never_overwrites_an_answer_given_meanwhile(reviewed_deal):
    """Found by the second independent review: settling read the draft without a lock."""

    def ask(session, draft_id, at):
        memo = session.get_one(DealMemo, reviewed_deal)
        draft_service.request_changes(
            session,
            memo,
            session.get_one(ContentDraft, draft_id),
            "Add the ad label.",
            at,
        )

    status, kinds = _stale_then(reviewed_deal, ask)

    assert status == "changes_requested"
    assert "draft_auto_approved" not in kinds


def test_the_clock_never_approves_a_draft_on_a_deal_cancelled_meanwhile(reviewed_deal):
    def cancel(session, draft_id, at):
        memo = session.get_one(DealMemo, reviewed_deal)
        memo.status = "cancelled"
        memo.cancellation_kind = "cancelled_by_brand"
        memo.cancelled_at = at
        session.commit()

    status, kinds = _stale_then(reviewed_deal, cancel)

    assert status == "submitted"
    assert "draft_auto_approved" not in kinds

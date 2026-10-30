"""Feedback given at the same moment (item 77, D-136).

Real, committed connections released together, every write held open
(`slow_writes`). Each answer seals an entry onto the deal record under the
deal's lock, so both sides answering at once both land in one unbroken
chain, and one side answering twice at once keeps exactly one answer.
"""

import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select, update

from app.db.session import SessionLocal
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import feedback_service, record_service
from app.modules.deal_memo.exceptions import FeedbackClosed
from app.modules.deal_memo.feedback_models import DealFeedback
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from tests.modules.conftest import CONCURRENCY_NOW as NOW

GOOD = {"brief": 5, "reliability": 4, "easy": 5}


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
def finished_barter(committed_application) -> Iterator[Any]:
    """The committed application's deal, made barter, agreed and its work approved."""
    with SessionLocal() as session:
        campaign_id = session.scalars(
            select(Application.campaign_id).where(Application.id == committed_application)
        ).one()
        session.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(campaign_type="barter", budget_min_paise=None, budget_max_paise=None)
        )
        memo = DealMemo(
            application_id=committed_application,
            deliverables="One reel, for a concurrency test.",
            status="accepted",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.flush()
        session.add(
            DeliverableProof(
                deal_memo_id=memo.id,
                content_url="https://www.instagram.com/reel/abc123/",
                format="reel",
                disclosure_confirmed=True,
                status="approved",
                approved_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.commit()
        memo_id = memo.id
    yield memo_id
    with SessionLocal() as session:
        session.execute(
            delete(DeliverableProof).where(DeliverableProof.deal_memo_id == memo_id)
        )
        session.commit()


@pytest.fixture
def barter_waiting_on_the_clock(finished_barter) -> Any:
    """The same deal, but its proof still waits and its 7-day window has just
    closed: the first read approves it by the clock, and that commits."""
    with SessionLocal() as session:
        session.execute(
            update(DeliverableProof)
            .where(DeliverableProof.deal_memo_id == finished_barter)
            .values(
                status="submitted",
                approved_at=None,
                created_at=NOW - timedelta(days=9),
            )
        )
        session.commit()
    return finished_barter


def answer(memo_id, side: str) -> Callable[[Any], Any]:
    def work(session):
        memo = session.get_one(DealMemo, memo_id)
        return feedback_service.give(session, memo, side, GOOD, f"From the {side}.", NOW)

    return work


def test_both_sides_at_once_both_land_in_one_chain(finished_barter, slow_writes):
    results = run_together(
        [answer(finished_barter, "brand"), answer(finished_barter, "creator")]
    )

    assert all(isinstance(r, DealFeedback) for r in results), results
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, finished_barter)
        entries = record_service.entries_for(session, memo.id)
        assert record_service.verify(memo, entries).intact
        assert sum(e.kind == "feedback_given" for e in entries) == 2


def test_one_side_twice_at_once_keeps_one_answer(finished_barter, slow_writes):
    results = run_together([answer(finished_barter, "brand")] * 4)

    assert sum(isinstance(r, DealFeedback) for r in results) == 1, results
    assert all(isinstance(r, DealFeedback | FeedbackClosed) for r in results), results
    with SessionLocal() as session:
        kept = session.scalars(
            select(DealFeedback).where(DealFeedback.deal_memo_id == finished_barter)
        ).all()
    assert len(kept) == 1


def test_one_side_twice_as_the_clock_approves_keeps_one_answer(
    barter_waiting_on_the_clock, slow_writes
):
    """The clock's approval commits mid-answer; the lock is taken again after it,
    so the second answer is refused, never a unique-key error (a 500)."""
    results = run_together([answer(barter_waiting_on_the_clock, "brand")] * 3)

    assert sum(isinstance(r, DealFeedback) for r in results) == 1, results
    assert all(isinstance(r, DealFeedback | FeedbackClosed) for r in results), results
    with SessionLocal() as session:
        kept = session.scalars(
            select(DealFeedback).where(
                DealFeedback.deal_memo_id == barter_waiting_on_the_clock
            )
        ).all()
        proof = session.scalars(
            select(DeliverableProof).where(
                DeliverableProof.deal_memo_id == barter_waiting_on_the_clock
            )
        ).one()
    assert len(kept) == 1
    assert (proof.status, proof.auto_approved) == ("approved", True)

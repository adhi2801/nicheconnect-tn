"""A barter shipment's steps at the same moment (item 68, D-131).

Real, committed connections released together, every write held open
(`slow_writes`). Shipping and receiving each take the deal's lock first,
so "it arrived" is said once however many taps arrive together, and a
correction racing the creator's "it arrived" either lands before it or is
refused: never a number changed after the goods were received.
"""

import threading
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service, shipment_service
from app.modules.deal_memo.exceptions import ShipmentAlreadyReceived
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.shipment_models import BarterShipment
from tests.modules.conftest import CONCURRENCY_NOW as NOW

AT_ONCE = 4


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
def barter_memo(committed_application) -> uuid.UUID:
    """The committed application's deal, made barter and agreed, its goods shipped."""
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
            deliverables="Two reels, for a concurrency test.",
            status="accepted",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        shipment_service.ship(
            session, memo, carrier="delhivery", tracking_number="123456789012", now=NOW
        )
        return memo.id


def entries(memo_id: uuid.UUID) -> list[DealRecordEntry]:
    with SessionLocal() as session:
        return record_service.entries_for(session, memo_id)


def test_it_arrived_said_at_once_is_said_once(barter_memo, slow_writes):
    def receive(session):
        return shipment_service.receive(
            session, session.get_one(DealMemo, barter_memo), NOW
        )

    results = run_together([receive] * AT_ONCE)

    assert sum(isinstance(r, BarterShipment) for r in results) == 1, results
    assert all(
        isinstance(r, BarterShipment | ShipmentAlreadyReceived) for r in results
    ), results
    kinds = [e.kind for e in entries(barter_memo)]
    assert kinds.count("product_received") == 1


def test_a_correction_racing_it_arrived_never_lands_after_it(barter_memo, slow_writes):
    def correct(session):
        return shipment_service.ship(
            session,
            session.get_one(DealMemo, barter_memo),
            carrier="delhivery",
            tracking_number="999999999999",
            now=NOW,
        )

    def receive(session):
        return shipment_service.receive(
            session, session.get_one(DealMemo, barter_memo), NOW
        )

    results = run_together([correct, receive])

    assert isinstance(results[1], BarterShipment), results
    kinds = [e.kind for e in entries(barter_memo)]
    received_at = kinds.index("product_received")
    assert "product_shipped" not in kinds[received_at + 1 :]
    assert isinstance(results[0], BarterShipment | ShipmentAlreadyReceived), results
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, barter_memo)
        assert shipment_service.unchanged(session, memo) is True
        assert record_service.verify(
            memo, record_service.entries_for(session, memo.id)
        ).intact

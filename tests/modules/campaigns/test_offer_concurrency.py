"""Offers at the same moment as each other, an answer, or the application moving (item 44, D-123).

Real, committed connections released together, with every write held open
(`slow_writes`), so the bad ordering happens on every run. Either side may
win; what must never happen is two open offers, an offer both accepted and
withdrawn, or an application accepted with an offer still waiting.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import offer_service as offers
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import OfferAnswered, OfferOpen, OffersClosed
from app.modules.campaigns.models import Application, Campaign
from app.modules.campaigns.offer_models import QuoteOffer
from app.modules.notifications.models import Notification
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW


def run_together(*works: Callable[[Any], Any]) -> list[Any]:
    """Run each `work(session)` in its own thread, released together."""
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
def waiting() -> Iterator[uuid.UUID]:
    """A committed application, shortlisted, on an open paid campaign."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"offer-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        creator = build_creator(
            session, handle=f"oc{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add_all([brand, creator])
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.flush()
        application = Application(
            campaign_id=campaign.id,
            creator_id=creator.id,
            pitch="A Coimbatore cafe page, for an offer race test.",
            quoted_amount_paise=600_000,
            status="shortlisted",
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(application)
        session.commit()
        ids = (application.id, campaign.id, creator.id, brand.id)
        account_ids = [brand_account.id, creator_account.id]
    try:
        yield ids[0]
    finally:
        with SessionLocal() as session:
            session.execute(delete(QuoteOffer).where(QuoteOffer.application_id == ids[0]))
            session.execute(
                delete(Notification).where(Notification.account_id.in_(account_ids))
            )
            session.execute(delete(Application).where(Application.id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[1]))
            session.execute(delete(Creator).where(Creator.id == ids[2]))
            session.execute(delete(Brand).where(Brand.id == ids[3]))
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
            session.commit()


def make(side: str, application_id: uuid.UUID, amount: int) -> Callable[[Any], Any]:
    def work(session):
        application = session.get_one(Application, application_id)
        return offers.make_offer(session, application, side, amount, None, NOW)

    return work


def open_offers(application_id: uuid.UUID) -> list[QuoteOffer]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(QuoteOffer).where(
                    QuoteOffer.application_id == application_id,
                    QuoteOffer.outcome.is_(None),
                )
            ).all()
        )


def test_two_offers_from_one_side_never_both_open(waiting, slow_writes):
    results = run_together(*(make("brand", waiting, 400_000 + n) for n in range(3)))

    assert sum(isinstance(r, QuoteOffer) for r in results) == 1
    assert all(isinstance(r, (QuoteOffer, OfferOpen)) for r in results), results
    assert len(open_offers(waiting)) == 1


def test_an_offer_and_a_counter_leave_exactly_one_open(waiting, slow_writes):
    results = run_together(
        make("brand", waiting, 400_000), make("creator", waiting, 700_000)
    )

    # Both land, one after the other: the second replaces the first.
    assert all(isinstance(r, QuoteOffer) for r in results), results
    assert len(open_offers(waiting)) == 1


def test_an_offer_is_never_both_accepted_and_withdrawn(waiting, slow_writes):
    with SessionLocal() as session:
        offer = offers.make_offer(
            session, session.get_one(Application, waiting), "brand", 400_000, None, NOW
        )
        offer_id = offer.id

    def accept(session):
        return offers.accept(
            session, session.get_one(Application, waiting), offer_id, "creator", NOW
        )

    def withdraw(session):
        return offers.withdraw(
            session, session.get_one(Application, waiting), offer_id, "brand", NOW
        )

    results = run_together(accept, withdraw)

    assert sum(isinstance(r, QuoteOffer) for r in results) == 1
    assert sum(isinstance(r, OfferAnswered) for r in results) == 1, results
    with SessionLocal() as session:
        outcome = session.get_one(QuoteOffer, offer_id).outcome
    assert outcome == ("accepted" if isinstance(results[0], QuoteOffer) else "withdrawn")


def test_an_offer_and_accepting_the_application_never_both_land(waiting, slow_writes):
    def accept_application(session):
        application = session.get_one(Application, waiting)
        return campaigns.change_application_status(
            session, application, "accepted", NOW, actor="brand"
        )

    offered, accepted = run_together(
        make("creator", waiting, 700_000), accept_application
    )

    with SessionLocal() as session:
        status = session.get_one(Application, waiting).status
    if isinstance(offered, QuoteOffer):
        # The offer landed first: the figure is settled before the deal.
        assert isinstance(accepted, OfferOpen), accepted
        assert status == "shortlisted"
    else:
        assert isinstance(offered, OffersClosed), offered
        assert isinstance(accepted, Application)
        assert status == "accepted"

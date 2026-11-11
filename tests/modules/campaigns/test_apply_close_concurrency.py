"""Applying while the brand closes the campaign (audit C11, 11 November 2026).

Applying checks "still open" and then writes. Until audit C11 it read the
campaign without a lock, so a close committed between the check and the
write left an application on a closed campaign. Now applying holds a shared
lock on the campaign until it commits, and closing (`change_status`, which
locks it for update) must wait for it.

Which commit came first cannot be read from the final rows, so this proves
the lock itself: while an application is in flight, a close attempted with
a 50 ms lock timeout times out. Without the lock it goes straight through.
"""

import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.models import Application, Campaign
from app.modules.notifications.models import Notification
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW


@pytest.fixture
def open_campaign() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """A committed open campaign and a creator who may apply: (campaign, creator)."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"apply-close-{uuid.uuid4().hex[:12]}@example.com",
        )
        creator = build_creator(
            session, handle=f"ac{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add_all([brand, creator])
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = (campaign.id, creator.id, brand.id, [brand_account.id, creator_account.id])
    try:
        yield ids[0], ids[1]
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(Notification.account_id.in_(ids[3]))
            )
            session.execute(delete(Application).where(Application.campaign_id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[0]))
            session.execute(delete(Creator).where(Creator.id == ids[1]))
            session.execute(delete(Brand).where(Brand.id == ids[2]))
            session.execute(delete(Account).where(Account.id.in_(ids[3])))
            session.commit()


def test_a_close_waits_for_an_application_in_flight(open_campaign, slow_writes):
    campaign_id, creator_id = open_campaign
    started = threading.Barrier(2)
    results: dict[str, object] = {}

    def apply() -> None:
        with SessionLocal() as session:
            started.wait()
            creator = session.get_one(Creator, creator_id)
            results["apply"] = campaigns.apply_to_campaign(
                session,
                campaign_id,
                creator,
                {"pitch": "A Madurai food page, applying in a race test."},
                NOW,
            ).status

    def close() -> None:
        with SessionLocal() as session:
            started.wait()
            time.sleep(0.05)  # the application has its lock by now
            session.execute(text("SET LOCAL lock_timeout = '50ms'"))
            campaign = session.get_one(Campaign, campaign_id)
            try:
                campaigns.change_status(session, campaign, "closed", NOW)
                results["close"] = "closed"
            except OperationalError as error:
                session.rollback()
                results["close"] = "waited" if "lock timeout" in str(error) else error

    threads = [threading.Thread(target=apply), threading.Thread(target=close)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert results == {"apply": "submitted", "close": "waited"}
    # Once the application is in, the brand closes as usual.
    with SessionLocal() as session:
        campaign = session.get_one(Campaign, campaign_id)
        assert (
            campaigns.change_status(session, campaign, "closed", NOW).status == "closed"
        )

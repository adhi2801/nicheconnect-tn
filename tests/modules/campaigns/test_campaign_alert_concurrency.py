"""Alerts saved, and campaigns sent, at the same moment (item 43, D-130).

Real, committed connections released together. Saving counts the cap
under the creator's row lock (writes held open by `slow_writes`). Sending
runs each batch under one advisory lock; every commit here is held open
(`slow_commits`), so without that lock a second batch would read the daily
count before the first one's rows were committed, every time.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import alert_service
from app.modules.campaigns.alert_models import (
    MAX_ALERTS_PER_CREATOR,
    CampaignAlert,
    CampaignAlertSend,
)
from app.modules.campaigns.exceptions import CampaignAlertsFull
from app.modules.campaigns.models import Campaign
from app.modules.notifications.models import Notification
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW

AT_ONCE = 4
NICHES = [
    "food",
    "fashion",
    "beauty",
    "tech",
    "travel",
    "fitness",
    "education",
    "finance",
]


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
        thread.join(timeout=60)
    return results


@pytest.fixture
def slow_commits() -> Iterator[None]:
    def hold(*args: object) -> None:
        time.sleep(0.2)

    event.listen(Session, "before_commit", hold)
    try:
        yield
    finally:
        event.remove(Session, "before_commit", hold)


@pytest.fixture
def committed() -> Iterator[dict[str, Any]]:
    """A committed brand with AT_ONCE open campaigns, each queued, and a creator."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"alert-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        creator = build_creator(
            session, handle=f"ac{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add(creator)
        session.flush()
        campaigns = [
            build_campaign(session, brand_id=brand.id, title=f"At once {n}")
            for n in range(AT_ONCE)
        ]
        session.add_all(campaigns)
        session.flush()
        sends = [CampaignAlertSend(campaign_id=c.id, queued_at=NOW) for c in campaigns]
        session.add_all(sends)
        session.commit()
        ids = {
            "brand": brand.id,
            "creator": creator.id,
            "creator_account": creator_account.id,
            "campaigns": [c.id for c in campaigns],
            "sends": [s.id for s in sends],
            "accounts": [brand_account.id, creator_account.id],
        }

    try:
        yield ids
    finally:
        with SessionLocal() as session:
            session.execute(
                delete(Notification).where(Notification.account_id.in_(ids["accounts"]))
            )
            session.execute(
                delete(CampaignAlertSend).where(
                    CampaignAlertSend.campaign_id.in_(ids["campaigns"])
                )
            )
            session.execute(delete(Campaign).where(Campaign.id.in_(ids["campaigns"])))
            session.execute(
                delete(CampaignAlert).where(CampaignAlert.creator_id == ids["creator"])
            )
            session.execute(delete(Creator).where(Creator.id == ids["creator"]))
            session.execute(delete(Brand).where(Brand.id == ids["brand"]))
            session.execute(delete(Account).where(Account.id.in_(ids["accounts"])))
            session.commit()


def alerts_held(ids) -> int:
    with SessionLocal() as session:
        return int(
            session.scalar(
                select(func.count()).where(CampaignAlert.creator_id == ids["creator"])
            )
        )


def told(ids) -> list[uuid.UUID]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(Notification.campaign_id).where(
                    Notification.account_id == ids["creator_account"],
                    Notification.notification_type == "campaign_alert",
                )
            ).all()
        )


@contextmanager
def own_session():
    with SessionLocal() as session:
        yield session


def test_alerts_saved_at_once_never_pass_the_cap(committed, slow_writes):
    with SessionLocal() as session:
        session.add_all(
            CampaignAlert(creator_id=committed["creator"], niche=niche)
            for niche in NICHES[: MAX_ALERTS_PER_CREATOR - 1]
        )
        session.commit()

    def save(niche: str) -> Callable[[Any], Any]:
        def work(session):
            creator = session.get_one(Creator, committed["creator"])
            return alert_service.create(
                session,
                creator,
                city=None,
                niche=niche,
                campaign_type=None,
                min_budget_paise=None,
                now=NOW,
            )

        return work

    results = run_together([save(n) for n in NICHES[-AT_ONCE:]])

    assert sum(isinstance(r, CampaignAlert) for r in results) == 1, results
    assert all(isinstance(r, CampaignAlert | CampaignAlertsFull) for r in results), (
        results
    )
    assert alerts_held(committed) == MAX_ALERTS_PER_CREATOR


def test_campaigns_sent_at_once_never_pass_the_daily_cap(
    committed, slow_commits, monkeypatch
):
    monkeypatch.setattr(alert_service, "MAX_ALERTS_A_DAY", 1)
    with SessionLocal() as session:
        session.add(CampaignAlert(creator_id=committed["creator"], niche="food"))
        session.commit()

    def send(send_id: uuid.UUID) -> Callable[[Any], Any]:
        def work(session):
            return alert_service.send_one(own_session, send_id, NOW)

        return work

    results = run_together([send(s) for s in committed["sends"]])

    assert all(isinstance(r, int) for r in results), results
    assert len(told(committed)) == 1


def test_one_campaign_sent_by_two_runs_at_once_tells_once(committed, slow_commits):
    with SessionLocal() as session:
        session.add(CampaignAlert(creator_id=committed["creator"], niche="food"))
        session.commit()
    send_id = committed["sends"][0]

    def send(session):
        return alert_service.send_one(own_session, send_id, NOW)

    results = run_together([send] * AT_ONCE)

    assert all(isinstance(r, int) for r in results), results
    assert told(committed) == [committed["campaigns"][0]]
    with SessionLocal() as session:
        recipients = session.get_one(CampaignAlertSend, send_id).recipients
    assert recipients == 1

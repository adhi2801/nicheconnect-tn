"""Erasing an account at the same moment as a memo, an invitation or a cancel (item 6, D-122).

Real, committed connections released together, with every write held open
for a moment (`slow_writes`), so the bad ordering happens on every run.
Either side may win; what must never happen is both: a memo or a waiting
invitation for a creator who left, or a cancel that half-undoes an erasure.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import invitation_service
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import CampaignNotOpen, CreatorNotFound
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.exceptions import CreatorLeft
from app.modules.deal_memo.models import DealMemo
from app.modules.me import account_deletion_service as service
from app.modules.notifications.models import Notification
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW

WAIT = timedelta(days=30)


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


def make_due(account_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        account = session.get_one(Account, account_id)
        account.deletion_requested_at = NOW - WAIT - timedelta(minutes=1)
        account.deletion_takes_effect_at = account.deletion_requested_at + WAIT
        session.commit()


def creator_account_of(application_id: uuid.UUID) -> uuid.UUID:
    with SessionLocal() as session:
        return session.scalars(
            select(Creator.account_id)
            .join(Application, Application.creator_id == Creator.id)
            .where(Application.id == application_id)
        ).one()


def test_a_memo_and_the_erasure_never_both_land(committed_application, slow_writes):
    creator_account_id = creator_account_of(committed_application)
    make_due(creator_account_id)

    def write_memo(session):
        application = session.get_one(Application, committed_application)
        return memos.create_memo(
            session,
            application,
            {"deliverables": "Two reels, for a race test.", "fee_amount_paise": 400_000},
            NOW,
        )

    erased, memo = run_together(
        lambda session: service.erase(session, creator_account_id, NOW), write_memo
    )

    with SessionLocal() as session:
        memos_written = session.scalars(
            select(DealMemo.id).where(DealMemo.application_id == committed_application)
        ).all()
        deleted_at = session.get_one(Account, creator_account_id).deleted_at
    if erased == "erased":
        assert isinstance(memo, CreatorLeft)
        assert memos_written == []
        assert deleted_at is not None
    else:
        # The memo landed first: the draft is a deal someone waits on.
        assert erased == "held"
        assert isinstance(memo, DealMemo)
        assert len(memos_written) == 1
        assert deleted_at is None


@pytest.fixture
def invitable() -> Iterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """A committed open campaign, and a committed creator about to be erased."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"erase-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        creator = build_creator(
            session, handle=f"ec{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add_all([brand, creator])
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = (campaign.id, creator.id, creator_account.id)
        cleanup = (brand.id, [brand_account.id, creator_account.id])
    make_due(ids[2])
    try:
        yield ids
    finally:
        with SessionLocal() as session:
            session.execute(delete(Application).where(Application.campaign_id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[0]))
            session.execute(delete(Creator).where(Creator.id == ids[1]))
            session.execute(delete(Brand).where(Brand.id == cleanup[0]))
            session.execute(
                delete(Notification).where(Notification.account_id.in_(cleanup[1]))
            )
            session.execute(delete(Account).where(Account.id.in_(cleanup[1])))
            session.commit()


def test_an_invitation_and_the_erasure_never_leave_one_waiting(invitable, slow_writes):
    campaign_id, creator_id, creator_account_id = invitable

    def invite(session):
        campaign = session.get_one(Campaign, campaign_id)
        return invitation_service.invite_creator(session, campaign, creator_id, None, NOW)

    erased, invitation = run_together(
        lambda session: service.erase(session, creator_account_id, NOW), invite
    )

    assert erased == "erased"
    with SessionLocal() as session:
        statuses = session.scalars(
            select(Application.status).where(Application.campaign_id == campaign_id)
        ).all()
    if isinstance(invitation, CreatorNotFound):
        assert statuses == []
    else:
        # It landed first, and the erasure declined it with the rest.
        assert isinstance(invitation, Application)
        assert statuses == ["declined"]


def test_a_cancel_and_the_erasure_never_half_undo_it(invitable, slow_writes):
    _, _, creator_account_id = invitable

    def cancel(session):
        account = session.get_one(Account, creator_account_id)
        service.cancel(session, account, NOW)
        return "cancelled"

    erased, cancelled = run_together(
        lambda session: service.erase(session, creator_account_id, NOW), cancel
    )

    assert cancelled == "cancelled"
    with SessionLocal() as session:
        account = session.get_one(Account, creator_account_id)
        if erased == "erased":
            # Done first: the cancel found nothing to undo, and the dates stay.
            assert account.deleted_at is not None
            assert account.deletion_requested_at is not None
        else:
            assert erased is None
            assert account.deleted_at is None
            assert account.deletion_requested_at is None
            assert account.phone is not None


@pytest.fixture
def leaving_brand() -> Iterator[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    """A committed brand about to be erased, its open campaign, and a creator."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"leave-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        creator = build_creator(
            session, handle=f"lc{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add_all([brand, creator])
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = (campaign.id, creator.id, brand_account.id)
        cleanup = (brand.id, [brand_account.id, creator_account.id])
    make_due(ids[2])
    try:
        yield ids
    finally:
        with SessionLocal() as session:
            session.execute(delete(Application).where(Application.campaign_id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[0]))
            session.execute(delete(Creator).where(Creator.id == ids[1]))
            session.execute(delete(Brand).where(Brand.id == cleanup[0]))
            session.execute(
                delete(Notification).where(Notification.account_id.in_(cleanup[1]))
            )
            session.execute(delete(Account).where(Account.id.in_(cleanup[1])))
            session.commit()


def test_an_application_and_a_brands_erasure_never_deadlock(leaving_brand, slow_writes):
    campaign_id, creator_id, brand_account_id = leaving_brand

    def apply(session):
        creator = session.get_one(Creator, creator_id)
        return campaigns.apply_to_campaign(
            session,
            campaign_id,
            creator,
            {"pitch": "A Salem food page, for a race test."},
            NOW,
        )

    erased, applied = run_together(
        lambda session: service.erase(session, brand_account_id, NOW), apply
    )

    assert erased == "erased"
    assert isinstance(applied, (Application, CampaignNotOpen)), applied
    with SessionLocal() as session:
        assert session.get_one(Campaign, campaign_id).status == "closed"

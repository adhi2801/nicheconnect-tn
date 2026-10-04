"""Fixtures shared by the module tests.

A test module that needs something different defines its own `clock` or
`client`, and pytest uses that one instead of these.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.db.session import SessionLocal, get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from tests.deal_flow import Clock
from tests.factories import (
    FIXED_NOW,
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.record_cleanup import remove_deal_records


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def client(db: Session, clock: Clock) -> Iterator[TestClient]:
    """The app, on the rolled-back test session, seeing the test's clock."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


# --- committed rows, for the concurrency tests --------------------------------------
#
# Concurrency tests need separate connections that really commit, so they
# cannot use the rolled-back `db` session. These build their own rows and
# remove them afterwards.

CONCURRENCY_NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)


@pytest.fixture
def slow_writes() -> Iterator[None]:
    """Hold every write for a moment just before it reaches the database.

    A race between two requests lasts a few milliseconds, so without this a
    test of unsafe code passes by luck. A busy database or a slow network
    holds that window open in production; this does the same in a test.
    """

    def hold(*args: object) -> None:
        time.sleep(0.2)

    event.listen(Session, "before_flush", hold)
    try:
        yield
    finally:
        event.remove(Session, "before_flush", hold)


@pytest.fixture
def committed_application() -> Iterator[uuid.UUID]:
    """A real, committed, accepted application with no memo yet."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        creator_account = create_account(session, "creator", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"memo-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        creator = build_creator(
            session, handle=f"mc{uuid.uuid4().hex[:12]}", account_id=creator_account.id
        )
        session.add(creator)
        session.flush()
        row = Application(
            campaign_id=campaign.id,
            creator_id=creator.id,
            pitch="I run a Coimbatore cafe page, for a concurrency test.",
            status="accepted",
            status_changed_at=CONCURRENCY_NOW,
            created_at=CONCURRENCY_NOW,
            updated_at=CONCURRENCY_NOW,
        )
        session.add(row)
        session.commit()
        ids = (row.id, campaign.id, creator.id, brand.id)
        account_ids = [brand_account.id, creator_account.id]

    try:
        yield ids[0]
    finally:
        with SessionLocal() as session:
            memo_ids = list(
                session.scalars(
                    select(DealMemo.id).where(DealMemo.application_id == ids[0])
                ).all()
            )
            remove_deal_records(session, memo_ids)
            session.execute(
                delete(DeliverableProof).where(
                    DeliverableProof.deal_memo_id.in_(memo_ids)
                )
            )
            session.execute(delete(DealMemo).where(DealMemo.id.in_(memo_ids)))
            session.execute(delete(Application).where(Application.id == ids[0]))
            session.execute(delete(Campaign).where(Campaign.id == ids[1]))
            session.execute(delete(Creator).where(Creator.id == ids[2]))
            session.execute(delete(Brand).where(Brand.id == ids[3]))
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
            session.commit()


@pytest.fixture
def committed_memo(committed_application) -> uuid.UUID:
    """The application's memo, accepted, with no proof yet."""
    with SessionLocal() as session:
        memo = DealMemo(
            application_id=committed_application,
            deliverables="Three reels, for a concurrency test.",
            fee_amount_paise=800_000,
            status="accepted",
            created_at=CONCURRENCY_NOW,
            updated_at=CONCURRENCY_NOW,
        )
        session.add(memo)
        session.commit()
        return memo.id

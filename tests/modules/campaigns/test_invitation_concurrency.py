"""Invitations arriving at once: the limit holds, and a repeat drafts one memo.

Two rules here are "check, then write" (backend.md section 5): at most
MAX_WAITING_INVITATIONS unanswered invitations per campaign, and one memo
per accepted repeat. Each is held by a row lock, and each test holds the gap
between check and write open, so the race happens every run, not by luck.

These need separate, really-committing connections, so they build their own
rows and remove them afterwards.
"""

import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, func, select

import app.db.models  # noqa: F401 - registers every table, as the app does
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns import invitation_service
from app.modules.campaigns.exceptions import (
    ApplicationStatusConflict,
    InvitationLimitReached,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from tests.factories import (
    build_brand,
    build_campaign,
    build_creator,
    create_account,
    unique_test_phone,
)
from tests.modules.conftest import CONCURRENCY_NOW as NOW
from tests.modules.payment_status.test_payment_concurrency import (
    AT_ONCE,
    run_at_once,
    split,
)
from tests.record_cleanup import remove_deal_records


@dataclass
class Rows:
    campaign_id: uuid.UUID
    earlier_campaign_id: uuid.UUID
    creator_ids: list[uuid.UUID]
    earlier_application_id: uuid.UUID
    invitation_id: uuid.UUID


@pytest.fixture
def rows() -> Iterator[Rows]:
    """A brand with an open campaign, AT_ONCE creators, and one repeat waiting.

    The first creator had an agreed deal on an earlier campaign, and is
    invited to the open one as a repeat of it.
    """
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"inv-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        earlier = build_campaign(session, status="closed", brand_id=brand.id)
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add_all([earlier, campaign])
        accounts = [brand_account.id]
        creators = []
        for _ in range(AT_ONCE + 1):
            account = create_account(session, "creator", phone=unique_test_phone())
            accounts.append(account.id)
            creator = build_creator(
                session, handle=f"ic{uuid.uuid4().hex[:12]}", account_id=account.id
            )
            session.add(creator)
            creators.append(creator)
        session.flush()
        first = creators[0]
        earlier_application = Application(
            campaign_id=earlier.id,
            creator_id=first.id,
            pitch="I run a Coimbatore cafe page, for a concurrency test.",
            status="accepted",
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(earlier_application)
        session.flush()
        session.add(
            DealMemo(
                application_id=earlier_application.id,
                deliverables="Three reels, for a concurrency test.",
                fee_amount_paise=800_000,
                status="accepted",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        invitation = Application(
            campaign_id=campaign.id,
            creator_id=first.id,
            origin="invited",
            status="invited",
            repeat_of_application_id=earlier_application.id,
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(invitation)
        session.commit()
        found = Rows(
            campaign_id=campaign.id,
            earlier_campaign_id=earlier.id,
            creator_ids=[creator.id for creator in creators[1:]],
            earlier_application_id=earlier_application.id,
            invitation_id=invitation.id,
        )
        all_creators = [creator.id for creator in creators]
        brand_id = brand.id

    try:
        yield found
    finally:
        with SessionLocal() as session:
            campaigns = [found.campaign_id, found.earlier_campaign_id]
            applications = select(Application.id).where(
                Application.campaign_id.in_(campaigns)
            )
            memo_ids = list(
                session.scalars(
                    select(DealMemo.id).where(DealMemo.application_id.in_(applications))
                )
            )
            remove_deal_records(session, memo_ids)
            session.execute(delete(DealMemo).where(DealMemo.id.in_(memo_ids)))
            # Repeats first: they point at the earlier application.
            session.execute(
                delete(Application).where(Application.campaign_id == found.campaign_id)
            )
            session.execute(
                delete(Application).where(
                    Application.campaign_id == found.earlier_campaign_id
                )
            )
            session.execute(delete(Campaign).where(Campaign.id.in_(campaigns)))
            session.execute(delete(Creator).where(Creator.id.in_(all_creators)))
            session.execute(delete(Brand).where(Brand.id == brand_id))
            # Notifications go with their accounts (ON DELETE CASCADE).
            session.execute(delete(Account).where(Account.id.in_(accounts)))
            session.commit()


def test_simultaneous_invitations_never_pass_the_limit(rows, monkeypatch):
    # One repeat is already waiting, so two more fill a limit of three.
    monkeypatch.setattr(invitation_service, "MAX_WAITING_INVITATIONS", 3)
    original = invitation_service.is_suspended

    def slow(*args, **kwargs):  # between the lock and the count
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(invitation_service, "is_suspended", slow)
    queue = list(rows.creator_ids)

    results = run_at_once(
        lambda s: invitation_service.invite_creator(
            s, s.get(Campaign, rows.campaign_id), queue.pop(), None, NOW
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, InvitationLimitReached)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (2, AT_ONCE - 2)
    with SessionLocal() as session:
        waiting = session.scalar(
            select(func.count()).where(
                Application.campaign_id == rows.campaign_id,
                Application.status == "invited",
            )
        )
    assert waiting == 3


def test_a_repeat_accepted_twice_at_once_drafts_one_memo(rows, slow_writes):
    results = run_at_once(
        lambda s: invitation_service.accept_invitation(
            s, s.get(Application, rows.invitation_id), NOW
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, ApplicationStatusConflict)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    with SessionLocal() as session:
        memos = session.scalar(
            select(func.count()).where(DealMemo.application_id == rows.invitation_id)
        )
    assert memos == 1

"""Two requests at once on one deal: never a 500, always one clear answer.

Review findings, PR #9: creating a memo and submitting proof both checked
"does one exist already?" and then wrote. Two requests together both passed
the check, the database's unique rule refused the second write, and the
error nobody caught reached the caller as a 500 instead of the conflict the
API documents.

Like the payment concurrency tests, these need separate, really-committing
connections, so they build their own rows and remove them afterwards. The
gap between each check and its write is held open on purpose, so the race
happens every run rather than by luck.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import proof_service
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.exceptions import MemoAlreadyExists, ProofAlreadyDecided
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from tests.factories import build_brand, build_campaign, build_creator, create_account
from tests.modules.payment_status.test_payment_concurrency import (
    AT_ONCE,
    run_at_once,
    split,
    unique_phone,
)
from tests.record_cleanup import remove_deal_records

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
LINK = "https://www.instagram.com/reel/concurrency/"


@pytest.fixture
def application() -> Iterator[uuid.UUID]:
    """A real, committed, accepted application with no memo yet."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_phone())
        creator_account = create_account(session, "creator", phone=unique_phone())
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
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
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
def accepted_memo(application) -> uuid.UUID:
    """The application's memo, accepted, with no proof yet."""
    with SessionLocal() as session:
        memo = DealMemo(
            application_id=application,
            deliverables="Three reels, for a concurrency test.",
            fee_amount_paise=800_000,
            status="accepted",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        return memo.id


def test_two_simultaneous_memos_for_one_application_give_one_memo_and_conflicts(
    application, monkeypatch
):
    original = memos._campaign_of

    def slow(*args, **kwargs):  # between the existence check and the write
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(memos, "_campaign_of", slow)

    results = run_at_once(
        lambda s: memos.create_memo(
            s,
            s.get(Application, application),
            {"deliverables": "Three reels.", "fee_amount_paise": 800_000},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, MemoAlreadyExists)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)


def test_two_simultaneous_proof_submissions_give_one_proof_and_conflicts(
    accepted_memo, monkeypatch
):
    original = proof_service.record.append

    def slow(*args, **kwargs):  # between the open-submission check and the commit
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(proof_service.record, "append", slow)

    results = run_at_once(
        lambda s: proof_service.submit_proof(
            s,
            s.get(DealMemo, accepted_memo),
            {"content_url": LINK, "format": "reel"},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)

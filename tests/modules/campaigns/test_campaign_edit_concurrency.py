"""Two changes to one campaign at once (audit C10, 8 November 2026).

Each change to a campaign is checked as a whole: the budget rules on the
campaign as it would be after it (audit C6), and which fields may change on
its status. Both read the campaign first, so without a lock two changes, each
fine alone, both passed their checks on the same old row and together broke
the database's budget check: one person's save answered 500.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.campaigns import service as campaigns
from app.modules.campaigns.exceptions import CampaignBudgetInvalid
from app.modules.campaigns.models import Campaign
from tests.factories import build_brand, build_campaign, create_account, unique_test_phone
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
def draft() -> Iterator[uuid.UUID]:
    """A committed draft paid campaign, budget 5,000 to 15,000 rupees."""
    with SessionLocal() as session:
        account = create_account(session, "brand", phone=unique_test_phone())
        brand = build_brand(
            session,
            account_id=account.id,
            email=f"edit-conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        campaign = build_campaign(session, status="draft", brand_id=brand.id)
        session.add(campaign)
        session.commit()
        ids = (campaign.id, brand.id, account.id)
    try:
        yield ids[0]
    finally:
        with SessionLocal() as session:
            session.execute(delete(Campaign).where(Campaign.id == ids[0]))
            session.execute(delete(Brand).where(Brand.id == ids[1]))
            session.execute(delete(Account).where(Account.id == ids[2]))
            session.commit()


def change(campaign_id: uuid.UUID, changes: dict[str, Any]) -> Callable[[Any], Any]:
    def work(session):
        campaign = session.get_one(Campaign, campaign_id)
        return campaigns.update_campaign(session, campaign, dict(changes), NOW)

    return work


def test_two_budget_changes_fine_alone_never_break_the_budget_together(
    draft, slow_writes
):
    results = run_together(
        change(draft, {"budget_max_paise": 600_000}),
        change(draft, {"budget_min_paise": 1_000_000}),
    )

    raw = [
        r
        for r in results
        if isinstance(r, Exception) and not isinstance(r, CampaignBudgetInvalid)
    ]
    assert raw == [], f"a raw database error reached the caller: {raw}"
    refused = [r for r in results if isinstance(r, CampaignBudgetInvalid)]
    assert len(refused) == 1
    with SessionLocal() as session:
        campaign = session.get_one(Campaign, draft)
        assert campaign.budget_min_paise <= campaign.budget_max_paise

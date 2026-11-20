"""Building what a quarterly city rate report counts, for its tests (item 84, D-200).

Each world has a city of its own, so rows other tests leave cannot change
its counts (testing.md section 4).
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application
from app.modules.deal_memo.deliverable_models import MemoDeliverable
from app.modules.deal_memo.models import DealMemo
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from tests.factories import build_brand, build_campaign, build_creator

PUBLISHED = datetime(2026, 5, 1, tzinfo=UTC)
# A moment inside 2026-Q2, and the morning the report on it is built.
IN_Q2 = datetime(2026, 5, 15, 6, 0, tzinfo=UTC)
BUILT = datetime(2026, 7, 2, 0, 30, tzinfo=UTC)
PITCH = "I run a Madurai street-food page with 12,000 local followers."


def city_name() -> str:
    return f"Ratepur {uuid.uuid4().hex[:10]}"


class World:
    """Creators, prices and deals in one city of this world's own."""

    def __init__(self, db: Session, city: str | None = None) -> None:
        self.db = db
        self.city = city or city_name()

    def creator(
        self,
        *,
        prices: dict[tuple[str, str], list[int]] | None = None,
        passport: bool = True,
        rate_card: bool = True,
        followers: int | None = None,
        city: str | None = None,
    ) -> Creator:
        creator = build_creator(
            self.db,
            handle=f"r{uuid.uuid4().hex[:12]}",
            city=city or self.city,
            passport_published_at=PUBLISHED if passport else None,
            rate_card_public_at=PUBLISHED if rate_card and prices else None,
        )
        self.db.add(creator)
        self.db.flush()
        position = 0
        for (platform, package_format), amounts in (prices or {}).items():
            for amount in amounts:
                self.db.add(
                    CreatorPackage(
                        creator_id=creator.id,
                        platform=platform,
                        format=package_format,
                        title="One piece",
                        price_paise=amount,
                        delivery_days=5,
                        position=position,
                    )
                )
                position += 1
        if followers is not None:
            for platform in {platform for platform, _ in prices or {}}:
                self.db.add(
                    CreatorChannel(
                        creator_id=creator.id,
                        platform=platform,
                        profile_url=f"https://{platform}.com/{creator.handle}",
                        followers=followers,
                        average_views=None,
                        figures_as_of=date(2026, 4, 1),
                    )
                )
        self.db.flush()
        return creator

    def listed(self, extra: int = 5) -> list[Creator]:
        """Published creators enough for the city to be listed, with no prices."""
        return [self.creator() for _ in range(extra)]

    def brand(self) -> Brand:
        brand = build_brand(self.db, email=f"r-{uuid.uuid4().hex[:12]}@example.com")
        self.db.add(brand)
        self.db.flush()
        return brand

    def deal(
        self,
        creator: Creator,
        brand: Brand,
        *,
        fee: int | None = 500_000,
        accepted: datetime = IN_Q2,
        status: str = "accepted",
        deliverables: list[tuple[str, str, int]] | None = None,
    ) -> DealMemo:
        campaign = build_campaign(
            self.db,
            brand_id=brand.id,
            campaign_type="paid" if fee is not None else "barter",
            budget_min_paise=None if fee is None else 100_000,
            budget_max_paise=None if fee is None else 5_000_000,
        )
        self.db.add(campaign)
        self.db.flush()
        application = Application(
            campaign_id=campaign.id,
            creator_id=creator.id,
            origin="applied",
            pitch=PITCH,
            status="accepted",
            status_changed_at=accepted,
            created_at=accepted,
            updated_at=accepted,
        )
        self.db.add(application)
        self.db.flush()
        memo = DealMemo(
            application_id=application.id,
            deliverables="One reel.",
            fee_amount_paise=fee,
            status=status,
            accepted_at=accepted if status != "sent" else None,
            cancellation_kind="cancelled_by_brand" if status == "cancelled" else None,
            created_at=accepted,
            updated_at=accepted,
        )
        self.db.add(memo)
        self.db.flush()
        for position, (platform, package_format, quantity) in enumerate(
            deliverables or [("instagram", "reel", 1)]
        ):
            self.db.add(
                MemoDeliverable(
                    deal_memo_id=memo.id,
                    position=position,
                    platform=platform,
                    format=package_format,
                    quantity=quantity,
                    note=None,
                )
            )
        self.db.flush()
        return memo


def suspend(db: Session, account_id: uuid.UUID) -> None:
    account = db.get(Account, account_id)
    assert account is not None
    account.suspended_at = PUBLISHED
    account.suspension_reason = "fake_profile"
    db.flush()

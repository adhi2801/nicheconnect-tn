"""Fill a local database with realistic Tamil Nadu sample data.

For local development and performance checks (database.md section 8). Refuses
to run outside ENVIRONMENT=local, and never invents real contact details:
phones are +9190000000xx and emails end in @example.com.

    python scripts/seed_dev_data.py --help
    python scripts/seed_dev_data.py --reset
"""

import argparse
import pathlib
import random
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

# Run as `python scripts/seed_dev_data.py` from the project root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.taxonomy import CURRENCY, NICHES
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import (
    MAX_PACKAGES_PER_CREATOR,
    CreatorChannel,
    CreatorPackage,
)
from app.modules.campaigns.models import (
    CAMPAIGN_TYPES,
    REJECTION_REASONS,
    Application,
    Campaign,
)

# Obviously fake: this range is reserved for sample data. It still has to pass
# the database's Indian-mobile rule, so it starts +919, not the +9100000000xx
# in database.md section 8 (that example cannot be stored).
PHONE_PREFIX = "+9190000"

TAMIL_NADU_CITIES = (
    "Chennai",
    "Coimbatore",
    "Madurai",
    "Tiruchirappalli",
    "Salem",
    "Tirunelveli",
    "Erode",
    "Vellore",
    "Thoothukudi",
    "Thanjavur",
)
BRAND_NAMES = (
    "Amma Sweets",
    "Kongu Textiles",
    "Meenakshi Silks",
    "Chettinad Spice Co",
    "Madurai Malli Flowers",
    "Nilgiri Tea House",
    "Coimbatore Cycles",
    "Marina Streetwear",
    "Thanjavur Handicrafts",
    "Salem Steel Kitchenware",
)
CAMPAIGN_TITLES = (
    "Pongal gift box launch",
    "Aadi sale reels",
    "New store opening in {city}",
    "Deepavali collection preview",
    "Weekend food trail in {city}",
    "Monsoon skincare routine",
    "Back to college essentials",
    "Wedding season lookbook",
)
PITCHES = (
    "I cover {niche} in {city} and my audience is mostly local families. "
    "I can deliver the reels within a week of receiving the products.",
    "My {city} page focuses on {niche}. Last month's similar collaboration "
    "reached 40,000 accounts, with most viewers from Tamil Nadu.",
    "I have been posting {niche} content in {city} for three years. "
    "Happy to shoot in Tamil, with English subtitles for wider reach.",
)
STATUS_WEIGHTS = {"draft": 1, "open": 6, "closed": 2, "cancelled": 1}
# (platform, format, title, price in paise, delivery days)
PACKAGE_OFFERS = (
    ("instagram", "reel", "1 Instagram Reel", 800_000, 5),
    ("instagram", "story", "3-story set", 300_000, 2),
    ("instagram", "post", "1 feed post", 500_000, 3),
    ("instagram", "live", "30-minute Instagram Live", 1_200_000, 7),
    ("youtube", "short", "1 YouTube Short", 600_000, 5),
    ("youtube", "video", "Dedicated YouTube video", 2_500_000, 14),
    ("youtube", "video", "60-second integration in a video", 1_500_000, 10),
    ("instagram", "reel", "Reel plus 2 stories", 1_000_000, 6),
    ("instagram", "other", "Store visit and reel", 1_800_000, 10),
    ("youtube", "live", "YouTube live unboxing", 2_000_000, 10),
)
APPLICATION_STATUS_WEIGHTS = {
    "submitted": 6,
    "shortlisted": 2,
    "accepted": 1,
    "rejected": 2,
    "withdrawn": 1,
}


def fake_phone(index: int) -> str:
    """+9190000xxxxx: valid in shape, obviously not a real number."""
    return f"{PHONE_PREFIX}{index:05d}"


def clear_sample_data(db) -> None:
    """Remove everything this script creates, newest tables first."""
    db.execute(delete(Application))
    db.execute(delete(Campaign))
    db.execute(delete(Brand))
    db.execute(delete(Creator))
    db.execute(delete(Account).where(Account.phone.like(f"{PHONE_PREFIX}%")))
    db.commit()


def seed(
    db,
    *,
    brands: int,
    creators: int,
    campaigns: int,
    applications: int,
    now: datetime,
    rng: random.Random,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    phone_number = 1

    brand_rows: list[Brand] = []
    for index in range(brands):
        account = Account(phone=fake_phone(phone_number), role="brand")
        phone_number += 1
        db.add(account)
        db.flush()
        name = BRAND_NAMES[index % len(BRAND_NAMES)]
        brand_rows.append(
            Brand(
                account_id=account.id,
                account_role="brand",
                name=f"{name}" if index < len(BRAND_NAMES) else f"{name} {index}",
                email=f"brand{index:03d}@example.com",
            )
        )
    db.add_all(brand_rows)
    db.flush()
    counts["brands"] = len(brand_rows)

    creator_rows: list[Creator] = []
    for index in range(creators):
        account = Account(phone=fake_phone(phone_number), role="creator")
        phone_number += 1
        db.add(account)
        db.flush()
        city = rng.choice(TAMIL_NADU_CITIES)
        niches = rng.sample(NICHES, rng.randint(1, 3))
        creator_rows.append(
            Creator(
                account_id=account.id,
                account_role="creator",
                display_name=f"Creator {index:04d}",
                handle=f"creator.{index:04d}",
                city=city,
                niches=niches,
                languages=["en"],
                bio=f"{niches[0].title()} creator based in {city}.",
            )
        )
    db.add_all(creator_rows)
    db.flush()
    counts["creators"] = len(creator_rows)

    # Channels and rate cards (D-055). About half the creators publish their
    # Passport and, separately, their prices. The first creator always has
    # both channels and the full ten packages, published, so the media kit
    # and the public page can be measured at their largest.
    channel_rows: list[CreatorChannel] = []
    package_rows: list[CreatorPackage] = []
    for index, creator in enumerate(creator_rows):
        fullest = index == 0
        if fullest or rng.random() < 0.5:
            creator.passport_published_at = now
        if fullest or rng.random() < 0.5:
            creator.rate_card_public_at = now
        platforms = ["instagram"]
        if fullest or rng.random() < 0.4:
            platforms.append("youtube")
        for platform in platforms:
            followers = rng.randint(2_000, 250_000)
            channel_rows.append(
                CreatorChannel(
                    creator_id=creator.id,
                    platform=platform,
                    profile_url=f"https://{platform}.com/{creator.handle}",
                    followers=followers,
                    average_views=rng.choice([None, followers // rng.randint(3, 20)]),
                    figures_as_of=now.date(),
                )
            )
        how_many = (
            MAX_PACKAGES_PER_CREATOR
            if fullest
            else rng.randint(0, MAX_PACKAGES_PER_CREATOR)
        )
        for position, offer in enumerate(rng.sample(PACKAGE_OFFERS, how_many)):
            platform, package_format, title, price, days = offer
            package_rows.append(
                CreatorPackage(
                    creator_id=creator.id,
                    platform=platform,
                    format=package_format,
                    title=title,
                    price_paise=price,
                    currency=CURRENCY,
                    delivery_days=days,
                    usage_rights_days=rng.choice([None, 30, 90]),
                    position=position,
                )
            )
    db.add_all(channel_rows)
    db.add_all(package_rows)
    db.flush()
    counts["channels"] = len(channel_rows)
    counts["packages"] = len(package_rows)

    statuses = list(STATUS_WEIGHTS)
    status_weights = list(STATUS_WEIGHTS.values())
    campaign_rows: list[Campaign] = []
    for index in range(campaigns):
        brand = rng.choice(brand_rows)
        city = rng.choice(TAMIL_NADU_CITIES)
        campaign_type = rng.choice(CAMPAIGN_TYPES)
        budget_min = rng.choice([200_000, 500_000, 1_000_000, 2_500_000])
        budget_max = budget_min + rng.choice([100_000, 500_000, 1_500_000])
        if campaign_type == "barter":
            budget_min = budget_max = None
        campaign_rows.append(
            Campaign(
                brand_id=brand.id,
                title=CAMPAIGN_TITLES[index % len(CAMPAIGN_TITLES)].format(city=city),
                description=(
                    f"We are looking for creators in {city} to feature our products. "
                    "Content in Tamil is welcome."
                ),
                campaign_type=campaign_type,
                budget_min_paise=budget_min,
                budget_max_paise=budget_max,
                cities=rng.sample(TAMIL_NADU_CITIES, rng.randint(1, 3)),
                niches=rng.sample(NICHES, rng.randint(1, 3)),
                deliverables="2 Instagram reels and 1 story set.",
                applications_close_on=(now + timedelta(days=rng.randint(5, 45))).date(),
                status=rng.choices(statuses, weights=status_weights)[0],
                # Spread over the last 90 days so paging has something to page.
                created_at=now - timedelta(minutes=rng.randint(0, 90 * 24 * 60)),
                updated_at=now,
            )
        )
    db.add_all(campaign_rows)
    db.flush()
    counts["campaigns"] = len(campaign_rows)

    application_statuses = list(APPLICATION_STATUS_WEIGHTS)
    application_weights = list(APPLICATION_STATUS_WEIGHTS.values())
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    application_rows: list[Application] = []
    open_campaigns = [row for row in campaign_rows if row.status in ("open", "closed")]
    for _ in range(applications):
        campaign = rng.choice(open_campaigns)
        creator = rng.choice(creator_rows)
        key = (campaign.id, creator.id)
        if key in seen:
            continue  # one application per creator per campaign
        seen.add(key)
        status = rng.choices(application_statuses, weights=application_weights)[0]
        application_rows.append(
            Application(
                campaign_id=campaign.id,
                creator_id=creator.id,
                pitch=rng.choice(PITCHES).format(
                    niche=creator.niches[0], city=creator.city
                ),
                quoted_amount_paise=rng.choice([None, 300_000, 750_000, 1_200_000]),
                status=status,
                rejection_reason=(
                    rng.choice(REJECTION_REASONS) if status == "rejected" else None
                ),
                status_changed_at=now,
                created_at=campaign.created_at + timedelta(minutes=rng.randint(1, 5000)),
                updated_at=now,
            )
        )
    db.add_all(application_rows)
    db.commit()
    counts["applications"] = len(application_rows)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brands", type=int, default=10)
    parser.add_argument("--creators", type=int, default=200)
    parser.add_argument("--campaigns", type=int, default=150)
    parser.add_argument("--applications", type=int, default=800)
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed, for repeatable data"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing sample data first"
    )
    args = parser.parse_args()

    if settings.environment != "local":
        print(
            f"Refusing to run: ENVIRONMENT is '{settings.environment}', not 'local'.",
            file=sys.stderr,
        )
        return 1

    rng = random.Random(args.seed)  # noqa: S311 - repeatable fake data, not security
    now = datetime.now(UTC)
    started = time.perf_counter()

    with SessionLocal() as db:
        if args.reset:
            clear_sample_data(db)
        existing = db.scalar(select(func.count()).select_from(Campaign))
        if existing:
            print(
                f"Refusing to run: {existing} campaigns already exist. "
                "Use --reset to replace the sample data.",
                file=sys.stderr,
            )
            return 1
        counts = seed(
            db,
            brands=args.brands,
            creators=args.creators,
            campaigns=args.campaigns,
            applications=args.applications,
            now=now,
            rng=rng,
        )

    seconds = time.perf_counter() - started
    print(f"Seeded in {seconds:.1f}s:")
    for name, count in counts.items():
        print(f"  {count:>5} {name}")
    print("\nSample phones look like +919000000001; emails end in @example.com.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

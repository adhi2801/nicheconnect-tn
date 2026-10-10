"""City figures for public pages: counts and medians, five or nothing (D-078).

"Coimbatore: 34 food creators, a Reel usually asks ₹6,000." City pages are
how search engines and AI answer engines find a local marketplace
(`docs/GO_TO_MARKET.md`), so the backend answers them now and a page is
published once a city has the data (D-071).

What counts, and why:

- **Only creators who published their Passport** (D-036): they chose to be
  seen by strangers. Asking prices count only from published rate cards, as
  in fair-rate guidance (D-056).
- **Suspended accounts never count** (D-061), nor their brands' campaigns.
- **Open campaigns** are public by design, so they are counted too.
- **Nothing from deals.** A deal is private between its brand and its
  creator (D-071 declined even a public receipt), so no figure here is built
  from one.
- **Counts and medians only, never a minimum or maximum**: each of those is
  one person.
- **Five or nothing.** Any figure resting on fewer than five creators or
  campaigns is None, meaning not enough to say, so no single person's price
  or presence can be read off a page (D-056).

Cities are typed by people, so they match case-insensitively, and a city is
shown with the spelling most of its creators used.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Row, exists, func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import CURRENCY, NICHES, Niche
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorPackage
from app.modules.auth.suspension import account_is_active, brand_is_active
from app.modules.campaigns.models import Campaign

MIN_COUNT = 5  # as fair-rate guidance (D-056)


def _shown(count: int) -> int | None:
    return count if count >= MIN_COUNT else None


def _published_creators() -> list[ColumnElement[bool]]:
    return [
        Creator.passport_published_at.is_not(None),
        account_is_active(Creator.account_id),
    ]


@dataclass(frozen=True)
class CityCount:
    city: str
    published_creators: int


@dataclass(frozen=True)
class AskingPrice:
    platform: str
    format: str
    creators: int
    median_paise: int


@dataclass(frozen=True)
class CityFigures:
    city: str
    published_creators: int | None
    creators_by_niche: dict[Niche, int | None]
    open_campaigns: int | None
    asking_prices: list[AskingPrice]


def cities(db: Session) -> list[CityCount]:
    """Every city with at least five published creators, largest first."""
    key = func.lower(func.btrim(Creator.city))
    rows = db.execute(
        select(
            func.mode().within_group(func.btrim(Creator.city)),
            func.count(Creator.id),
        )
        .where(*_published_creators())
        .group_by(key)
        .having(func.count(Creator.id) >= MIN_COUNT)
        .order_by(func.count(Creator.id).desc(), key)
    ).all()
    return [CityCount(city=name, published_creators=count) for name, count in rows]


def for_city(db: Session, city: str) -> CityFigures:
    """One city's figures, in four queries."""
    wanted = city.strip().lower()
    in_city = func.lower(func.btrim(Creator.city)) == wanted
    creators = [*_published_creators(), in_city]

    name, total = db.execute(
        select(
            func.mode().within_group(func.btrim(Creator.city)), func.count(Creator.id)
        ).where(*creators)
    ).one()

    # Each creator's own niches: PostgreSQL joins a function in FROM to the
    # row before it (LATERAL). joins_implicitly says so to SQLAlchemy, which
    # otherwise warned of a cartesian product in every test run, and a
    # warning that is always there hides the one that matters.
    niche = func.unnest(Creator.niches).column_valued("niche", joins_implicitly=True)
    by_niche: dict[Niche, int | None] = dict.fromkeys(NICHES, None)
    for found, count in db.execute(
        select(niche, func.count()).select_from(Creator).where(*creators).group_by(niche)
    ):
        if found in by_niche:
            by_niche[found] = _shown(count)

    campaign_city = func.unnest(Campaign.cities).column_valued("c")
    campaigns = db.scalar(
        select(func.count(Campaign.id)).where(
            Campaign.status == "open",
            brand_is_active(Campaign.brand_id),
            exists(
                select(campaign_city).where(
                    func.lower(func.btrim(campaign_city)) == wanted
                )
            ),
        )
    )

    return CityFigures(
        city=name or city.strip(),
        published_creators=_shown(total),
        creators_by_niche=by_niche,
        open_campaigns=_shown(campaigns or 0),
        asking_prices=_asking_prices(db, creators),
    )


def _asking_prices(db: Session, creators: list[ColumnElement[bool]]) -> list[AskingPrice]:
    """The median asking price per platform and format, five creators or more.

    Each creator counts once: their own median in the group first, so one
    creator with five Reel packages cannot outweigh four others (D-056).
    """
    per_creator = (
        select(
            CreatorPackage.platform,
            CreatorPackage.format,
            func.percentile_cont(0.5)
            .within_group(CreatorPackage.price_paise)
            .label("price"),
        )
        .join(Creator, Creator.id == CreatorPackage.creator_id)
        .where(
            *creators,
            Creator.rate_card_public_at.is_not(None),
            CreatorPackage.currency == CURRENCY,
        )
        .group_by(
            CreatorPackage.creator_id, CreatorPackage.platform, CreatorPackage.format
        )
        .subquery()
    )
    rows: list[Row[Any]] = list(
        db.execute(
            select(
                per_creator.c.platform,
                per_creator.c.format,
                func.count(),
                func.percentile_cont(0.5).within_group(per_creator.c.price),
            )
            .group_by(per_creator.c.platform, per_creator.c.format)
            .having(func.count() >= MIN_COUNT)
            .order_by(per_creator.c.platform, per_creator.c.format)
        ).all()
    )
    return [
        AskingPrice(
            platform=platform,
            format=package_format,
            creators=count,
            median_paise=round(median),
        )
        for platform, package_format, count, median in rows
    ]

"""The queries behind a quarterly city rate report (item 84, D-200).

A fixed number of queries whatever the number of cities (the cities, the
asking prices by city, by audience band, and the agreed fees), each
returning raw counts and per-creator figures; the floors and the rounding are
`rate_report_rules`. Which asking prices count is `asking_prices`, the rule
city figures and fair-rate guidance count by.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.taxonomy import CURRENCY
from app.modules.auth.models.creator import Creator
from app.modules.auth.suspension import account_is_active, brand_is_active
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.deliverable_models import MemoDeliverable
from app.modules.deal_memo.models import DealMemo
from app.modules.insights import asking_prices, city_figures_service
from app.modules.insights.rate_guidance_service import AUDIENCE_BANDS
from app.modules.insights.rate_report_rules import AskingCell, Deal, asking_cell

# (key, platform, format): the key a city, or an audience band.
CellKey = tuple[str, str, str]


@dataclass(frozen=True)
class ListedCity:
    key: str  # `lower(btrim(city))`, worked out by the database, as it matches
    name: str  # as most of its creators spell it


@dataclass(frozen=True)
class BandCell:
    cell: AskingCell
    audience_figures_from: date | None


def listed_cities(db: Session) -> list[ListedCity]:
    """The cities city figures list: five or more published creators, largest
    first. One query."""
    return [
        ListedCity(key=row.key, name=row.city) for row in city_figures_service.cities(db)
    ]


def _city_key() -> ColumnElement[str]:
    return func.lower(func.btrim(Creator.city))


def asking_by_city(db: Session, keys: list[str]) -> dict[CellKey, AskingCell]:
    """Asking prices per city, platform and format, as city figures count
    them: published Passports and published rate cards. One query."""
    city = _city_key().label("city_key")
    per_creator = asking_prices.per_creator(
        [Creator.passport_published_at.is_not(None), _city_key().in_(keys)], city
    )
    rows = db.execute(
        select(
            per_creator.c.city_key,
            per_creator.c.platform,
            per_creator.c.format,
            func.count(),
            *_quartiles(per_creator.c.price),
        ).group_by(per_creator.c.city_key, per_creator.c.platform, per_creator.c.format)
    ).all()
    return {
        (key, platform, package_format): asking_cell(count, lower, median, upper)
        for key, platform, package_format, count, lower, median, upper in rows
    }


def asking_by_band(db: Session) -> dict[CellKey, BandCell]:
    """Statewide asking prices per audience band, platform and format, as
    fair-rate guidance counts them (`asking_prices.band_of`: the creator's
    own channel on the package's platform decides the band). One query."""
    band = asking_prices.band_of(AUDIENCE_BANDS).label("band")
    per_creator = asking_prices.per_creator([], band, by_audience=True)
    rows = db.execute(
        select(
            per_creator.c.band,
            per_creator.c.platform,
            per_creator.c.format,
            func.count(),
            *_quartiles(per_creator.c.price),
            func.min(per_creator.c.figures_as_of),
        ).group_by(per_creator.c.band, per_creator.c.platform, per_creator.c.format)
    ).all()
    found: dict[CellKey, BandCell] = {}
    for label, platform, package_format, count, lower, median, upper, oldest in rows:
        cell = asking_cell(count, lower, median, upper)
        found[(label, platform, package_format)] = BandCell(
            cell=cell, audience_figures_from=oldest if cell.creators is not None else None
        )
    return found


def agreed_by_city(
    db: Session, keys: list[str], start: datetime, end: datetime
) -> dict[CellKey, list[Deal]]:
    """Every deal that counts towards agreed fees, by its creator's city and
    its one deliverable's platform and format. One query.

    A deal counts when its memo was accepted in [start, end) and is still
    accepted (never cancelled), it has exactly one deliverable, of quantity
    1, so its fee is for that one piece of work, and neither side's account
    is suspended or deleted (D-061). Barter memos count, with no fee.
    """
    deliverables_of_memo = (
        select(func.count())
        .where(MemoDeliverable.deal_memo_id == DealMemo.id)
        .correlate(DealMemo)
        .scalar_subquery()
    )
    rows = db.execute(
        select(
            _city_key(),
            MemoDeliverable.platform,
            MemoDeliverable.format,
            Application.creator_id,
            Campaign.brand_id,
            DealMemo.fee_amount_paise,
        )
        .select_from(DealMemo)
        .join(MemoDeliverable, MemoDeliverable.deal_memo_id == DealMemo.id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Creator, Creator.id == Application.creator_id)
        .where(
            DealMemo.status == "accepted",
            DealMemo.accepted_at >= start,
            DealMemo.accepted_at < end,
            DealMemo.currency == CURRENCY,
            MemoDeliverable.quantity == 1,
            deliverables_of_memo == 1,
            _city_key().in_(keys),
            account_is_active(Creator.account_id),
            brand_is_active(Campaign.brand_id),
        )
    ).all()
    found: dict[CellKey, list[Deal]] = defaultdict(list)
    for key, platform, package_format, creator_id, brand_id, fee in rows:
        found[(key, platform, package_format)].append(
            Deal(creator=creator_id, brand=brand_id, fee_paise=fee)
        )
    return found


def _quartiles(price: Any) -> list[Any]:
    return [
        func.percentile_cont(fraction).within_group(price)
        for fraction in (0.25, 0.5, 0.75)
    ]

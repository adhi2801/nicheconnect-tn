"""Brands searching for creators.

Matching (D-052) answers "who suits this campaign?". Search answers the
question a brand asks before, or instead of, posting one: "show me food
creators in Madurai with 10,000 to 50,000 Instagram followers who charge
under ₹10,000 for a Reel".

Who is searchable follows decisions already made, not new ones:

- **Only creators who published their Passport.** The same rule as matching
  (D-052) and the public page (D-036): somebody who has not chosen to be
  found is not found.
- **Price filters read every package.** Brands already see all of a
  creator's prices in the media kit (D-055 point 2); the public switch is
  about strangers, and only signed-in brands can search.
- **Follower counts are the creator's own**, never verified, and every
  result says so with the date they were stated (D-042).

Results come newest profile first with the one cursor style every list uses
(backend.md section 2). Three queries a page, whatever the page size: the
page itself, then the channels and the lowest prices for exactly those
creators.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.orm import Session

from app.core.pagination import Slice, build_slice, older_than_cursor
from app.core.taxonomy import CURRENCY
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.schemas import ChannelPlatform


@dataclass(frozen=True)
class CreatorSearch:
    text: str | None = None
    niche: str | None = None
    city: str | None = None
    platform: str | None = None
    min_followers: int | None = None
    max_followers: int | None = None
    max_price_paise: int | None = None
    package_format: str | None = None


@dataclass(frozen=True)
class ChannelFigure:
    platform: ChannelPlatform
    followers: int
    figures_as_of: date


@dataclass(frozen=True)
class SearchResult:
    creator: Creator
    channels: list[ChannelFigure]
    lowest_price_paise: int | None


def _like(text: str) -> str:
    """A LIKE pattern matching `text` literally, anywhere, in any case."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filtered(search: CreatorSearch) -> Select[tuple[Creator]]:
    query = select(Creator).where(Creator.passport_published_at.is_not(None))

    if search.text:
        pattern = _like(search.text.strip())
        query = query.where(
            Creator.handle.ilike(pattern, escape="\\")
            | Creator.display_name.ilike(pattern, escape="\\")
            | Creator.bio.ilike(pattern, escape="\\")
        )
    if search.niche:
        query = query.where(Creator.niches.any_() == search.niche)
    if search.city:
        # Cities are typed by people, so "madurai" finds "Madurai".
        query = query.where(func.lower(Creator.city) == search.city.strip().lower())

    if (
        search.platform is not None
        or search.min_followers is not None
        or search.max_followers is not None
    ):
        # One channel must meet every audience condition at once: 20,000 on
        # Instagram does not count toward a YouTube filter.
        conditions = [CreatorChannel.creator_id == Creator.id]
        if search.platform is not None:
            conditions.append(CreatorChannel.platform == search.platform)
        if search.min_followers is not None:
            conditions.append(CreatorChannel.followers >= search.min_followers)
        if search.max_followers is not None:
            conditions.append(CreatorChannel.followers <= search.max_followers)
        query = query.where(exists().where(and_(*conditions)))

    if search.max_price_paise is not None or search.package_format is not None:
        # Likewise one package: a cheap Story does not make a Reel affordable.
        conditions = [
            CreatorPackage.creator_id == Creator.id,
            CreatorPackage.currency == CURRENCY,
        ]
        if search.max_price_paise is not None:
            conditions.append(CreatorPackage.price_paise <= search.max_price_paise)
        if search.package_format is not None:
            conditions.append(CreatorPackage.format == search.package_format)
        if search.platform is not None:
            conditions.append(CreatorPackage.platform == search.platform)
        query = query.where(exists().where(and_(*conditions)))

    return query


def search_creators(
    db: Session, search: CreatorSearch, *, limit: int, cursor: str | None = None
) -> Slice[SearchResult]:
    """One page of creators matching every filter given, newest first."""
    query = _filtered(search)
    if cursor is not None:
        query = query.where(older_than_cursor(Creator.created_at, Creator.id, cursor))
    creators = list(
        db.scalars(
            query.order_by(Creator.created_at.desc(), Creator.id.desc()).limit(limit + 1)
        ).all()
    )
    page = build_slice(creators, limit, key=lambda c: (c.created_at, c.id))
    ids = [c.id for c in page.rows]

    channels: dict[uuid.UUID, list[ChannelFigure]] = {i: [] for i in ids}
    lowest: dict[uuid.UUID, int] = {}
    if ids:
        for row in db.execute(
            select(
                CreatorChannel.creator_id,
                CreatorChannel.platform,
                CreatorChannel.followers,
                CreatorChannel.figures_as_of,
            )
            .where(CreatorChannel.creator_id.in_(ids))
            .order_by(CreatorChannel.creator_id, CreatorChannel.platform)
        ):
            channels[row.creator_id].append(
                # The CHECK on creator_channel.platform guarantees the value.
                ChannelFigure(row.platform, row.followers, row.figures_as_of)
            )
        price_query = (
            select(CreatorPackage.creator_id, func.min(CreatorPackage.price_paise))
            .where(
                CreatorPackage.creator_id.in_(ids),
                CreatorPackage.currency == CURRENCY,
            )
            .group_by(CreatorPackage.creator_id)
        )
        # "From ₹X" means the cheapest package that answers the question
        # asked: with a format filter, the cheapest of that format.
        if search.package_format is not None:
            price_query = price_query.where(
                CreatorPackage.format == search.package_format
            )
        if search.platform is not None:
            price_query = price_query.where(CreatorPackage.platform == search.platform)
        lowest = {creator_id: price for creator_id, price in db.execute(price_query)}

    return Slice(
        rows=[
            SearchResult(
                creator=c, channels=channels[c.id], lowest_price_paise=lowest.get(c.id)
            )
            for c in page.rows
        ],
        next_cursor=page.next_cursor,
    )

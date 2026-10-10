"""Brands searching for creators, over HTTP. The rules live in `search_service`."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.core.taxonomy import CURRENCY, Niche
from app.db.session import get_db
from app.modules.auth import availability_service as availability
from app.modules.auth import search_service as service
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.auth.exceptions import InvalidSearch
from app.modules.auth.schemas import (
    ChannelPlatform,
    CreatorSearchResultRead,
    PackageFormat,
    SearchChannelRead,
)

READ_LIMIT = "60 per minute"
MAX_FOLLOWERS = 1_000_000_000
MAX_PRICE_PAISE = 10_000_000_000  # ₹10 crore: far above any real package

router = APIRouter(prefix="/api/v1/creators", tags=["creator search"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands can search for creators"),
    422: problem_doc("A filter is not valid, or the filters contradict each other"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _to_read(result: service.SearchResult, today: date) -> CreatorSearchResultRead:
    creator = result.creator
    return CreatorSearchResultRead(
        creator_id=creator.id,
        handle=creator.handle,
        display_name=creator.display_name,
        city=creator.city,
        niches=creator.niches,
        bio=creator.bio,
        member_since=creator.created_at.strftime("%Y-%m"),
        channels=[
            SearchChannelRead(
                platform=c.platform,
                followers=c.followers,
                figures_as_of=c.figures_as_of,
            )
            for c in result.channels
        ],
        from_price_paise=result.lowest_price_paise,
        currency=CURRENCY,
        booked_until=availability.booked_until_shown(creator.booked_until, today),
    )


@router.get(
    "",
    response_model=Page[CreatorSearchResultRead],
    summary="Search for creators",
    description=(
        "Creators who published their Passport, filtered by any combination "
        "of words in their handle, name or bio; niche; city; a platform and an "
        "audience size on it; and a price limit, optionally for one format. "
        "Every audience filter must hold for one channel, and every price "
        "filter for one package. Follower counts are the creator's own "
        "statement, dated, never verified. Newest profiles first; pass "
        "`next_cursor` back as `cursor` for the next page. Each result says "
        "until when the creator is booked, if they are; `available_on` keeps "
        "only creators free that day. Brands only."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def search_creators(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[
        str | None,
        Query(
            min_length=2, max_length=60, description="Words in the handle, name or bio"
        ),
    ] = None,
    niche: Niche | None = None,
    city: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    platform: ChannelPlatform | None = None,
    min_followers: Annotated[int | None, Query(ge=0, le=MAX_FOLLOWERS)] = None,
    max_followers: Annotated[int | None, Query(ge=0, le=MAX_FOLLOWERS)] = None,
    max_price_paise: Annotated[
        int | None, Query(ge=1, le=MAX_PRICE_PAISE, description="In paise: ₹1 is 100")
    ] = None,
    format: Annotated[
        PackageFormat | None, Query(description="Only packages of this format count")
    ] = None,
    available_on: Annotated[
        date | None,
        Query(description="Only creators not booked on this Tamil Nadu day"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
    now: datetime = Depends(get_now),
) -> Page[CreatorSearchResultRead]:
    if (
        min_followers is not None
        and max_followers is not None
        and min_followers > max_followers
    ):
        raise InvalidSearch("min_followers is larger than max_followers.")
    result = service.search_creators(
        db,
        service.CreatorSearch(
            text=q,
            niche=niche,
            city=city,
            platform=platform,
            min_followers=min_followers,
            max_followers=max_followers,
            max_price_paise=max_price_paise,
            package_format=format,
            available_on=available_on,
        ),
        limit=limit,
        cursor=cursor,
    )
    today = india_date(now)
    return Page(
        items=[_to_read(r, today) for r in result.rows], next_cursor=result.next_cursor
    )

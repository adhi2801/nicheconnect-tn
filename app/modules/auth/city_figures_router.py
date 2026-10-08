"""City figures for public pages, readable without logging in (D-078).

Public like the Creator Passport, and written as defensively: hand-built
responses, a cache header and an ETag, and nothing that depends on who is
asking. The rules for what counts are in city_figures_service.py.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import city_figures_service as figures
from app.modules.auth.schemas import (
    AskingPriceRead,
    CityCountRead,
    CityFiguresRead,
    NicheCountRead,
)

# Figures move slowly, and a city page is read far more often than any
# figure on it changes. TTL: 1 hour. Invalidation: the ETag hashes the
# answer itself, so a change shows within the hour at worst (backend.md
# section 6).
CACHE_SECONDS = 3600
PUBLIC_READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/cities", tags=["public"])

City = Annotated[
    str,
    Path(
        min_length=2,
        max_length=60,
        pattern=r"^[A-Za-z][A-Za-z .'-]*$",
        description="A city name as people write it; matched without regard to case",
        examples=["Coimbatore"],
    ),
]

_ERRORS: ResponseDocs = {
    429: problem_doc("Too many requests; see the Retry-After header")
}


def _cached(
    body: BaseModel, response: Response, if_none_match: str | None
) -> Response | None:
    """Set the cache headers; a 304 when the reader already has this answer."""
    etag = '"' + hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:32] + '"'
    headers = {"Cache-Control": f"public, max-age={CACHE_SECONDS}", "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return None


@router.get(
    "",
    response_model=list[CityCountRead],
    summary="Cities with public figures",
    description=(
        "Every city with at least five creators who published their Passport, "
        "largest first: the cities a public page can be made for. Cached for "
        "an hour, with an ETag."
    ),
    responses=_ERRORS,
)
@rate_limit(PUBLIC_READ_LIMIT)
def list_cities(
    request: Request,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Response | list[CityCountRead]:
    """Anyone may call this."""
    found = [
        CityCountRead(city=row.city, published_creators=row.published_creators)
        for row in figures.cities(db)
    ]

    class _All(BaseModel):
        cities: list[CityCountRead]

    return _cached(_All(cities=found), response, if_none_match) or found


@router.get(
    "/{city}/figures",
    response_model=CityFiguresRead,
    summary="A city's public figures",
    description=(
        "Counts and medians for one city: published creators, by niche, open "
        "campaigns, and median asking prices by platform and format. Any figure "
        "resting on fewer than five is `null`, meaning **not enough to say**, "
        "and must not be shown as zero; a city nobody has joined answers the "
        "same way rather than 404. Nothing is built from a deal. Cached for an "
        "hour, with an ETag."
    ),
    responses={**_ERRORS, 422: problem_doc("That is not a city name")},
)
@rate_limit(PUBLIC_READ_LIMIT)
def city_figures(
    request: Request,
    response: Response,
    city: City,
    if_none_match: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Response | CityFiguresRead:
    """Anyone may call this. Nothing here depends on who is asking."""
    found = figures.for_city(db, city)
    body = CityFiguresRead(
        city=found.city,
        min_count=figures.MIN_COUNT,
        published_creators=found.published_creators,
        creators_by_niche=[
            NicheCountRead(niche=niche, creators=count)
            for niche, count in found.creators_by_niche.items()
        ],
        open_campaigns=found.open_campaigns,
        asking_prices=[
            AskingPriceRead(
                platform=price.platform,
                format=price.format,
                creators=price.creators,
                median_paise=price.median_paise,
            )
            for price in found.asking_prices
        ],
    )
    return _cached(body, response, if_none_match) or body

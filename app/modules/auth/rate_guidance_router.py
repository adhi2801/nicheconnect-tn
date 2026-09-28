"""Fair-rate guidance over HTTP (D-056). The rules live in the service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.core.taxonomy import CURRENCY, Niche
from app.db.session import get_db
from app.modules.auth import rate_guidance_service as service
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.schemas import (
    ChannelPlatform,
    NarrowedTo,
    PackageFormat,
    RateGuidanceRead,
)

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1", tags=["rate guidance"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    422: problem_doc("An unknown platform, format or niche, or a bad follower count"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/rate-guidance",
    response_model=RateGuidanceRead,
    summary="What creators like this charge",
    description=(
        "The lower quarter, middle and upper quarter of what creators of this "
        "audience size charge for this format, from rate cards creators have "
        "published. Narrowed to the niche and city when at least five "
        "creators match; otherwise wider, and `narrowed_to` says so. Below "
        "five creators the figures are `null`, meaning **not enough to say**: "
        "never show that as zero. Readable by any signed-in brand or creator."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_rate_guidance(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    platform: ChannelPlatform,
    format: PackageFormat,
    followers: Annotated[
        int,
        Query(ge=0, le=1_000_000_000, description="The audience to compare with"),
    ],
    niche: Niche | None = None,
    city: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
) -> RateGuidanceRead:
    """Any signed-in account: both sides of a deal are better off knowing."""
    guidance = service.for_group(
        db,
        platform=platform,
        package_format=format,
        followers=followers,
        niche=niche,
        city=city,
    )
    return RateGuidanceRead(
        platform=platform,
        format=format,
        audience_band=guidance.audience_band,
        narrowed_to=NarrowedTo(niche=guidance.niche, city=guidance.city),
        source="published_asking_prices",
        creators_counted=guidance.creators_counted,
        lower_quarter_paise=guidance.lower_quarter_paise,
        median_paise=guidance.median_paise,
        upper_quarter_paise=guidance.upper_quarter_paise,
        currency=CURRENCY,
        audience_figures_from=guidance.audience_figures_from,
        as_of=india_date(now),
    )

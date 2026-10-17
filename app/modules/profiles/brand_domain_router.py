"""A brand's domain over HTTP (item 74, D-106). Rules in brand_domain_service.

Only the brand itself, under /me with no id, so no one can reach another
brand's claim. Creators see the verified facts on campaigns and on the
brand's payment record instead.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_domain_service as service
from app.modules.profiles import profile_service as profiles
from app.modules.profiles.schemas import (
    BrandDomainClaim,
    BrandDomainRead,
    to_brand_domain_read,
)

READ_LIMIT = "60 per minute"
# A new claim is a new token; a day's worth is plenty.
CLAIM_LIMIT = "10 per minute;20 per day"
# Each check asks two resolvers about the brand's domain: never a way to
# have us query someone's DNS over and over (trust-and-safety.md rule 2).
CHECK_LIMIT = "5 per minute;10 per day"
PATH = "/api/v1/brands/me/domain"

router = APIRouter(prefix=PATH, tags=["brand domain"], route_class=IdempotentRoute)

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only a brand has a domain"),
    404: problem_doc("No brand profile yet, or no domain claimed"),
    422: problem_doc("A field is not valid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _brand(db: Session, account_id: uuid.UUID) -> Brand:
    return profiles.get_profile(db, Brand, account_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=BrandDomainRead,
    summary="Claim your website's domain",
    description=(
        "Returns a TXT record to add at your DNS host: `record_name` and "
        "`record_value`. Then ask for a check. The token is good for 7 days. "
        "Claiming again, the same domain or another, replaces the claim with a "
        "new token, and a verified domain stops showing until the new one is "
        "found. Creators are shown the domain itself and when it was "
        "registered, never a verdict on the brand."
    ),
    responses={
        **_ERRORS,
        409: problem_doc("Another brand has already verified that domain"),
    },
)
@rate_limit(CLAIM_LIMIT)
def claim_domain(
    request: Request,
    response: Response,
    body: BrandDomainClaim,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BrandDomainRead:
    claimed = service.claim(db, _brand(db, account.id), body.domain, now)
    response.headers["Location"] = PATH
    return to_brand_domain_read(claimed)


@router.get(
    "",
    response_model=BrandDomainRead,
    summary="Your domain claim and its last check",
    description=(
        "The record to publish, and what the last check found. Only you see "
        "this; creators see the domain once it is verified."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_domain(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
) -> BrandDomainRead:
    return to_brand_domain_read(service.get_mine(db, _brand(db, account.id)))


@router.post(
    "/check",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BrandDomainRead,
    summary="Check the TXT record now",
    description=(
        "Accepted at once, and checked within a minute: Cloudflare's and "
        "Google's resolvers must both see the record. Read the claim again for "
        "the result, or see it in `GET /api/v1/me/attention`. A verified "
        "domain is also checked every day; three days in a row without the "
        "record, and it lapses. Limit: 10 a day."
    ),
    responses={
        **_ERRORS,
        409: problem_doc("The claim lapsed, or its token expired: claim again"),
    },
)
@rate_limit(CHECK_LIMIT)
def check_domain(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BrandDomainRead:
    return to_brand_domain_read(service.request_check(db, _brand(db, account.id), now))


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw your domain claim",
    description="Creators stop seeing the domain at once.",
    responses=_ERRORS,
)
@rate_limit(CLAIM_LIMIT)
def withdraw_domain(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    service.withdraw(db, _brand(db, account.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

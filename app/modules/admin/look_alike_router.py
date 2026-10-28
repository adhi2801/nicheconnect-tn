"""Look-alike brand names, for the admins (HTTP; item 75, D-118). Rules: profiles.brand_names."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.admin import look_alike_service as service
from app.modules.admin.schemas import (
    LookAlikeBrandRead,
    LookAlikeListRead,
    NameClearanceIn,
    NameClearanceRead,
)
from app.modules.auth.dependencies import CurrentAdmin, get_now
from app.modules.auth.models.brand import Brand

ADMIN_LIMIT = "60 per minute"

# route_class: an admin's repeated tap clears or withdraws once (D-040).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], route_class=IdempotentRoute)

BrandId = Annotated[uuid.UUID, Path(description="The brand's id")]
_CLEARANCE_ERRORS: ResponseDocs = {
    404: problem_doc("No such brand; also the answer for anyone who is not an admin"),
    409: problem_doc(
        "`brand_name_not_flagged`, `brand_name_already_cleared` or "
        "`brand_name_not_cleared`"
    ),
    422: problem_doc("The note is missing or too short"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _clearance(brand: Brand) -> NameClearanceRead:
    return NameClearanceRead(
        brand_id=brand.id,
        name=brand.name,
        name_cleared=brand.name_cleared == brand.name,
        name_cleared_at=brand.name_cleared_at,
    )


@router.get(
    "/brands/look-alikes",
    response_model=LookAlikeListRead,
    summary="Brands whose names look like a protected brand's",
    description=(
        "Every brand whose name looks like a protected brand's (the curated list, "
        "or a brand here with a verified domain) and has not verified that "
        "brand's domain, or mixes look-alike letters, newest first, at most 100. "
        "Each cannot publish a campaign until it verifies the domain (item 75). "
        "Worked out from the names each time. Limit: 60 requests per minute."
    ),
    responses={
        404: problem_doc(
            "Not found, which is also the answer for anyone who is not an admin"
        ),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(ADMIN_LIMIT)
def list_look_alike_brands(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
) -> LookAlikeListRead:
    found, truncated = service.flagged(db)
    return LookAlikeListRead(
        items=[
            LookAlikeBrandRead(
                brand_id=item.brand_id,
                account_id=item.account_id,
                name=item.name,
                created_at=item.created_at,
                resembles_name=None
                if item.flag.resembles is None
                else item.flag.resembles.name,
                resembles_domain=(
                    None if item.flag.resembles is None else item.flag.resembles.domain
                ),
                mixed_script=item.flag.mixed_script,
            )
            for item in found
        ],
        truncated=truncated,
    )


@router.post(
    "/brands/{brand_id}/name-clearance",
    response_model=NameClearanceRead,
    summary="Clear a brand's look-alike name after review",
    description=(
        "For a genuine brand whose name is close to a protected one and that "
        "cannot verify that brand's domain: after looking at the business "
        "behind it, clear its current name, so it can publish and creators see "
        "no warning. Only that exact name: a rename is held again until looked "
        "at. Written to the admin log with your note. Limit: 60 requests per "
        "minute."
    ),
    responses=_CLEARANCE_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def clear_brand_name(
    request: Request,
    brand_id: BrandId,
    body: NameClearanceIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> NameClearanceRead:
    return _clearance(service.clear_name(db, admin, brand_id, note=body.note, now=now))


@router.post(
    "/brands/{brand_id}/name-clearance/withdraw",
    response_model=NameClearanceRead,
    summary="Withdraw a brand name's clearance",
    description=(
        "Puts the brand's current name back on hold: it cannot publish a new "
        "campaign, and creators see the warning again. Written to the admin log "
        "with your note. Limit: 60 requests per minute."
    ),
    responses=_CLEARANCE_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def withdraw_brand_name_clearance(
    request: Request,
    brand_id: BrandId,
    body: NameClearanceIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> NameClearanceRead:
    return _clearance(
        service.withdraw_clearance(db, admin, brand_id, note=body.note, now=now)
    )

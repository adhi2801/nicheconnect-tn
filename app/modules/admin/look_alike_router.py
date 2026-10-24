"""Look-alike brand names, for the admins (HTTP; item 75, D-118). Rules: profiles.brand_names."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.admin import look_alike_service as service
from app.modules.admin.schemas import LookAlikeBrandRead, LookAlikeListRead
from app.modules.auth.dependencies import CurrentAdmin

ADMIN_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


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

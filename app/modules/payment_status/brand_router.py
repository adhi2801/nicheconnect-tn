"""A brand's payment record, for a creator deciding whether to work with them.

Signed in, but any account: a creator needs this *before* applying, which is
the only moment it can change a decision. Showing it only after a deal is
agreed would make it decoration.

It is not public. Publishing a business's payment failures to the open
internet is a different question from showing them to the people being asked
to take the risk, and it cannot be undone once done. That decision is a
founder's, and until it is made this stays behind a login.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import problem_doc
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.payment_status import reliability
from app.modules.payment_status.schemas import BrandReliabilityRead, to_reliability_read

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/brands", tags=["reliability"])

BrandId = Annotated[uuid.UUID, Path(description="The brand's id")]


@router.get(
    "/{brand_id}/reliability",
    response_model=BrandReliabilityRead,
    summary="How this brand pays",
    description=(
        "A brand's payment record, built from what happened rather than from "
        "reviews. The figures are withheld until three deals have completed, "
        "because two out of two is not evidence of anything; `null` there "
        "means **not enough to say**, and must not be shown as zero. "
        "`currently_overdue` is always reported, including for a brand with "
        "no completed deals, so a new account can never hide a creator who "
        "is still waiting to be paid."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        404: problem_doc("No such brand"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(READ_LIMIT)
def read_brand_reliability(
    request: Request,
    brand_id: BrandId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BrandReliabilityRead:
    """Any signed-in account may read any brand's record."""
    if not reliability.brand_exists(db, brand_id):
        raise ProfileNotFound()
    record = reliability.for_brand(db, brand_id, india_date(now))
    return to_reliability_read(record)

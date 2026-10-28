"""Typical response times: how long each side usually takes to answer (D-077).

Read with the same access as the record each sits beside: a brand's by any
signed-in account, like how it pays; a creator's by any brand or the
creator themself, like how it delivers.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount
from app.modules.auth.exceptions import ProfileNotFound, RoleNotAllowed
from app.modules.deal_memo import delivery_record, response_times
from app.modules.deal_memo.schemas import (
    BrandResponseTimesRead,
    CreatorResponseTimesRead,
    to_response_time_read,
)
from app.modules.payment_status import reliability

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1", tags=["reliability"])

_MEANING = (
    "Measured from the deal record, never estimated. `median_hours` is null "
    "until there are five examples, meaning **not enough to say**, and must "
    "not be shown as zero; `examples` is always returned."
)
_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    422: problem_doc("The id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/brands/{brand_id}/response-times",
    response_model=BrandResponseTimesRead,
    summary="How long this brand takes to decide on work",
    description=(
        "From work submitted to approved or sent back; an approval by the "
        "clock counts at the moment the review window ended. " + _MEANING
    ),
    responses={**_ERRORS, 404: problem_doc("No such brand")},
)
@rate_limit(READ_LIMIT)
def brand_response_times(
    request: Request,
    brand_id: Annotated[uuid.UUID, Path(description="The brand's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> BrandResponseTimesRead:
    """Any signed-in account, as for the brand's payment record."""
    if not reliability.brand_exists(db, brand_id):
        raise ProfileNotFound()
    found = response_times.for_brand(db, brand_id)
    return BrandResponseTimesRead(
        brand_id=brand_id, work_reviewed=to_response_time_read(found.work_reviewed)
    )


@router.get(
    "/creators/{creator_id}/response-times",
    response_model=CreatorResponseTimesRead,
    summary="How long this creator takes to answer",
    description=(
        "From a memo sent to its answer (accepted, declined or a change "
        "requested), and from a payment marked as sent to the creator "
        "confirming it arrived. " + _MEANING
    ),
    responses={
        **_ERRORS,
        403: problem_doc("Only brands, or the creator themself, can read this"),
        404: problem_doc("No such creator"),
    },
)
@rate_limit(READ_LIMIT)
def creator_response_times(
    request: Request,
    creator_id: Annotated[uuid.UUID, Path(description="The creator's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> CreatorResponseTimesRead:
    """Any brand, or the creator themself, as for the delivery record."""
    # Checked before existence, so another creator learns nothing.
    if (
        account.role != "brand"
        and delivery_record.creator_id_for_account(db, account.id) != creator_id
    ):
        raise RoleNotAllowed()
    if not delivery_record.creator_exists(db, creator_id):
        raise ProfileNotFound()
    found = response_times.for_creator(db, creator_id)
    return CreatorResponseTimesRead(
        creator_id=creator_id,
        memo_answered=to_response_time_read(found.memo_answered),
        payment_confirmed=to_response_time_read(found.payment_confirmed),
    )

"""A creator's delivery record, for a brand deciding whether to work with them.

The mirror of a brand's payment record (D-034, D-038). A brand needs it
*before* shortlisting or accepting, which is the only moment it can change a
decision, so any brand may read any creator's record.

Narrower than the brand record, on purpose: a creator is a person, not a
business, so other creators cannot read it. The creator can always read
their own, to see exactly what brands see. It is not public; whether it
ever should be is a founder's decision, as it is for the brand record.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import ProfileNotFound, RoleNotAllowed
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.schemas import CreatorDeliveryRead, to_delivery_read

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/creators", tags=["reliability"])

CreatorId = Annotated[uuid.UUID, Path(description="The creator's id")]

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands, or the creator themself, can read this"),
    404: problem_doc("No such creator"),
    422: problem_doc("The creator id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{creator_id}/delivery-record",
    response_model=CreatorDeliveryRead,
    summary="How this creator delivers",
    description=(
        "A creator's delivery record, built from what happened rather than "
        "from reviews: deals delivered, deals not delivered, and whether the "
        "work arrived by the agreed date. The shares are withheld until three "
        "deals have completed; `null` there means **not enough to say**, and "
        "must not be shown as zero. `currently_overdue` is always reported, "
        "so a new account can never hide work a brand is still waiting for. "
        "Barter deals are counted separately and never scored."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_delivery_record(
    request: Request,
    creator_id: CreatorId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> CreatorDeliveryRead:
    """Any brand, or the creator themself."""
    # Checked before existence, so another creator learns nothing, not even
    # whether the id belongs to anybody.
    if (
        account.role != "brand"
        and delivery_record.creator_id_for_account(db, account.id) != creator_id
    ):
        raise RoleNotAllowed()
    if not delivery_record.creator_exists(db, creator_id):
        raise ProfileNotFound()
    return to_delivery_read(delivery_record.for_creator(db, creator_id, now))

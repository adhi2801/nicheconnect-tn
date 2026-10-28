"""A person's own takedowns over HTTP (item 52). The rules: takedown_service."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount
from app.modules.safety import takedown_service as service
from app.modules.safety.schemas import TakedownRead
from app.modules.safety.takedown_models import Takedown

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["takedowns"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    422: problem_doc("A query parameter or the cursor is invalid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(takedown: Takedown) -> TakedownRead:
    """Field by field: never the admins, their notes, or the order's arrival."""
    return TakedownRead(
        id=takedown.id,
        subject_kind=takedown.subject_kind,
        subject_id=takedown.subject_id,
        basis=takedown.basis,
        reference_sealed=takedown.reference_sealed,
        withheld_at=takedown.withheld_at,
        lifted_at=takedown.lifted_at,
        **service.order_details(takedown),
    )


@router.get(
    "/takedowns",
    response_model=Page[TakedownRead],
    summary="What of mine is withheld",
    description=(
        "Your creator profile, brand or campaigns withheld for legal reasons, "
        "newest first, including those since lifted (item 52). While one is "
        "withheld, everyone else gets 451 for it and it leaves search, matches "
        "and discovery; you still see it, and deals already agreed carry on. "
        "Nothing new can start from it until it is lifted. A sealed order's "
        "details are null."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def list_my_takedowns(
    request: Request,
    account: CurrentAccount,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> Page[TakedownRead]:
    result = service.list_mine(db, account, limit=limit, cursor=cursor)
    return Page[TakedownRead](
        items=[_read(t) for t in result.rows], next_cursor=result.next_cursor
    )

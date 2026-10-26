"""More like the creators who delivered for you (HTTP, item 65, D-133)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.campaigns.service import get_brand_for_account
from app.modules.deal_memo.schemas import to_delivery_read
from app.modules.matching import search_service
from app.modules.matching import similar_service as service
from app.modules.matching.schemas import (
    SimilarAnchorRead,
    SimilarCreatorRead,
    SimilarPageRead,
)

# It reads creators' facts as search does: search's ceiling, so it is never
# a way round it (trust-and-safety.md rule 2).
SIMILAR_LIMIT = "30 per minute;600 per day"
DEFAULT_SIMILAR = 10
MAX_SIMILAR = 50

router = APIRouter(prefix="/api/v1/creators", tags=["creator search"])

Limit = Annotated[int, Query(ge=1, le=MAX_SIMILAR, description="Creators per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]

_RESPONSES: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands are shown creators like their own"),
    422: problem_doc("A query parameter or the cursor is invalid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/like-my-best",
    response_model=SimilarPageRead,
    summary="Creators like the ones who delivered for you",
    description=(
        "Ranked by how close each creator's public profile is to those of the "
        "creators who finished a deal with you: paid and confirmed, or barter "
        "with the work approved. Each result names which of them it is most like "
        "and carries its own delivery record. Only creators you could find in "
        "search today, never one you have already agreed a deal with. `based_on` "
        "is how many it rests on; with none yet the list is empty. Pass "
        "`next_cursor` back as `cursor` for more."
    ),
    responses=_RESPONSES,
)
@rate_limit(SIMILAR_LIMIT)
def like_my_best(
    request: Request,
    account: CurrentBrand,
    limit: Limit = DEFAULT_SIMILAR,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> SimilarPageRead:
    brand = get_brand_for_account(db, account.id)
    result = service.page(db, brand, now, limit=limit, cursor=cursor)
    today = india_date(now)
    return SimilarPageRead(
        based_on=result.based_on,
        items=[
            SimilarCreatorRead(
                **search_service.to_read(row.result, today).model_dump(),
                similarity=row.similarity,
                closest_to=SimilarAnchorRead(
                    creator_id=row.closest_to.creator_id, handle=row.closest_to.handle
                ),
                delivery=to_delivery_read(row.delivery),
            )
            for row in result.rows
        ],
        next_cursor=result.next_cursor,
    )

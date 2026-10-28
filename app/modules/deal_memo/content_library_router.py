"""A brand's content library (HTTP, item 70, D-132). The rules: content_library_service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns.dependencies import CurrentBrandProfile
from app.modules.deal_memo import content_library_service as service
from app.modules.deal_memo.schemas import ContentItemRead, RightsState

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/brands/me/content", tags=["deal memos"])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Posts per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
State = Annotated[
    RightsState | None,
    Query(description="Only posts whose usage window stands so; any when left out"),
]

_RESPONSES: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands keep a content library"),
    422: problem_doc("A query parameter or the cursor is invalid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "",
    response_model=Page[ContentItemRead],
    summary="My content library",
    description=(
        "Every post approved on your deals, latest approved first, each with the "
        "days of use its accepted memo states and the day they end, counted from "
        "the day the work was approved. `rights_state` is `active`, `lapsing` "
        "within 30 days, `lapsed`, or `not_agreed` when the memo states none. "
        "These are the memo's terms, not a ruling on what the law allows. Pass "
        "`next_cursor` back as `cursor` for more."
    ),
    responses=_RESPONSES,
)
@rate_limit(READ_LIMIT)
def my_content(
    request: Request,
    brand: CurrentBrandProfile,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    rights_state: State = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Page[ContentItemRead]:
    result = service.page(db, brand, now, limit=limit, cursor=cursor, state=rights_state)
    return Page[ContentItemRead](
        items=[
            ContentItemRead(
                proof_id=item.proof.id,
                deal_memo_id=item.memo.id,
                campaign_id=item.campaign_id,
                campaign_title=item.campaign_title,
                creator_id=item.creator_id,
                creator_handle=item.creator_handle,
                format=item.proof.format,
                content_url=item.proof.content_url,
                approved_at=item.proof.approved_at,
                auto_approved=item.proof.auto_approved,
                content_removed_on=item.proof.content_removed_on,
                usage_rights_days=item.memo.usage_rights_days,
                rights_until=item.rights_until,
                rights_state=item.rights_state,
            )
            for item in result.rows
        ],
        next_cursor=result.next_cursor,
    )

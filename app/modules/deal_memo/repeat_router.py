"""Work together again: `POST /deal-memos/{memo_id}/repeat` (D-084)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns.dependencies import CurrentBrandProfile
from app.modules.campaigns.schemas import ApplicationRead, RepeatCreate
from app.modules.deal_memo import repeat_service
from app.modules.deal_memo.dependencies import BrandMemo

WRITE_LIMIT = "30 per minute"
# A ceiling per day as well as per minute (trust-and-safety.md rule 2, item 58):
# a per-minute limit stops a script, not a person spamming by hand all day.
REPEAT_LIMIT = "30 per minute;100 per day"

router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["deal memos"], route_class=IdempotentRoute
)


@router.post(
    "/{memo_id}/repeat",
    status_code=status.HTTP_201_CREATED,
    response_model=ApplicationRead,
    summary="Work together again",
    description=(
        "Invites the creator of this deal to another of the signed-in brand's "
        "open campaigns, as a repeat of it. The deal must be one both sides "
        "agreed and nobody cancelled. When the creator accepts, the new deal "
        "memo is drafted with this deal's terms (everything but the due date, "
        "which the brand sets before sending). Answers with the invitation."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc("Only a brand may repeat a deal"),
        404: problem_doc("No such deal or campaign, or it is not yours"),
        409: problem_doc(
            "The brand profile is missing, the deal was not agreed or was "
            "cancelled, its fee does not suit the campaign's type, the campaign "
            "is not open, the creator is already on it, or it has 25 "
            "invitations waiting"
        ),
        422: problem_doc("A field is missing or invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(REPEAT_LIMIT)
def repeat_deal(
    request: Request,
    response: Response,
    body: RepeatCreate,
    memo: BrandMemo,
    brand: CurrentBrandProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    invitation = repeat_service.repeat_deal(
        db, memo, brand, body.campaign_id, body.note, now
    )
    response.headers["Location"] = f"/api/v1/applications/{invitation.id}"
    return ApplicationRead.model_validate(invitation)

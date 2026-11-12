"""The pre-deal check over HTTP (item 133, D-182). The rules live in `check_service`."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import check_service
from app.modules.deal_memo.check_schemas import DealCheckRead, to_check_read
from app.modules.deal_memo.dependencies import MemoId, party_memo

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/deal-memos", tags=["reliability"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    404: problem_doc(
        "No such memo, not yours, a draft read by the creator, or a block "
        "stands between the two of you"
    ),
    422: problem_doc("The memo id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{memo_id}/check",
    response_model=DealCheckRead,
    summary="Facts about the other side, before the deal is agreed",
    description=(
        "What our records hold about the other side of this deal, on one "
        "screen. The creator reads about the brand: its payment record, "
        "verified domain and look-alike name flag, how long it takes to "
        "decide on work, the deals that went to a dispute and how each "
        "ended, and when its account was created. The brand reads about the "
        "creator: the delivery record, how long the creator takes to answer, "
        "the deals that went to a dispute and how each ended, when the "
        "account was created, and each channel's figures as the creator's "
        "own claim beside any count a connected platform reported. Both read "
        "whether this is their first deal together and how many earlier "
        "deals between them finished. Facts with the number each rests on; "
        "every share and median is `null` below its floor, meaning **not "
        "enough to say**, never 0. Never a score, and it never stops anyone "
        "agreeing. The brand's team from the draft on; the creator once the "
        "memo is sent."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_deal_check(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DealCheckRead:
    """Either party. Anyone else gets 404, so ids cannot be walked."""
    memo = party_memo(db, request, memo_id, account)
    return to_check_read(check_service.check(db, memo, account.role, now))

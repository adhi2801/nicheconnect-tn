"""Feedback on a finished deal (HTTP, item 77, D-136). The rules: feedback_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, Slice
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import ProfileNotFound, RoleNotAllowed
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo import feedback_service as service
from app.modules.deal_memo.dependencies import MemoId, party_memo
from app.modules.deal_memo.feedback_service import FeedbackView, Figures, NoteAbout
from app.modules.deal_memo.schemas import (
    DealFeedbackRead,
    FeedbackFiguresRead,
    FeedbackIn,
    FeedbackNoteRead,
    FeedbackRead,
)
from app.modules.payment_status import reliability

READ_LIMIT = "60 per minute"
# Feedback reaches the other side (trust-and-safety.md rule 2).
WRITE_LIMIT = "10 per minute;50 per day"

router = APIRouter(prefix="/api/v1", tags=["deal memos"], route_class=IdempotentRoute)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Notes per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
CreatorId = Annotated[uuid.UUID, Path(description="The creator's id")]
BrandId = Annotated[uuid.UUID, Path(description="The brand's id")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_DEAL: ResponseDocs = {**_COMMON, 404: problem_doc("No such deal, or it is not yours")}


def _view(found: FeedbackView) -> DealFeedbackRead:
    return DealFeedbackRead(
        window_ends_at=found.window_ends_at,
        open=found.open,
        mine=FeedbackRead.model_validate(found.mine) if found.mine else None,
        theirs=FeedbackRead.model_validate(found.theirs) if found.theirs else None,
    )


def _figures(found: Figures) -> FeedbackFiguresRead:
    return FeedbackFiguresRead(
        answers=found.answers,
        counterparties=found.counterparties,
        brief=found.brief,
        reliability=found.reliability,
        easy=found.easy,
    )


@router.get(
    "/deal-memos/{memo_id}/feedback",
    response_model=DealFeedbackRead,
    summary="A finished deal's feedback",
    description=(
        "Your own answer, and the other side's once you have both answered or the "
        "14 days have passed. The brand and the creator of this deal only."
    ),
    responses=_DEAL,
)
@rate_limit(READ_LIMIT)
def read_feedback(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DealFeedbackRead:
    memo = party_memo(db, request, memo_id, account)
    return _view(service.view(db, memo, account.role, now))


@router.post(
    "/deal-memos/{memo_id}/feedback",
    status_code=status.HTTP_201_CREATED,
    response_model=DealFeedbackRead,
    summary="Give feedback on a finished deal",
    description=(
        "Three scores, 1 to 5, and an optional note, once, within 14 days of the "
        "deal finishing (paid and confirmed, or its barter work approved). It can "
        "never be changed. Neither side sees the other's until both have answered "
        "or the 14 days pass, so nobody answers to retaliate. The other side is "
        "told an answer exists, never what it says."
    ),
    responses={
        **_DEAL,
        409: problem_doc(
            "`feedback_closed`: not finished, already given, or the 14 days passed"
        ),
        422: problem_doc("A score outside 1 to 5, or a note too long"),
    },
)
@rate_limit(WRITE_LIMIT)
def give_feedback(
    request: Request,
    response: Response,
    memo_id: MemoId,
    body: FeedbackIn,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DealFeedbackRead:
    memo = party_memo(db, request, memo_id, account)
    scores = {"brief": body.brief, "reliability": body.reliability, "easy": body.easy}
    service.give(db, memo, account.role, scores, body.note, now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}/feedback"
    return _view(service.view(db, memo, account.role, now))


def _creator_readable(
    db: Session, account_id: uuid.UUID, role: str, creator_id: uuid.UUID
) -> None:
    """Any brand, or the creator themself, as their delivery record (D-038)."""
    if (
        role != "brand"
        and delivery_record.creator_id_for_account(db, account_id) != creator_id
    ):
        raise RoleNotAllowed()
    if not delivery_record.creator_exists(db, creator_id):
        raise ProfileNotFound()


@router.get(
    "/creators/{creator_id}/feedback",
    response_model=FeedbackFiguresRead,
    summary="What brands said about a creator",
    description=(
        "Averages of the revealed answers brands gave after finished deals, with "
        "how many and from how many brands. Null below three answers. Show beside "
        "the delivery record, never instead. Any brand, or the creator themself."
    ),
    responses={
        **_COMMON,
        403: problem_doc("Another creator"),
        404: problem_doc("No such creator"),
    },
)
@rate_limit(READ_LIMIT)
def creator_feedback(
    request: Request,
    creator_id: CreatorId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FeedbackFiguresRead:
    _creator_readable(db, account.id, account.role, creator_id)
    return _figures(service.figures(db, "creator", creator_id, now))


@router.get(
    "/creators/{creator_id}/feedback/notes",
    response_model=Page[FeedbackNoteRead],
    summary="Brands' notes about a creator",
    description="Revealed notes, newest first, each beside the creator's own words on that deal.",
    responses={
        **_COMMON,
        403: problem_doc("Another creator"),
        404: problem_doc("No such creator"),
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@rate_limit(READ_LIMIT)
def creator_feedback_notes(
    request: Request,
    creator_id: CreatorId,
    account: CurrentAccount,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Page[FeedbackNoteRead]:
    _creator_readable(db, account.id, account.role, creator_id)
    return _notes(
        service.notes(db, "creator", creator_id, now, limit=limit, cursor=cursor)
    )


@router.get(
    "/brands/{brand_id}/feedback",
    response_model=FeedbackFiguresRead,
    summary="What creators said about a brand",
    description=(
        "Averages of the revealed answers creators gave after finished deals, with "
        "how many and from how many creators. Null below three answers. Show beside "
        "the payment record, never instead. Any signed-in account."
    ),
    responses={**_COMMON, 404: problem_doc("No such brand")},
)
@rate_limit(READ_LIMIT)
def brand_feedback(
    request: Request,
    brand_id: BrandId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> FeedbackFiguresRead:
    if not reliability.brand_exists(db, brand_id):
        raise ProfileNotFound()
    return _figures(service.figures(db, "brand", brand_id, now))


@router.get(
    "/brands/{brand_id}/feedback/notes",
    response_model=Page[FeedbackNoteRead],
    summary="Creators' notes about a brand",
    description="Revealed notes, newest first, each beside the brand's own words on that deal.",
    responses={
        **_COMMON,
        404: problem_doc("No such brand"),
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@rate_limit(READ_LIMIT)
def brand_feedback_notes(
    request: Request,
    brand_id: BrandId,
    account: CurrentAccount,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Page[FeedbackNoteRead]:
    if not reliability.brand_exists(db, brand_id):
        raise ProfileNotFound()
    return _notes(service.notes(db, "brand", brand_id, now, limit=limit, cursor=cursor))


def _notes(found: Slice[NoteAbout]) -> Page[FeedbackNoteRead]:
    return Page[FeedbackNoteRead](
        items=[
            FeedbackNoteRead(
                note=n.feedback.note or "",
                reply=n.reply,
                author_side=n.feedback.author_side,
                created_at=n.feedback.created_at,
            )
            for n in found.rows
        ],
        next_cursor=found.next_cursor,
    )

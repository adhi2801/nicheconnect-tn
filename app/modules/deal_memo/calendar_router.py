"""A deal's agreed dates as a calendar file (item 69, D-102). Rules in calendar_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import calendar_ics, calendar_service
from app.modules.deal_memo.dependencies import party_memo

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/deal-memos", tags=["deal memos"])


@router.get(
    "/{memo_id}/calendar.ics",
    response_class=Response,
    summary="The deal's agreed dates, as a calendar file",
    description=(
        "An iCalendar file (RFC 5545) to add to any phone or desktop calendar: "
        "the content due date (moved by the days the brand held a draft), "
        "the moment a waiting draft or submitted work approves itself, and the "
        "payment due date while unconfirmed, each with a "
        "reminder a day before. Only an accepted deal has dates; any other "
        "gives an empty calendar. Adding it again updates the same events. "
        "The brand and the creator of this deal only."
    ),
    responses={
        200: {
            "description": "The calendar file",
            "content": {"text/calendar": {"schema": {"type": "string"}}},
        },
        401: problem_doc("No access token, or it is invalid or expired"),
        404: problem_doc("No such memo, or not yours"),
        422: problem_doc("The memo id is not a valid id"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(READ_LIMIT)
def deal_calendar(
    request: Request,
    memo_id: Annotated[uuid.UUID, Path(description="The memo's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    """Either party. Anyone else gets 404, so ids cannot be walked."""
    memo = party_memo(db, request, memo_id, account)
    name, events = calendar_service.deal_dates(db, memo, now)
    return Response(
        content=calendar_ics.calendar(name, events, stamp=now),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="deal-{memo.id}.ics"',
            # Personal: never kept by a shared cache.
            "Cache-Control": "private, no-store",
        },
    )

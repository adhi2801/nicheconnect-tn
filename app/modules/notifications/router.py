"""Notification endpoints: what happened, for the signed-in account (D-023)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.notifications import service
from app.modules.notifications.exceptions import NotificationNotFound
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import MarkedRead, NotificationRead, UnreadCount

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _own_notification(
    notification_id: Annotated[uuid.UUID, Path(description="The notification's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> Notification:
    """A notification belonging to the signed-in account, else 404."""
    notification = db.scalars(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.account_id == account.id,
        )
    ).first()
    if notification is None:
        raise NotificationNotFound()
    return notification


OwnNotification = Annotated[Notification, Depends(_own_notification)]


@router.get(
    "",
    response_model=Page[NotificationRead],
    summary="List my notifications",
    description=(
        "The signed-in account's notifications, newest first. `unread_only=true` "
        "returns just the ones not yet read."
    ),
    responses={
        **_COMMON_ERRORS,
        422: problem_doc("A query parameter or cursor is invalid"),
    },
)
@limiter.limit(READ_LIMIT)
def list_notifications(
    request: Request,
    account: CurrentAccount,
    unread_only: Annotated[bool, Query(description="Only unread ones")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(description="From a previous page")] = None,
    db: Session = Depends(get_db),
) -> Page[NotificationRead]:
    result = service.list_for_account(
        db, account.id, limit=limit, cursor=cursor, unread_only=unread_only
    )
    return Page[NotificationRead](
        items=[NotificationRead.model_validate(row) for row in result.rows],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCount,
    summary="How many are unread",
    description="The number for the badge. Cheap: it reads an index of unread rows only.",
    responses=_COMMON_ERRORS,
)
@limiter.limit(READ_LIMIT)
def count_unread(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
) -> UnreadCount:
    return UnreadCount(unread=service.unread_count(db, account.id))


@router.post(
    "/{notification_id}/read",
    response_model=NotificationRead,
    summary="Mark one as read",
    description="Marking an already-read notification again keeps the first time.",
    responses={**_COMMON_ERRORS, 404: problem_doc("No such notification, or not yours")},
)
@limiter.limit(WRITE_LIMIT)
def mark_read(
    request: Request,
    notification: OwnNotification,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> NotificationRead:
    return NotificationRead.model_validate(service.mark_read(db, notification, now))


@router.post(
    "/read-all",
    response_model=MarkedRead,
    summary="Mark everything as read",
    description="Clears the badge. Returns how many changed from unread.",
    responses=_COMMON_ERRORS,
)
@limiter.limit(WRITE_LIMIT)
def mark_all_read(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> MarkedRead:
    return MarkedRead(marked_read=service.mark_all_read(db, account.id, now))

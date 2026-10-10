"""My notification preferences: read them, or replace them (D-079).

Only the person themself: there is no id in the path, so nobody can reach
anyone else's.
"""

from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.notifications import preference_service as preferences
from app.modules.notifications.preference_models import URGENT_TYPES
from app.modules.notifications.schemas import (
    NotificationPreferencesIn,
    NotificationPreferencesRead,
)

READ_LIMIT = "60 per minute"
WRITE_LIMIT = "30 per minute"

router = APIRouter(prefix="/api/v1/me/notification-preferences", tags=["notifications"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(found: preferences.Preferences) -> NotificationPreferencesRead:
    def clock(moment: time | None) -> str | None:
        return None if moment is None else moment.strftime("%H:%M")

    return NotificationPreferencesRead(
        quiet_from=clock(found.quiet_from),
        quiet_until=clock(found.quiet_until),
        digest=found.digest,
        digest_hour=found.digest_hour,
        muted_types=list(found.muted_types),
        always_sent=list(URGENT_TYPES),
        is_default=found.saved_at is None,
        saved_at=found.saved_at,
    )


@router.get(
    "",
    response_model=NotificationPreferencesRead,
    summary="Read my notification preferences",
    description=(
        "The defaults until saved: quiet hours 22:00 to 08:00 Tamil Nadu time, "
        "digest off, nothing muted. They govern delivery outside the app only; "
        "the in-app list keeps everything. `always_sent` lists the types that "
        "arrive at once whatever is set."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_preferences(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> NotificationPreferencesRead:
    return _read(preferences.get(db, account.id))


@router.put(
    "",
    response_model=NotificationPreferencesRead,
    summary="Replace my notification preferences",
    description=(
        "Saves the whole set, so sending the same body twice is harmless. "
        "Urgent types (those in `always_sent`) cannot be muted."
    ),
    responses={
        **_ERRORS,
        422: problem_doc("A field is invalid, or an urgent type was muted"),
    },
)
@rate_limit(WRITE_LIMIT)
def save_preferences(
    request: Request,
    body: NotificationPreferencesIn,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> NotificationPreferencesRead:
    return _read(
        preferences.save(
            db,
            account.id,
            quiet_from=body.quiet_from,
            quiet_until=body.quiet_until,
            digest=body.digest,
            digest_hour=body.digest_hour,
            muted_types=list(body.muted_types),
            now=now,
        )
    )

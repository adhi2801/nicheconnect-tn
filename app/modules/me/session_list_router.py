"""Where you are logged in, and ending one session (HTTP; item 81, D-114).

The rules and the threat model: session_service and auth.sessions.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import (
    CurrentAccount,
    CurrentSessionId,
    StepUpCode,
    get_now,
)
from app.modules.me import session_service as service
from app.modules.me.session_schemas import SessionRead

READ_LIMIT = "60 per minute"
# As for the other session routes (security.md section 5); a code from the
# phone stands behind every session but this one, with the phone's caps.
END_LIMIT = "30 per minute"

# route_class: a repeated acknowledgement answers as the first did (D-040).
router = APIRouter(prefix="/api/v1/me", tags=["auth"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/sessions",
    response_model=Page[SessionRead],
    summary="Where I am logged in",
    description=(
        "Every session of yours that can still renew itself, the latest sign-in "
        "first, with what each app said it is, when and how it signed in, and "
        "when it was last active. `is_current` marks the one asking. A label is "
        "whatever the app sent at sign-in, never checked: show it beside the "
        "sign-in time and method, which no app can choose. No address or "
        "location is kept. Paginated: `limit` (default 20, at most 100) and "
        "`cursor`. Limit: 60 requests per minute."
    ),
    responses={
        **_COMMON,
        422: problem_doc("`limit` is out of range, or `cursor` is not one of ours"),
    },
)
@rate_limit(READ_LIMIT)
def list_my_sessions(
    request: Request,
    account: CurrentAccount,
    current_session_id: CurrentSessionId,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(description="From a previous page")] = None,
) -> Page[SessionRead]:
    page = service.list_mine(db, account, now, limit=limit, cursor=cursor)
    return Page(
        items=[
            SessionRead(
                id=found.id,
                platform=found.platform,
                label=found.label,
                signed_in_at=found.signed_in_at,
                last_active_at=found.last_active_at,
                expires_at=found.expires_at,
                signed_in_with=found.signed_in_with,
                is_current=found.id == current_session_id,
                sign_in_acknowledged_at=found.acknowledged_at,
            )
            for found in page.rows
        ],
        next_cursor=page.next_cursor,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End one session",
    description=(
        "Logs that session out at once: its access token stops working on its "
        "next request, and it can no longer renew. Ending **this** session "
        "needs nothing more; it is logging out. Ending any **other** needs a "
        "code: ask at `POST /api/v1/me/step-up` with `end_session` and this "
        "session's id, then send it in the `Step-Up-Code` header; you are then "
        "told in the app. That way someone holding a stolen session cannot "
        "throw you out. To stop push notifications to this phone too, log out "
        "with `POST /api/v1/auth/logout` and its push token instead. Limit: 30 "
        "requests per minute."
    ),
    responses={
        204: {"description": "The session has ended"},
        400: problem_doc("The code is wrong, expired, used, or for another change"),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`: "
            "no code was sent for another session"
        ),
        404: problem_doc(
            "`session_not_found`: no live session of yours has this id (another "
            "account's reads the same, as does one already ended)"
        ),
        422: problem_doc("The id or the code is malformed"),
        429: problem_doc(
            "Too many requests, or too many wrong codes for your phone; see the "
            "Retry-After header"
        ),
    },
)
@rate_limit(END_LIMIT)
def end_my_session(
    request: Request,
    session_id: uuid.UUID,
    account: CurrentAccount,
    current_session_id: CurrentSessionId,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> Response:
    service.end_one(db, account, session_id, current_session_id, step_up_code, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/acknowledge",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Say a sign-in was yours",
    description=(
        "Takes a `new_sign_in` off your attention list once you know it was you, "
        "for example your new laptop. Only from a device that was signed in "
        "**before** that sign-in: whoever signed in last can never vouch for "
        "themselves, so a sign-in you did not make always stays in front of "
        "you. The session stays listed and can still be ended. Limit: 30 "
        "requests per minute."
    ),
    responses={
        204: {"description": "The sign-in is acknowledged"},
        401: problem_doc("No access token, or it is invalid or expired"),
        404: problem_doc("`session_not_found`: no live session of yours has this id"),
        409: problem_doc(
            "`acknowledge_from_an_earlier_session`: this device signed in after "
            "that one, or is that one"
        ),
        422: problem_doc("The id is malformed"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(END_LIMIT)
def acknowledge_sign_in(
    request: Request,
    session_id: uuid.UUID,
    account: CurrentAccount,
    current_session_id: CurrentSessionId,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    service.acknowledge(db, account, session_id, current_session_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

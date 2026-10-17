"""Logging out of every device (HTTP). The rules: session_service.

The path stays under /api/v1/auth, where clients have always found it; the
route lives in `me` only so the owner can be told (D-099).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, StepUpCode, get_now
from app.modules.auth.schemas import LoggedOutAll
from app.modules.me import session_service

# As for the other session routes, refresh and logout (security.md section 5).
SESSION_LIMIT = "30 per minute"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/logout-all",
    response_model=LoggedOutAll,
    summary="Log out of every device",
    description=(
        "Ends every session of the signed-in account, on all devices, and stops "
        "push notifications to all of them. Needs a valid access token and "
        "**a code**: ask for one at `POST /api/v1/me/step-up` with "
        "`log_out_everywhere`, then send it in the `Step-Up-Code` header. You "
        "are told in the app when you next log in. Limit: 30 requests per "
        "minute per IP address."
    ),
    responses={
        400: problem_doc("The code is wrong, expired, used, or for another change"),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`: "
            "no code was sent"
        ),
        422: problem_doc("The code is not 6 digits"),
        429: problem_doc(
            "Too many requests, or too many wrong codes for your phone; see the "
            "Retry-After header"
        ),
    },
)
@rate_limit(SESSION_LIMIT)
def logout_all(
    request: Request,
    account: CurrentAccount,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> LoggedOutAll:
    return LoggedOutAll(
        sessions_ended=session_service.log_out_everywhere(db, account, step_up_code, now)
    )

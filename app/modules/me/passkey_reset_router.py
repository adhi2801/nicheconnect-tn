"""Starting a passkey reset with the number alone (HTTP). The rules: passkey_service.

Under /api/v1/auth, where signing in lives, since with passkey-only sign-in
on, the number and a code cannot sign in; it is in `me` only so the owner
can be told (D-099), as for logging out everywhere.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.me import passkey_service as service
from app.modules.me.passkey_schemas import PasskeyResetIn, PasskeyResetRead

# As for checking a login code: per address.
RESET_LIMIT = "10 per 10 minutes"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/passkey-reset",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PasskeyResetRead,
    summary="Reset my passkeys, having lost them all",
    description=(
        "For when every passkey is lost. Send your number and a login code "
        "sent to it (`POST /api/v1/auth/otp/request`); the code is used up "
        "here. **Every passkey is removed 7 days later**, and passkey-only "
        "sign-in turned off, unless anyone signs in with a passkey before "
        "then, which cancels it. You are told in the app either way. Asking "
        "again while one waits changes nothing. Limit: 10 per 10 minutes per "
        "address."
    ),
    responses={
        400: problem_doc("`otp_invalid`: the code is wrong, expired or used"),
        409: problem_doc(
            "`no_passkey_to_reset`: the number's account has no passkey (said "
            "only once the code was right)"
        ),
        422: problem_doc("The number or the code is malformed"),
        429: problem_doc("Too many attempts; see the Retry-After header"),
    },
)
@rate_limit(RESET_LIMIT)
def start_a_passkey_reset(
    request: Request,
    body: PasskeyResetIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PasskeyResetRead:
    return PasskeyResetRead.model_validate(
        service.request_reset(db, body.phone, body.code, now)
    )

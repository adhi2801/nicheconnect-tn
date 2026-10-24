"""The admins' login with two factors, over HTTP (item 101, D-105). Rules in admin_login_service.

Public, like every login route: the credentials are in the body. Not under
/api/v1/admin, whose routes answer 404 to anyone who is not already a
signed-in admin.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.admin import admin_login_service as service
from app.modules.admin.schemas import (
    AdminLoginIn,
    SecondFactorSetupIn,
    SecondFactorSetupRead,
)
from app.modules.auth.dependencies import get_now
from app.modules.auth.schemas import AccountSummary, LoginTokens
from app.modules.auth.service import ClientDevice

# Per address, as for the phone-code login (security.md section 5). The
# phone's own guess limits and the factor's lock sit behind it.
ADMIN_LOGIN_LIMIT = "10 per 10 minutes"

router = APIRouter(prefix="/api/v1/auth/admin", tags=["admin login"])

_ERRORS: ResponseDocs = {
    400: problem_doc(
        "A code or the ticket is wrong, expired or used, or the number is not "
        "an admin's: one answer for all, so nothing is revealed"
    ),
    403: problem_doc("This admin account is suspended"),
    422: problem_doc("A field is missing or invalid"),
    429: problem_doc("Too many attempts; see the Retry-After header"),
}


def _seconds_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds())


@router.post(
    "/login",
    response_model=LoginTokens,
    summary="Log in as an admin, with the phone code and the authenticator code",
    description=(
        "Both factors in one request: the code sent to the phone, and the "
        "6-digit code the admin's authenticator app shows. Either wrong is "
        "answered exactly as a wrong phone code. Every active admin is told of "
        "every sign-in, and of a right phone code with a refused authenticator "
        "code. Ten refused authenticator codes in a row lock it until a founder "
        "issues a new setup ticket. The refresh token lasts an hour from each "
        "use and never past 12 hours from this login. Limit: 10 requests per 10 "
        "minutes per IP address; each phone code allows 5 attempts."
    ),
    responses=_ERRORS,
)
@rate_limit(ADMIN_LOGIN_LIMIT)
def log_in(
    request: Request,
    response: Response,
    body: AdminLoginIn,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> LoginTokens:
    device = ClientDevice(**body.device.model_dump()) if body.device is not None else None
    result = service.log_in(
        db, body.phone, body.code, body.authenticator_code, now, device
    )
    # Tokens must never be cached by browsers or proxies.
    response.headers["Cache-Control"] = "no-store"
    return LoginTokens(
        access_token=result.access_token,
        expires_in=_seconds_between(now, result.access_token_expires_at),
        refresh_token=result.refresh_token,
        refresh_expires_in=_seconds_between(now, result.refresh_token_expires_at),
        account=AccountSummary(id=result.account_id, role=result.role, is_new=False),
    )


@router.post(
    "/second-factor",
    status_code=status.HTTP_201_CREATED,
    response_model=SecondFactorSetupRead,
    summary="Set up an authenticator app, with a founder's setup ticket",
    description=(
        "Redeems the one-time ticket from `scripts/make_admin.py <phone> "
        "--second-factor` (15 minutes), with a code sent to the admin's phone, "
        "for a new authenticator secret. **Shown once**: put it into an "
        "authenticator app on a different device from this phone, or one "
        "locked by fingerprint, and not one that copies codes to a cloud "
        "account. Every active admin is told. There is no other way to change "
        "an admin's authenticator. Limit: 10 requests per 10 minutes per IP "
        "address."
    ),
    responses=_ERRORS,
)
@rate_limit(ADMIN_LOGIN_LIMIT)
def set_up_second_factor(
    request: Request,
    response: Response,
    body: SecondFactorSetupIn,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> SecondFactorSetupRead:
    setup = service.set_up(db, body.phone, body.code, body.ticket, now)
    response.headers["Cache-Control"] = "no-store"
    return SecondFactorSetupRead(secret=setup.secret, setup_link=setup.setup_link)

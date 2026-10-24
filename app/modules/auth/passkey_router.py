"""Logging in with a passkey (HTTP). The rules: auth.passkeys."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import passkeys
from app.modules.auth.dependencies import get_now
from app.modules.auth.passkey_schemas import PasskeyLoginIn
from app.modules.auth.schemas import AccountSummary, LoginTokens
from app.modules.auth.service import ClientDevice

# As for login codes: per address, since nobody is known yet.
PASSKEY_LOGIN_LIMIT = "10 per 10 minutes"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/passkey/options",
    summary="Start logging in with a passkey",
    description=(
        "WebAuthn's request options, to pass to `navigator.credentials.get` "
        "(or the phone's credential manager); no number is needed, as the "
        "phone offers the passkeys it holds for us. Its challenge works once, "
        "for 5 minutes. Limit: 10 per 10 minutes per address."
    ),
    responses={
        200: {"description": "WebAuthn's PublicKeyCredentialRequestOptions, as JSON"},
        429: problem_doc("Too many requests; see the Retry-After header"),
        503: problem_doc("`passkeys_unavailable`: passkeys are not switched on yet"),
    },
)
@rate_limit(PASSKEY_LOGIN_LIMIT)
def passkey_login_options(
    request: Request,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> dict[str, Any]:
    return passkeys.login_options(db, now)


@router.post(
    "/passkey/login",
    response_model=LoginTokens,
    summary="Log in with a passkey",
    description=(
        "Checks the passkey's answer and returns tokens, as a code login "
        "does. The session's tokens say it was proven by a passkey. Limit: 10 "
        "per 10 minutes per address."
    ),
    responses={
        400: problem_doc("`passkey_invalid`: the answer could not be checked"),
        403: problem_doc("`account_suspended`"),
        422: problem_doc("The answer is malformed"),
        429: problem_doc("Too many attempts; see the Retry-After header"),
        503: problem_doc("`passkeys_unavailable`: passkeys are not switched on yet"),
    },
)
@rate_limit(PASSKEY_LOGIN_LIMIT)
def passkey_login(
    request: Request,
    response: Response,
    body: PasskeyLoginIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> LoginTokens:
    device = ClientDevice(**body.device.model_dump()) if body.device is not None else None
    result = passkeys.log_in(db, body.credential, now, device)
    # Tokens must never be cached by browsers or proxies.
    response.headers["Cache-Control"] = "no-store"
    return LoginTokens(
        access_token=result.access_token,
        expires_in=int((result.access_token_expires_at - now).total_seconds()),
        refresh_token=result.refresh_token,
        refresh_expires_in=int((result.refresh_token_expires_at - now).total_seconds()),
        account=AccountSummary(id=result.account_id, role=result.role, is_new=False),
    )

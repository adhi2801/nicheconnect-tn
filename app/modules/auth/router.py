"""HTTP endpoints for OTP login (D-013). HTTP only: rules live in service.py."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.dependencies import get_now
from app.modules.auth.schemas import (
    AccountSummary,
    LoginTokens,
    OtpRequestAccepted,
    OtpRequestIn,
    OtpVerifyIn,
)
from app.modules.auth.sender import OtpSender, get_otp_sender

# Per-IP limits (security.md section 4). Per-phone send limits live in the service.
OTP_REQUEST_LIMIT = "3 per 10 minutes"
OTP_VERIFY_LIMIT = "10 per 10 minutes"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _seconds_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds())


@router.post(
    "/otp/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OtpRequestAccepted,
    summary="Send a one-time login code to a phone",
    description=(
        "Sends a 6-digit code by SMS or WhatsApp. The response is the same whether "
        "or not the number is registered. Limits: 3 codes per 10 minutes and 10 per "
        "day per phone, and 3 requests per 10 minutes per IP address."
    ),
    responses={
        422: problem_doc("The phone number is missing or not a valid Indian mobile"),
        429: problem_doc("Too many codes requested; see the Retry-After header"),
    },
)
@limiter.limit(OTP_REQUEST_LIMIT)
def request_code(
    request: Request,
    body: OtpRequestIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: OtpSender = Depends(get_otp_sender),
    now: datetime = Depends(get_now),
) -> OtpRequestAccepted:
    pending = service.request_otp(db, body.phone, now)
    background_tasks.add_task(service.deliver_otp, sender, pending)
    return OtpRequestAccepted(expires_in_seconds=_seconds_between(now, pending.expires_at))


@router.post(
    "/otp/verify",
    response_model=LoginTokens,
    summary="Log in with a one-time code",
    description=(
        "Checks the latest code sent to the phone. A new number gets an account with "
        "the given role. Returns a 15-minute access token and a 30-day refresh token. "
        "Limit: 10 requests per 10 minutes per IP address; each code allows 5 attempts."
    ),
    responses={
        400: problem_doc("The code is wrong, expired, already used, or was never sent"),
        409: problem_doc("The number is registered with the other role"),
        422: problem_doc("A field is missing or invalid"),
        429: problem_doc("Too many attempts; see the Retry-After header"),
    },
)
@limiter.limit(OTP_VERIFY_LIMIT)
def verify_code(
    request: Request,
    response: Response,
    body: OtpVerifyIn,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> LoginTokens:
    result = service.verify_otp(db, body.phone, body.code, body.role, now)
    # Tokens must never be cached by browsers or proxies.
    response.headers["Cache-Control"] = "no-store"
    return LoginTokens(
        access_token=result.access_token,
        expires_in=_seconds_between(now, result.access_token_expires_at),
        refresh_token=result.refresh_token,
        refresh_expires_in=_seconds_between(now, result.refresh_token_expires_at),
        account=AccountSummary(
            id=result.account_id, role=result.role, is_new=result.is_new_account
        ),
    )

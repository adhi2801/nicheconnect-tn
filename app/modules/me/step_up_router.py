"""Asking for a second check before a risky change (item 82, D-107).

The rules, and what they do and do not stop: auth.step_up_service. Here,
in `me` rather than `auth`, because a UPI ID is checked by payment_status's
own rule before a code is sent for it, and only a module above both may
read both (D-099); a new phone number likewise by phone_change_service.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import service as login
from app.modules.auth import step_up_service
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.sender import OtpSender, get_otp_sender
from app.modules.me import phone_change_service as phone_changes
from app.modules.me.step_up_schemas import (
    StepUpAccepted,
    StepUpForPhone,
    StepUpForUpiId,
    StepUpIn,
)

# Per account, beside the phone's own caps, which login codes share.
STEP_UP_LIMIT = "3 per 10 minutes;10 per day"

# A retry with the same Idempotency-Key gets the first answer, and no second
# message is sent.
router = APIRouter(prefix="/api/v1/me", tags=["auth"], route_class=IdempotentRoute)


@router.post(
    "/step-up",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StepUpAccepted,
    summary="Ask for a code before a risky change",
    description=(
        "Sends a 6-digit code to your phone for one change: setting a UPI ID "
        "(this exact one), downloading your data, logging out everywhere, or "
        "moving your account to a new phone number (this exact one). "
        "Then make the change with the code in the `Step-Up-Code` header, "
        "within 5 minutes. A code works once, and only for the change it was "
        "asked for. Admins are sent nothing: they use their authenticator "
        "app's code. Limits: 3 per 10 minutes and 10 a day, counted with "
        "login codes for your phone."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc(
            "Only a creator may ask to set a UPI ID; an admin may not change "
            "their phone number here"
        ),
        409: problem_doc("`phone_unchanged`: that is already your number"),
        422: problem_doc(
            "The action is unknown, or the UPI ID or new number is not usable"
        ),
        429: problem_doc("Too many codes asked for; see the Retry-After header"),
    },
)
@rate_limit(STEP_UP_LIMIT)
def ask_for_step_up(
    request: Request,
    body: StepUpIn,
    account: CurrentAccount,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: OtpSender = Depends(get_otp_sender),
    now: datetime = Depends(get_now),
) -> StepUpAccepted:
    value = ""
    if isinstance(body, StepUpForUpiId):
        value = body.upi_id
    elif isinstance(body, StepUpForPhone):
        # Before a message is sent for a change that would be refused.
        phone_changes.ensure_new_phone(account, body.new_phone)
        value = body.new_phone
    code = step_up_service.request_code(db, account, body.action, value, now)
    if code.pending is not None:
        background_tasks.add_task(login.deliver_otp, sender, code.pending)
    return StepUpAccepted(
        action=code.action,
        method=code.method,
        expires_in_seconds=(
            None
            if code.expires_at is None
            else int((code.expires_at - now).total_seconds())
        ),
    )

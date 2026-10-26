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
from app.modules.auth.dependencies import CurrentAccount, LoginTime, get_now
from app.modules.auth.sender import OtpSender, get_otp_sender
from app.modules.me import step_up_changes
from app.modules.me.step_up_schemas import (
    StepUpAccepted,
    StepUpGranted,
    StepUpIn,
    StepUpPasskeyIn,
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
        "(this exact one), downloading one exact copy of your data, logging "
        "out everywhere, "
        "moving your account to a new phone number (this exact one), or "
        "deleting your account (`delete_account`), or making a token for an "
        "assistant with exactly these scopes (`create_agent_token`). "
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
            "their phone number here; or `login_too_recent`: changing the phone "
            "number, or replacing a UPI ID in effect, needs a login at least 7 "
            "days old (see Retry-After); an admin account cannot be deleted here, "
            "nor make a token for an assistant"
        ),
        404: problem_doc(
            "`export_not_found`: no such export of yours; `passkey_not_found`; "
            "or `session_not_found`: no such live session of yours"
        ),
        409: problem_doc(
            "`phone_unchanged`: that is already your number; or the export "
            "cannot be downloaded (`export_not_ready`, `export_failed`, "
            "`export_already_downloaded`, `export_expired`); or the account "
            "cannot be deleted yet (`deletion_already_requested`, "
            "`deletion_held_by_deals`)"
        ),
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
    login_time: LoginTime,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: OtpSender = Depends(get_otp_sender),
    now: datetime = Depends(get_now),
) -> StepUpAccepted:
    # Before a message is sent for a change that would be refused.
    value = step_up_changes.value_of(db, account, body, login_time, now)
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
        passkey_options=code.passkey_options,
    )


@router.post(
    "/step-up/passkey",
    response_model=StepUpGranted,
    summary="Approve a risky change with a passkey",
    description=(
        "Once you have a passkey, a risky change is proven by it, never by a "
        "code sent to your phone, which a SIM swapper could read. Ask at "
        "`POST /api/v1/me/step-up` for the change: the answer's "
        "`passkey_options` is a challenge for exactly that change. Answer it "
        "with your passkey and send the answer here, with the same change. "
        "You get a code for exactly that change, working once, for 5 "
        "minutes: send it in `Step-Up-Code` with the change itself."
    ),
    responses={
        400: problem_doc("The passkey's answer could not be checked"),
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc("This account type cannot make this change"),
        422: problem_doc("The change or the answer is malformed"),
        429: problem_doc("Too many requests; see the Retry-After header"),
        503: problem_doc("`passkeys_unavailable`: passkeys are not switched on yet"),
    },
)
@rate_limit(STEP_UP_LIMIT)
def approve_with_passkey(
    request: Request,
    body: StepUpPasskeyIn,
    account: CurrentAccount,
    login_time: LoginTime,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> StepUpGranted:
    value = step_up_changes.value_of(db, account, body.change, login_time, now)
    grant = step_up_service.grant_for_passkey(
        db, account, body.change.action, value, body.credential, now
    )
    return StepUpGranted(
        action=grant.action,
        code=grant.code,
        expires_in_seconds=int((grant.expires_at - now).total_seconds()),
    )

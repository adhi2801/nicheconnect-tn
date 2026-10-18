"""Changing the phone number you log in with (HTTP). The rules and the threat model: phone_change_service."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import (
    CurrentAccount,
    LoginTime,
    StepUpCode,
    get_now,
)
from app.modules.me import phone_change_service as service
from app.modules.me.phone_change_schemas import (
    PhoneChangeIn,
    PhoneChangeRead,
    PhoneChangeWaitingRead,
)

READ_LIMIT = "60 per minute"
# Per account, beside both phones' own caps on codes, sent and guessed.
CHANGE_LIMIT = "5 per 10 minutes;10 per day"
CANCEL_LIMIT = "30 per minute"

# A retry of the change with the same Idempotency-Key gets the first answer,
# rather than being refused for codes already used.
router = APIRouter(prefix="/api/v1/me", tags=["auth"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(state: service.PhoneChangeState) -> PhoneChangeRead:
    return PhoneChangeRead(
        phone=state.phone,
        waiting=(
            PhoneChangeWaitingRead.model_validate(state.waiting, from_attributes=True)
            if state.waiting is not None
            else None
        ),
    )


@router.get(
    "/phone-change",
    response_model=PhoneChangeRead,
    summary="My phone number, and a new one waiting",
    description=(
        "The number you log in with, and under `waiting` a new number you "
        "asked to move to, with when it takes over; null when there is none. "
        "Show a waiting change at the top of every screen, with a one-tap "
        "cancel: if it was not you, someone may have your number."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def read_my_phone_change(
    request: Request, account: CurrentAccount, db: Session = Depends(get_db)
) -> PhoneChangeRead:
    return _read(service.get_for_account(db, account))


@router.post(
    "/phone-change",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PhoneChangeRead,
    summary="Move my account to a new phone number",
    description=(
        "Needs **a login at least 7 days old**, which a SIM swapper never "
        "has: from a newer one, 403 `login_too_recent`, with `Retry-After` "
        "saying when. And **a code from each number**: from your current number, ask at "
        "`POST /api/v1/me/step-up` with `change_phone` and this exact new "
        "number, and send it in the `Step-Up-Code` header; from the new "
        "number, ask at `POST /api/v1/auth/otp/request`, and send it as "
        "`new_phone_code`. **The new number takes over 72 hours later**: "
        "until then you log in with your current number, are told in the "
        "app, and can cancel with no code. Then every session ends, and you "
        "log in with the new number; the old one no longer reaches this "
        "account. Asking again replaces a change still waiting and starts its "
        "72 hours again. Brands and creators only: an admin's number is "
        "changed by the founders. Limits: 5 per 10 minutes and 10 a day, "
        "beside each number's own limits on codes."
    ),
    responses={
        **_COMMON,
        400: problem_doc(
            "A code is wrong, expired or used: `otp_invalid` for the new "
            "number's, `step_up_code_invalid` for the current number's"
        ),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`: "
            "no code from the current number was sent"
        ),
        403: problem_doc(
            "`role_not_allowed`: an admin's number cannot be changed here; "
            "`login_too_recent`: this login is under 7 days old (see Retry-After)"
        ),
        409: problem_doc(
            "`phone_unchanged`: it is already your number; `phone_in_use`: the "
            "new number is on an account, or waiting to move onto one; "
            "`phone_change_taking_effect`: the change waiting is past its 72 "
            "hours and being made"
        ),
        422: problem_doc("The new number or its code is not valid"),
        429: problem_doc(
            "Too many requests, or too many wrong codes for either number; see "
            "the Retry-After header"
        ),
    },
)
@rate_limit(CHANGE_LIMIT)
def change_my_phone(
    request: Request,
    body: PhoneChangeIn,
    account: CurrentAccount,
    login_time: LoginTime,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PhoneChangeRead:
    return _read(
        service.request_change(
            db,
            account,
            body.new_phone,
            body.new_phone_code,
            step_up_code,
            login_time,
            now,
        )
    )


@router.post(
    "/phone-change/without-current-number",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PhoneChangeRead,
    summary="Move my account to a new number when my current number is lost",
    description=(
        "For when your current number is already gone, so no code can reach "
        "it. Needs **a login at least 30 days old** (403 `login_too_recent`, "
        "with `Retry-After`, from a newer one), or, once you have a passkey, "
        "the passkey's grant in `Step-Up-Code` instead; and a code from the "
        "new number, "
        "asked for at `POST /api/v1/auth/otp/request`, as `new_phone_code`. "
        "**The new number takes over 7 days later**, and **any login with "
        "your current number before then cancels it**, since that number was "
        "not lost after all; you are told either way. Asking again replaces a "
        "change still waiting. Brands and creators only. There is no other "
        "way: we never move a number on someone's word, so a lost number "
        "with no login this old cannot be recovered. Limits as for a change "
        "with both numbers."
    ),
    responses={
        **_COMMON,
        400: problem_doc("The new number's code is wrong, expired or used"),
        403: problem_doc(
            "`role_not_allowed`: an admin's number cannot be changed here; "
            "`login_too_recent`: this login is under 30 days old (see Retry-After)"
        ),
        409: problem_doc(
            "`phone_unchanged`, `phone_in_use` or `phone_change_taking_effect`, "
            "as for a change with both numbers"
        ),
        422: problem_doc("The new number or its code is not valid"),
        429: problem_doc(
            "Too many requests, or too many wrong codes for the new number; see "
            "the Retry-After header"
        ),
    },
)
@rate_limit(CHANGE_LIMIT)
def change_my_lost_phone(
    request: Request,
    body: PhoneChangeIn,
    account: CurrentAccount,
    login_time: LoginTime,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PhoneChangeRead:
    return _read(
        service.request_change_without_current_number(
            db,
            account,
            body.new_phone,
            body.new_phone_code,
            login_time,
            now,
            step_up_code=step_up_code,
        )
    )


@router.delete(
    "/phone-change",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel a new phone number before it takes over",
    description=(
        "Drops the new number under `waiting`, so you keep logging in with "
        "the one you have. For when the change was not you: no code is "
        "needed, so it works from any of your sessions even if someone else "
        "has your number. Safe to repeat; nothing waiting is fine."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`phone_change_taking_effect`: its 72 hours are over and it is "
            "being made; see the Retry-After header"
        ),
    },
)
@rate_limit(CANCEL_LIMIT)
def cancel_my_phone_change(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    service.cancel(db, account, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

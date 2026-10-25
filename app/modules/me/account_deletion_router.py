"""Deleting your account (HTTP). The rules and the threat model: account_deletion_service."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, StepUpCode, get_now
from app.modules.me import account_deletion_service as service
from app.modules.me.account_deletion_schemas import (
    MAX_UNFINISHED_SHOWN,
    AccountDeletionRead,
    KeptKindRead,
)

READ_LIMIT = "60 per minute"
# Per account, beside the phone's own caps on step-up codes.
REQUEST_LIMIT = "5 per 10 minutes;10 per day"
CANCEL_LIMIT = "30 per minute"

# A retry of the request with the same Idempotency-Key gets the first
# answer, rather than being refused for a code already used.
router = APIRouter(prefix="/api/v1/me", tags=["auth"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(state: service.DeletionState) -> AccountDeletionRead:
    return AccountDeletionRead(
        status=state.status,
        requested_at=state.requested_at,
        takes_effect_at=state.takes_effect_at,
        unfinished_deals=len(state.unfinished_deal_ids),
        unfinished_deal_ids=state.unfinished_deal_ids[:MAX_UNFINISHED_SHOWN],
        kept=[
            KeptKindRead(
                kind=kind.kind, what=kind.what, kept_for_days=kind.kept_for_days()
            )
            for kind in state.kept
        ],
    )


@router.get(
    "/deletion",
    response_model=AccountDeletionRead,
    summary="Deleting my account: where it stands",
    description=(
        "Whether your account is waiting to be deleted and when, the deals "
        "that would hold it, and what is kept afterwards because a law may "
        "require it. Show a waiting deletion at the top of every screen, "
        "with a one-tap cancel: if it was not you, someone may have your "
        "number."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def read_my_deletion(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AccountDeletionRead:
    return _read(service.get_state(db, account, now))


@router.post(
    "/deletion",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AccountDeletionRead,
    summary="Delete my account, 30 days from now",
    description=(
        "Needs **a code**: ask at `POST /api/v1/me/step-up` with "
        "`delete_account`, and send it in the `Step-Up-Code` header. Refused "
        "while any of your deals is unfinished: finish, decline or cancel "
        "each first. **It takes effect 30 days later**: until then "
        "everything works as before, you are told in the app, and you can "
        "cancel with no code. Then what no law asks us to keep is erased: "
        "your number, sessions, passkeys, notifications, prices, channels, "
        "UPI IDs, blocks, exports, Passport, and your name and handle, "
        "which the other side's deals then show as someone who left. What "
        "is kept is listed under `kept`. Your number is free to make a new "
        "account with. A deal begun in the 30 days holds the deletion until "
        "it is finished. Brands and creators only. Limits: 5 per 10 minutes "
        "and 10 a day."
    ),
    responses={
        **_COMMON,
        400: problem_doc("`step_up_code_invalid`: the code is wrong, expired or used"),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`: "
            "no code was sent"
        ),
        403: problem_doc(
            "`role_not_allowed`: an admin account is removed by the founders"
        ),
        409: problem_doc(
            "`deletion_already_requested`: it is already waiting; "
            "`deletion_held_by_deals`: a deal of yours is unfinished"
        ),
        429: problem_doc(
            "Too many requests, or too many wrong codes for your phone; see the "
            "Retry-After header"
        ),
    },
)
@rate_limit(REQUEST_LIMIT)
def delete_my_account(
    request: Request,
    account: CurrentAccount,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AccountDeletionRead:
    return _read(service.request_deletion(db, account, step_up_code, now))


@router.delete(
    "/deletion",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Keep my account: cancel its deletion",
    description=(
        "Cancels a deletion waiting its 30 days, or held by a deal. For when "
        "it was not you: no code is needed, so it works from any of your "
        "sessions even if someone else has your number. Safe to repeat; "
        "nothing waiting is fine."
    ),
    responses=_COMMON,
)
@rate_limit(CANCEL_LIMIT)
def cancel_my_deletion(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    service.cancel(db, account, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Your passkeys (HTTP). The rules and the threat model: passkey_service and auth.passkeys."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, LoginTime, StepUpCode, get_now
from app.modules.me import passkey_service as service
from app.modules.me.passkey_schemas import (
    PasskeyCreate,
    PasskeyOnlySet,
    PasskeyRead,
    PasskeyRename,
    PasskeyResetRead,
    PasskeysRead,
)

READ_LIMIT = "60 per minute"
WRITE_LIMIT = "30 per minute"
# Each sign-up challenge is a row; a person adds a handful of keys, ever.
OPTIONS_LIMIT = "10 per 10 minutes;30 per day"

router = APIRouter(prefix="/api/v1/me", tags=["passkeys"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_CODE: ResponseDocs = {
    400: problem_doc("The code is wrong, expired, used, or for another change"),
    401: problem_doc(
        "No access token, or it is invalid or expired; or `step_up_required`: "
        "no code was sent"
    ),
    429: problem_doc(
        "Too many requests, or too many wrong codes; see the Retry-After header"
    ),
}
_UNAVAILABLE: ResponseDocs = {
    503: problem_doc("`passkeys_unavailable`: passkeys are not switched on yet")
}


def _read(state: service.PasskeyState) -> PasskeysRead:
    return PasskeysRead(
        items=[PasskeyRead.model_validate(key) for key in state.passkeys],
        passkey_only=state.passkey_only,
        reset=(
            PasskeyResetRead.model_validate(state.reset)
            if state.reset is not None
            else None
        ),
    )


@router.get(
    "/passkeys",
    response_model=PasskeysRead,
    summary="My passkeys",
    description=(
        "Every passkey on your account, whether only they sign you in, and a "
        "reset waiting, if one was asked for with your number."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_my_passkeys(
    request: Request, account: CurrentAccount, db: Session = Depends(get_db)
) -> PasskeysRead:
    return _read(service.state_of(db, account))


@router.post(
    "/passkeys/options",
    summary="Start adding a passkey",
    description=(
        "WebAuthn's creation options, to pass to `navigator.credentials.create` "
        "(or the phone's credential manager). Its challenge works once, for 5 "
        "minutes. Then send the answer to `POST /api/v1/me/passkeys`."
    ),
    responses={
        **_COMMON,
        200: {"description": "WebAuthn's PublicKeyCredentialCreationOptions, as JSON"},
        403: problem_doc("Admins cannot add passkeys yet"),
        **_UNAVAILABLE,
    },
)
@rate_limit(OPTIONS_LIMIT)
def start_adding_a_passkey(
    request: Request,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> dict[str, Any]:
    return service.registration_options(db, account, now)


@router.post(
    "/passkeys",
    status_code=status.HTTP_201_CREATED,
    response_model=PasskeyRead,
    summary="Add a passkey",
    description=(
        "Keeps the passkey your phone made. **Needs a code** for `add_passkey` "
        "from `POST /api/v1/me/step-up`: for your first passkey, a code sent "
        "to your phone, from a login at least 7 days old (or your account's "
        "very first login); for every later one, your passkey's approval. "
        "You are told on every device. At most 10."
    ),
    responses={
        **_CODE,
        400: problem_doc(
            "`passkey_invalid`: the answer could not be checked; or the code is "
            "wrong, expired or used"
        ),
        403: problem_doc(
            "Admins cannot add passkeys yet; or `login_too_recent` for a first "
            "passkey from a login under 7 days old"
        ),
        409: problem_doc("`too_many_passkeys`: you have 10 already"),
        422: problem_doc("The name or the answer is malformed"),
        **_UNAVAILABLE,
    },
)
@rate_limit(WRITE_LIMIT)
def add_a_passkey(
    request: Request,
    response: Response,
    body: PasskeyCreate,
    account: CurrentAccount,
    login_time: LoginTime,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PasskeyRead:
    passkey = service.add(
        db, account, body.credential, body.name, step_up_code, login_time, now
    )
    response.headers["Location"] = "/api/v1/me/passkeys"
    return PasskeyRead.model_validate(passkey)


@router.patch(
    "/passkeys/{passkey_id}",
    response_model=PasskeyRead,
    summary="Rename a passkey",
    description="Changes only its name. No code is needed.",
    responses={
        **_COMMON,
        404: problem_doc("No such passkey of yours"),
        422: problem_doc("The name is blank or too long"),
    },
)
@rate_limit(WRITE_LIMIT)
def rename_a_passkey(
    request: Request,
    passkey_id: uuid.UUID,
    body: PasskeyRename,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PasskeyRead:
    return PasskeyRead.model_validate(
        service.rename(db, account, passkey_id, body.name, now)
    )


@router.delete(
    "/passkeys/{passkey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a passkey",
    description=(
        "**Needs your passkey's approval** for `remove_passkey` and this "
        "passkey's id. Removing the last one also turns passkey-only sign-in "
        "off. You are told on every device. Lost every passkey? Start a reset "
        "with your number at `POST /api/v1/auth/passkey-reset`."
    ),
    responses={**_CODE, 404: problem_doc("No such passkey of yours")},
)
@rate_limit(WRITE_LIMIT)
def remove_a_passkey(
    request: Request,
    passkey_id: uuid.UUID,
    account: CurrentAccount,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    service.remove(db, account, passkey_id, step_up_code, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/passkeys/only",
    response_model=PasskeysRead,
    summary="Sign in only with a passkey, or not",
    description=(
        "With it on, a code sent to your phone no longer signs you in, so a "
        "SIM swapper cannot either; a code can then only start a 7-day reset. "
        "**Needs your passkey's approval** for `passkey_only` with exactly "
        "this `enabled`. You are told on every device."
    ),
    responses={
        **_CODE,
        403: problem_doc("Admins cannot use passkeys yet"),
        409: problem_doc("`passkey_needed_first`: add a passkey first"),
        422: problem_doc("`enabled` is missing or not true or false"),
    },
)
@rate_limit(WRITE_LIMIT)
def set_passkey_only(
    request: Request,
    body: PasskeyOnlySet,
    account: CurrentAccount,
    step_up_code: StepUpCode = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PasskeysRead:
    service.set_passkey_only(db, account, body.enabled, step_up_code, now)
    return _read(service.state_of(db, account))

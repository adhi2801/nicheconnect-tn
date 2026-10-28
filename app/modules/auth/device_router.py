"""Push devices over HTTP (item 9, D-095). The rules live in `device_service`."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import device_service
from app.modules.auth.dependencies import CurrentAccount, CurrentSessionId, get_now
from app.modules.auth.device_schemas import DeviceRead, DeviceRegister

# Apps register on every start and when a token changes: a handful a day.
# The daily ceiling stops a loop in a broken build from churning the table.
WRITE_LIMIT = "20 per minute;200 per day"

router = APIRouter(prefix="/api/v1/me/devices", tags=["notifications"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    422: problem_doc("A field is missing or invalid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.put(
    "",
    response_model=DeviceRead,
    summary="Register this phone for push notifications",
    description=(
        "Records the push token Firebase or Apple gave this install, or refreshes "
        "it; send it on every app start and whenever the token changes. Safe to "
        "repeat. A token already registered to another account moves to this "
        "one, so a phone handed on stops showing the last person's "
        "notifications. Each account keeps its 10 most recently seen phones. "
        "The phone belongs to the session registering it: when that session "
        "ends, by a logout, from another device or everywhere, the phone is "
        "unregistered with it. A session already ended is refused (401). "
        "The token is never returned; keep the `id` to unregister."
    ),
    responses=_ERRORS,
)
@rate_limit(WRITE_LIMIT)
def register_device(
    request: Request,
    body: DeviceRegister,
    account: CurrentAccount,
    session_id: CurrentSessionId,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DeviceRead:
    device = device_service.register(
        db,
        account.id,
        token=body.token,
        platform=body.platform,
        app_version=body.app_version,
        now=now,
        session_id=session_id,
    )
    return DeviceRead(
        id=device.id,
        platform=device.platform,
        app_version=device.app_version,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
    )


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop push notifications to a phone",
    description=(
        "Unregisters one of your phones, by the `id` registering it returned. "
        "Ending the session that registered it does this too."
    ),
    responses={
        **_ERRORS,
        404: problem_doc("No such device, or it is not yours"),
        422: problem_doc("The device id is not a valid id"),
    },
)
@rate_limit(WRITE_LIMIT)
def remove_device(
    request: Request,
    device_id: Annotated[uuid.UUID, Path(description="The id registering returned")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    device_service.remove(db, account.id, device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

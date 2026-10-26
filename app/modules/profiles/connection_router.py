"""Connected Instagram and YouTube accounts (HTTP, item 29, D-134).

Two groups: the creator's own connections, signed in; and Meta's callbacks,
public by design and verified by Meta's signature instead of a login. The
rules: connection_service.
"""

from datetime import datetime
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Body, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentCreator, get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.profiles import connection_service as service
from app.modules.profiles import profile_service as profiles
from app.modules.profiles.connection_models import ConnectedAccount
from app.modules.profiles.schemas import (
    ConnectedPlatform,
    ConnectionComplete,
    ConnectionRead,
    ConnectionStartRead,
    DeletionStatusRead,
    MetaDeletionRead,
)

READ_LIMIT = "60 per minute"
# Starting and completing are each a round trip to a platform: a few an
# hour is plenty for a person, and a ceiling a day for a script.
CONNECT_LIMIT = "10 per minute;50 per day"
# Meta's callbacks come from Meta's servers, keyed by address.
CALLBACK_LIMIT = "60 per minute"

router = APIRouter(
    prefix="/api/v1/creators/me/connections",
    tags=["profiles"],
    route_class=IdempotentRoute,
)
meta_router = APIRouter(prefix="/api/v1/platforms/meta", tags=["profiles"])

Platform = Annotated[ConnectedPlatform, Path(description="instagram or youtube")]
FormBody = Annotated[
    bytes,
    Body(
        media_type="application/x-www-form-urlencoded",
        description="Meta's form: `signed_request=<signature>.<payload>`",
    ),
]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only creators connect accounts"),
    404: problem_doc("You have not created a creator profile yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_OFF: ResponseDocs = {503: problem_doc("`connections_unavailable`: not switched on yet")}


def _creator(db: Session, account: Account) -> Creator:
    return profiles.get_profile(db, Creator, account.id)


def _read(connection: ConnectedAccount) -> ConnectionRead:
    return ConnectionRead(
        platform=connection.platform,
        handle=connection.handle,
        status=connection.status,
        connected_at=connection.connected_at,
        verified_followers=connection.verified_followers,
        verified_as_of=connection.verified_as_of,
    )


@router.get(
    "",
    response_model=list[ConnectionRead],
    summary="My connected accounts",
    description=(
        "The Instagram and YouTube accounts you connected, with the counts the "
        "platform itself reported. At most one a platform."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def my_connections(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> list[ConnectionRead]:
    return [_read(c) for c in service.connections_of(db, _creator(db, account))]


@router.post(
    "/{platform}/start",
    response_model=ConnectionStartRead,
    summary="Start connecting an account",
    description=(
        "Returns the platform's sign-in link, good for 10 minutes and once. The "
        "platform sends you back to our website or app with `code` and `state`; "
        "post them to `.../complete` while signed in as you."
    ),
    responses={**_COMMON, **_OFF},
)
@rate_limit(CONNECT_LIMIT)
def start_connecting(
    request: Request,
    platform: Platform,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ConnectionStartRead:
    _creator(db, account)
    started = service.start(db, account.id, platform, now)
    return ConnectionStartRead(
        authorize_url=started.authorize_url, expires_at=started.expires_at
    )


@router.post(
    "/{platform}/complete",
    response_model=ConnectionRead,
    summary="Finish connecting an account",
    description=(
        "With the `code` and `state` the platform sent back. The account it "
        "reaches is connected to you, and its count read. Connecting again "
        "replaces your earlier connection on that platform."
    ),
    responses={
        **_COMMON,
        **_OFF,
        409: problem_doc(
            "`connection_attempt_invalid`: expired, used or not yours; "
            "`platform_refused`: the platform said no; "
            "`channel_already_connected`: another creator holds that account"
        ),
        422: problem_doc("The code or state is missing or too long"),
    },
)
@rate_limit(CONNECT_LIMIT)
def complete_connecting(
    request: Request,
    platform: Platform,
    body: ConnectionComplete,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ConnectionRead:
    creator = _creator(db, account)
    connection = service.complete(
        db, account.id, creator, platform, code=body.code, state=body.state, now=now
    )
    return _read(connection)


@router.delete(
    "/{platform}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect an account",
    description=(
        "Deletes the connection and the keys the platform gave us, then asks the "
        "platform to revoke them where it offers that. Always allowed."
    ),
    responses={**_COMMON, 404: problem_doc("No account connected on that platform")},
)
@rate_limit(CONNECT_LIMIT)
def disconnect(
    request: Request,
    platform: Platform,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> Response:
    service.disconnect(db, _creator(db, account), platform)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _signed_request(raw: bytes) -> str:
    values = parse_qs(raw.decode("utf-8", errors="replace")).get("signed_request", [])
    return values[0] if len(values) == 1 else ""


_META: ResponseDocs = {
    400: problem_doc("`invalid_signed_request`: not signed by Meta with our app secret"),
    429: problem_doc("Too many requests; see the Retry-After header"),
    503: problem_doc("`connections_unavailable`: no Meta app is set up yet"),
}


@meta_router.post(
    "/data-deletion",
    response_model=MetaDeletionRead,
    summary="Meta: delete what we hold about one of its users",
    description=(
        "Meta's data deletion callback, public by design: verified by Meta's "
        "signature. Deletes the person's connection and answers with a status "
        "link and a confirmation code."
    ),
    responses=_META,
)
@rate_limit(CALLBACK_LIMIT)
def meta_data_deletion(
    request: Request,
    raw: FormBody,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> MetaDeletionRead:
    deleted = service.meta_data_deletion(db, _signed_request(raw), now)
    base = str(settings.platform_redirect_base or "").rstrip("/")
    return MetaDeletionRead(
        url=f"{base}/meta-deletion/{deleted.confirmation_code}",
        confirmation_code=deleted.confirmation_code,
    )


@meta_router.post(
    "/deauthorize",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Meta: one of its users removed our app",
    description=(
        "Meta's deauthorize callback, public by design: verified by Meta's "
        "signature. The person's connection is deleted."
    ),
    responses=_META,
)
@rate_limit(CALLBACK_LIMIT)
def meta_deauthorize(
    request: Request, raw: FormBody, db: Session = Depends(get_db)
) -> Response:
    service.meta_deauthorize(db, _signed_request(raw))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@meta_router.get(
    "/data-deletion/{confirmation_code}",
    response_model=DeletionStatusRead,
    summary="Meta: what happened to a deletion request",
    description=(
        "Public by design, as Meta requires: the code alone, 24 random "
        "characters, says nothing about the person."
    ),
    responses={
        404: problem_doc("`deletion_request_not_found`: no request has that code"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(CALLBACK_LIMIT)
def meta_deletion_status(
    request: Request,
    confirmation_code: Annotated[str, Path(min_length=1, max_length=24)],
    db: Session = Depends(get_db),
) -> DeletionStatusRead:
    found = service.deletion_status(db, confirmation_code)
    return DeletionStatusRead(
        confirmation_code=found.confirmation_code,
        platform=found.platform,
        received_at=found.received_at,
        status="done",
        removed=found.removed,
    )

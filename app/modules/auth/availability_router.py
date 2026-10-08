"""A creator's availability, over HTTP (D-083). The rules: availability_service."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import availability_service as service
from app.modules.auth import profiles
from app.modules.auth.dependencies import CurrentCreator, get_now
from app.modules.auth.models.creator import Creator
from app.modules.auth.schemas import AvailabilityRead, AvailabilityUpdate

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

# PUT replaces the whole setting, so it is idempotent by nature and needs no
# Idempotency-Key (backend.md section 2).
router = APIRouter(prefix="/api/v1/creators", tags=["availability"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only a creator may use this endpoint"),
    404: problem_doc("You have not created a creator profile yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(creator: Creator, now: datetime) -> AvailabilityRead:
    today = india_date(now)
    return AvailabilityRead(
        booked_until=service.booked_until_shown(creator.booked_until, today),
        available_from=service.available_from(creator.booked_until, today),
    )


@router.get(
    "/me/availability",
    response_model=AvailabilityRead,
    summary="My availability",
    description=(
        "Whether you are taking new work, and from when. Signed-in brands see "
        "the same date in search and in suggested creators; it is never on "
        "your public Passport."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_availability(
    request: Request,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AvailabilityRead:
    return _read(profiles.get_profile(db, Creator, account.id), now)


@router.put(
    "/me/availability",
    response_model=AvailabilityRead,
    summary="Set my availability",
    description=(
        '"Booked until 20 Nov": the last day you are not taking new work, '
        "from today to a year ahead; null when you are taking work. Nothing "
        "is blocked: brands can still reach you and you can still apply."
    ),
    responses={
        **_ERRORS,
        422: problem_doc("The date is in the past or more than a year ahead"),
    },
)
@rate_limit(WRITE_LIMIT)
def set_availability(
    request: Request,
    body: AvailabilityUpdate,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> AvailabilityRead:
    creator = profiles.get_profile(db, Creator, account.id)
    service.set_booked_until(db, creator, body.booked_until, today=india_date(now))
    return _read(creator, now)

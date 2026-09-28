"""A creator's channels, packages and the switch that publishes their prices.

HTTP only: the rules live in `rate_card_service.py` (D-055).
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import profiles
from app.modules.auth import rate_card_service as service
from app.modules.auth.dependencies import CurrentCreator, get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import MAX_PACKAGES_PER_CREATOR
from app.modules.auth.schemas import (
    ChannelPlatform,
    ChannelRead,
    ChannelUpsert,
    CreatorProfileRead,
    PackageCreate,
    PackageRead,
    PackageUpdate,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

# route_class: a creator on patchy 4G who taps twice must not end up with two
# identical packages (D-040).
router = APIRouter(
    prefix="/api/v1/creators", tags=["rate card"], route_class=IdempotentRoute
)

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only a creator may use this endpoint"),
    404: problem_doc("You have not created a creator profile yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}

Platform = Annotated[ChannelPlatform, Path(description="instagram or youtube")]


def _creator(db: Session, account: Account) -> Creator:
    return profiles.get_profile(db, Creator, account.id)


# --- channels --------------------------------------------------------------


@router.get(
    "/me/channels",
    response_model=list[ChannelRead],
    summary="My channels",
    description=(
        "The Instagram and YouTube channels you have added, with the figures "
        "you gave and the date you gave them. These are your own numbers: we "
        "have never checked or changed them."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(READ_LIMIT)
def list_my_channels(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> list[ChannelRead]:
    return [
        ChannelRead.model_validate(row)
        for row in service.list_channels(db, _creator(db, account))
    ]


@router.put(
    "/me/channels/{platform}",
    response_model=ChannelRead,
    summary="Add or update one of my channels",
    description=(
        "Adds the channel if it is not there and replaces it if it is, so a "
        "retry is safe.\n\n"
        "The link must be on the platform you chose: an Instagram channel "
        "needs an instagram.com link. **The date is set by us, not by you** — "
        "it records when you told us, which is what makes the figures "
        "readable to a brand."
    ),
    responses={
        **_COMMON_ERRORS,
        422: problem_doc("A field is invalid, or the link is not on that platform"),
    },
)
@rate_limit(WRITE_LIMIT)
def save_my_channel(
    request: Request,
    platform: Platform,
    body: ChannelUpsert,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ChannelRead:
    channel = service.save_channel(
        db,
        _creator(db, account),
        platform=platform,
        profile_url=body.profile_url,
        followers=body.followers,
        average_views=body.average_views,
        today=india_date(now),
    )
    return ChannelRead.model_validate(channel)


@router.delete(
    "/me/channels/{platform}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove one of my channels",
    description="Takes the channel off your profile and your media kit at once.",
    responses={**_COMMON_ERRORS, 404: problem_doc("No channel for that platform")},
)
@rate_limit(WRITE_LIMIT)
def delete_my_channel(
    request: Request,
    platform: Platform,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> Response:
    service.delete_channel(db, _creator(db, account), platform)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- packages --------------------------------------------------------------


@router.get(
    "/me/packages",
    response_model=list[PackageRead],
    summary="My rate card",
    description=(
        "Everything you offer, in the order you set. Prices are whole paise, "
        "so 800000 is Rs 8,000."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(READ_LIMIT)
def list_my_packages(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> list[PackageRead]:
    return [
        PackageRead.model_validate(row)
        for row in service.list_packages(db, _creator(db, account))
    ]


@router.post(
    "/me/packages",
    response_model=PackageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a package to my rate card",
    description=(
        f"Up to {MAX_PACKAGES_PER_CREATOR} packages. Price in whole paise, and "
        "a price of zero is refused: that is a conversation, not a rate."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc(f"You already have {MAX_PACKAGES_PER_CREATOR} packages"),
        422: problem_doc("A field is invalid"),
    },
)
@rate_limit(WRITE_LIMIT)
def add_my_package(
    request: Request,
    body: PackageCreate,
    response: Response,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> PackageRead:
    package = service.create_package(
        db, _creator(db, account), **body.model_dump(exclude_unset=False)
    )
    response.headers["Location"] = f"/api/v1/creators/me/packages/{package.id}"
    return PackageRead.model_validate(package)


@router.patch(
    "/me/packages/{package_id}",
    response_model=PackageRead,
    summary="Change one of my packages",
    description="Send only the fields you are changing.",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such package of yours"),
        422: problem_doc("A field is invalid, or no field was sent"),
    },
)
@rate_limit(WRITE_LIMIT)
def change_my_package(
    request: Request,
    package_id: Annotated[uuid.UUID, Path(description="The package's id")],
    body: PackageUpdate,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> PackageRead:
    package = service.update_package(
        db, _creator(db, account), package_id, body.model_dump(exclude_unset=True)
    )
    return PackageRead.model_validate(package)


@router.delete(
    "/me/packages/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a package",
    description="Deleted outright, not hidden.",
    responses={**_COMMON_ERRORS, 404: problem_doc("No such package of yours")},
)
@rate_limit(WRITE_LIMIT)
def delete_my_package(
    request: Request,
    package_id: Annotated[uuid.UUID, Path(description="The package's id")],
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> Response:
    service.delete_package(db, _creator(db, account), package_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- the consent switch ----------------------------------------------------


@router.post(
    "/me/rate-card/publish",
    response_model=CreatorProfileRead,
    summary="Show my prices on my public page",
    description=(
        "Puts your packages on the public Passport at "
        "`/api/v1/creators/by-handle/{handle}`.\n\n"
        "**Signed-in brands can already see your prices**; this is only about "
        "the open internet. Publishing again keeps the date you first chose, "
        "and you can turn it off at any time."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(WRITE_LIMIT)
def publish_my_rate_card(
    request: Request,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Creator:
    return service.publish_rate_card(db, _creator(db, account), now)


@router.post(
    "/me/rate-card/unpublish",
    response_model=CreatorProfileRead,
    summary="Take my prices off my public page",
    description=(
        "Stops the public page showing your prices, immediately. Signed-in "
        "brands still see them, and your packages are not deleted."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(WRITE_LIMIT)
def unpublish_my_rate_card(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> Creator:
    return service.unpublish_rate_card(db, _creator(db, account))

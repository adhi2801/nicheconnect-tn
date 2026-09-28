"""The media kit: one signed-in screen for a brand weighing a creator (D-055).

The rules live in `media_kit_service`; this file is HTTP only.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import media_kit_service
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import ProfileNotFound, RoleNotAllowed
from app.modules.auth.media_kit_service import MediaKit
from app.modules.auth.schemas import ChannelRead, MediaKitRead, PackageRead
from app.modules.deal_memo.schemas import to_delivery_read

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/creators", tags=["media kit"])

CreatorId = Annotated[uuid.UUID, Path(description="The creator's id")]

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands, or the creator themself, can read this"),
    404: problem_doc("No such creator"),
    422: problem_doc("The creator id is not a valid id"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _to_read(kit: MediaKit) -> MediaKitRead:
    """Field by field: never a blanket dump of the creator row."""
    creator = kit.creator
    return MediaKitRead(
        creator_id=creator.id,
        handle=creator.handle,
        display_name=creator.display_name,
        city=creator.city,
        niches=creator.niches,
        languages=creator.languages,
        bio=creator.bio,
        member_since=creator.created_at.strftime("%Y-%m"),
        channels=[ChannelRead.model_validate(c) for c in kit.channels],
        packages=[PackageRead.model_validate(p) for p in kit.packages],
        delivery_record=to_delivery_read(kit.delivery),
    )


@router.get(
    "/{creator_id}/media-kit",
    response_model=MediaKitRead,
    summary="A creator's media kit",
    description=(
        "Everything a brand needs to weigh a creator, on one screen: the "
        "profile, each channel with its follower count and average views, "
        "every package with its price, and the delivery record. Channel "
        "numbers are the creator's own claim, dated by `figures_as_of`, and "
        "must be shown as self-reported. Prices appear here whether or not "
        "the creator published them on their public page. Readable by any "
        "brand and by the creator themself, never by another creator."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_media_kit(
    request: Request,
    creator_id: CreatorId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> MediaKitRead:
    """Any brand, or the creator themself."""
    if not media_kit_service.may_read(db, account, creator_id):
        raise RoleNotAllowed()
    kit = media_kit_service.for_creator(db, creator_id, now)
    if kit is None:
        raise ProfileNotFound()
    return _to_read(kit)

"""The public Creator Passport: one read-only page, no login needed.

This is the only endpoint in the product that answers to anyone at all, so it
is written defensively:

- it returns a narrow, hand-listed set of fields, never a model dump, so a
  column added later cannot leak by accident;
- contact details are not in the creator table at all (D-011), and the account
  id is withheld, so a public page cannot be tied back to a login;
- one function decides whether a profile may be published, which is where the
  creator's own opt-out will plug in (see PUBLICATION NOTE below);
- responses carry a cache header and an ETag, because a link in an Instagram
  bio is read far more often than it changes;
- channels appear as links only, never with our copy of a follower count
  (D-042), and prices only once the creator has published them, a consent
  separate from the Passport itself (D-055).

PUBLICATION: nobody is published until they choose to be. A creator who
signed up only to browse campaigns is not findable by strangers, and a
profile only appears here once its owner has turned the Passport on
(D-036). That switch is read in exactly one place, `passport_is_public`.
"""

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.rate_card_service import list_channels, list_packages
from app.modules.auth.schemas import (
    PublicChannelRead,
    PublicCreatorRead,
    PublicPackageRead,
    _normalize_handle,
)

# A bio in an Instagram profile is opened far more often than it is edited, so
# a short shared cache is worth it. TTL: 5 minutes. Invalidation: the ETag
# is a hash of the response itself, so any edit to the profile, a channel or
# a package changes it, and an edit is visible within the TTL at worst
# (backend.md section 6).
CACHE_SECONDS = 300
PUBLIC_READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/creators", tags=["public"])


def passport_is_public(creator: Creator) -> bool:
    """Whether this profile may be shown to the open internet.

    Only if its owner said so. `passport_published_at` is both the switch
    and the record of when they chose it.
    """
    return creator.passport_published_at is not None


def prices_are_public(creator: Creator) -> bool:
    """Whether this creator's packages may be shown to the open internet.

    A second consent, separate from the Passport: a creator may want to be
    findable without publishing what they charge (D-055).
    """
    return creator.rate_card_public_at is not None


def _etag(page: PublicCreatorRead) -> str:
    """A short fingerprint of exactly what the reader would receive.

    Hashing the page rather than a timestamp means an edit to a channel or a
    package, which lives in another table, changes it too.
    """
    digest = hashlib.sha256(page.model_dump_json().encode()).hexdigest()
    return '"' + digest[:32] + '"'


def _to_public(
    creator: Creator,
    channels: list[CreatorChannel],
    packages: list[CreatorPackage],
) -> PublicCreatorRead:
    """Build the response field by field: never a blanket dump of the row."""
    return PublicCreatorRead(
        id=creator.id,
        handle=creator.handle,
        display_name=creator.display_name,
        city=creator.city,
        niches=creator.niches,
        languages=creator.languages,
        bio=creator.bio,
        member_since=creator.created_at.strftime("%Y-%m"),
        channels=[
            PublicChannelRead(platform=c.platform, profile_url=c.profile_url)
            for c in channels
        ],
        packages=[PublicPackageRead.model_validate(p) for p in packages],
    )


@router.get(
    "/by-handle/{handle}",
    response_model=PublicCreatorRead,
    summary="Read a creator's public profile",
    description=(
        "The public Creator Passport, readable without logging in. Handles are "
        "matched in lowercase, so `@Priya.Eats` and `priya.eats` find the same "
        "profile. Channels are links only, never follower counts; packages "
        "appear only once the creator has published their prices, and are an "
        "empty list otherwise. Contact details are never included. Cached for "
        "5 minutes, with an ETag so an unchanged profile costs almost nothing "
        "to re-read."
    ),
    responses={
        404: problem_doc("No creator with that handle, or the profile is not public"),
        422: problem_doc("That is not a valid handle"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(PUBLIC_READ_LIMIT)
def read_public_profile(
    request: Request,
    response: Response,
    handle: str,
    if_none_match: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Response | PublicCreatorRead:
    """Anyone may call this. Nothing here depends on who is asking."""
    try:
        normalised = _normalize_handle(handle)
    except Exception:
        # An impossible handle is simply not found: no hint about what a valid
        # one looks like, and no stack trace for a stranger.
        raise ProfileNotFound() from None

    creator = db.scalars(select(Creator).where(Creator.handle == normalised)).first()
    if creator is None or not passport_is_public(creator):
        raise ProfileNotFound()

    # Three queries at most, however many channels or packages there are.
    # Unpublished prices are not even read.
    channels = list_channels(db, creator)
    packages = list_packages(db, creator) if prices_are_public(creator) else []
    page = _to_public(creator, channels, packages)

    etag = _etag(page)
    cache_headers = {"Cache-Control": f"public, max-age={CACHE_SECONDS}", "ETag": etag}
    if if_none_match == etag:
        # Unchanged since the reader last saw it: no body to send.
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)

    response.headers.update(cache_headers)
    return page

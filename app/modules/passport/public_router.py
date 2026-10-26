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
(D-036). That switch is read in exactly one place, `passport_service.passport_is_public`.
"""

import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.auth.models.creator import Creator
from app.modules.auth.schemas import _normalize_handle
from app.modules.passport import passport_service, structured_data
from app.modules.passport.schemas import (
    IndexablePassportRead,
    PublicChannelRead,
    PublicConnectionRead,
    PublicCreatorRead,
    PublicPackageRead,
)
from app.modules.profiles import connection_service as connections
from app.modules.profiles.connection_models import ConnectedAccount
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from app.modules.profiles.rate_card_service import list_channels, list_packages

# A bio in an Instagram profile is opened far more often than it is edited, so
# a short shared cache is worth it. TTL: 5 minutes. Invalidation: the ETag
# is a hash of the response itself, so any edit to the profile, a channel or
# a package changes it, and an edit is visible within the TTL at worst
# (backend.md section 6).
CACHE_SECONDS = 300
PUBLIC_READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/creators", tags=["public"])


def _etag(page: PublicCreatorRead) -> str:
    """A short fingerprint of exactly what the reader would receive.

    Hashing the page rather than a timestamp means an edit to a channel or a
    package, which lives in another table, changes it too.
    """
    digest = hashlib.sha256(page.model_dump_json().encode()).hexdigest()
    return '"' + digest[:32] + '"'


def _structured_data(
    creator: Creator,
    channels: list[CreatorChannel],
    packages: list[CreatorPackage],
) -> dict[str, Any] | None:
    """The Passport as search engines read it (item 85), or None while that is off."""
    if not settings.passport_indexing:
        return None
    prices_public = passport_service.prices_are_public(creator)
    return structured_data.profile_page(
        structured_data.PassportFacts(
            creator_id=creator.id,
            handle=creator.handle,
            display_name=creator.display_name,
            bio=creator.bio,
            created_at=creator.created_at,
            # The rule `passport_service.last_modified_sql` applies in SQL.
            last_modified=structured_data.last_modified(
                [
                    creator.updated_at,
                    creator.passport_published_at,
                    *(channel.updated_at for channel in channels),
                    creator.rate_card_public_at if prices_public else None,
                    *(package.updated_at for package in packages),
                ]
            ),
            channel_urls=[channel.profile_url for channel in channels],
        )
    )


def _to_public(
    creator: Creator,
    channels: list[CreatorChannel],
    packages: list[CreatorPackage],
    connections: list[ConnectedAccount],
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
        # Proof of control only, never a count (D-135, keeping D-042).
        connected_accounts=[
            PublicConnectionRead(
                platform=c.platform,
                handle=c.handle,
                connected_since=c.connected_at.date(),
            )
            for c in connections
        ],
        structured_data=_structured_data(creator, channels, packages),
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
        451: problem_doc(
            "The profile is withheld for legal reasons (item 52). Never cached"
        ),
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

    creator = passport_service.public_creator(db, normalised)

    # Four queries at most, however many channels, packages or connections.
    # Unpublished prices are not even read.
    channels = list_channels(db, creator)
    packages = (
        list_packages(db, creator) if passport_service.prices_are_public(creator) else []
    )
    page = _to_public(creator, channels, packages, connections.active_for(db, creator.id))

    etag = _etag(page)
    cache_headers = {"Cache-Control": f"public, max-age={CACHE_SECONDS}", "ETag": etag}
    if if_none_match == etag:
        # Unchanged since the reader last saw it: no body to send.
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)

    response.headers.update(cache_headers)
    return page


@router.get(
    "/indexable",
    response_model=Page[IndexablePassportRead],
    summary="Every Passport search engines may show",
    description=(
        "For the website's sitemap.xml (item 85): each published Passport's "
        "handle and when what its readers see last changed, newest Passport "
        "first. Exactly the Passports anyone may read: published by their "
        "creator, not suspended, not withheld. Readable without logging in. "
        "Empty until indexing is switched on, once the publish notice says "
        "search engines will show the Passport. Paginated: `limit` (default "
        "20, at most 100) and `cursor`. Cached for 5 minutes, with an ETag."
    ),
    responses={
        422: problem_doc("`limit` is out of range, or `cursor` is not one of ours"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(PUBLIC_READ_LIMIT)
def list_indexable_passports(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(description="From a previous page")] = None,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response | Page[IndexablePassportRead]:
    """Anyone may call this. Nothing here depends on who is asking."""
    found = passport_service.indexable_passports(db, limit=limit, cursor=cursor)
    page = Page[IndexablePassportRead](
        items=[
            IndexablePassportRead(handle=item.handle, last_modified=item.last_modified)
            for item in found.rows
        ],
        next_cursor=found.next_cursor,
    )
    etag = '"' + hashlib.sha256(page.model_dump_json().encode()).hexdigest()[:32] + '"'
    cache_headers = {"Cache-Control": f"public, max-age={CACHE_SECONDS}", "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=cache_headers)
    response.headers.update(cache_headers)
    return page

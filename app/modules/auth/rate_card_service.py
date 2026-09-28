"""Rules for a creator's channels and prices (D-055, D-042).

The schema enforces what a database can: a positive price, a known platform,
one Instagram per creator. Three rules it cannot enforce live here.

**A link must belong to the platform it claims.** The database only checks
`https://`. Without a domain check, a creator could put any link at all on a
page brands read, and the public Passport would carry it under our name.

**Ten packages.** A CHECK cannot count rows, so the limit is applied where it
can say something useful when it is reached.

**Publishing keeps the first date.** The timestamp is the consent itself
(D-036's reasoning, applied to prices), so a second tap on a slow connection
must not rewrite when the creator actually chose.
"""

import uuid
from datetime import date, datetime
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.exceptions import (
    ChannelNotFound,
    PackageLimitReached,
    PackageNotFound,
    ProfileUrlDoesNotMatchPlatform,
)
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import (
    MAX_PACKAGES_PER_CREATOR,
    CreatorChannel,
    CreatorPackage,
)

# The hosts each platform is actually served from. A creator pasting a
# shortened or regional link gets a clear refusal rather than a page that
# quietly sends brands somewhere else.
PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "instagram": ("instagram.com", "www.instagram.com"),
    "youtube": ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"),
}


def check_profile_url(platform: str, profile_url: str) -> None:
    """Refuse a link that does not belong to the platform it claims."""
    host = (urlparse(profile_url).hostname or "").lower()
    if host not in PLATFORM_HOSTS.get(platform, ()):
        raise ProfileUrlDoesNotMatchPlatform(
            f"A {platform} link must be on "
            f"{' or '.join(PLATFORM_HOSTS[platform][:2])}, not '{host or profile_url}'."
        )


# --- channels --------------------------------------------------------------


def list_channels(db: Session, creator: Creator) -> list[CreatorChannel]:
    return list(
        db.scalars(
            select(CreatorChannel)
            .where(CreatorChannel.creator_id == creator.id)
            .order_by(CreatorChannel.platform)
        ).all()
    )


def save_channel(
    db: Session,
    creator: Creator,
    *,
    platform: str,
    profile_url: str,
    followers: int,
    average_views: int | None,
    today: date,
) -> CreatorChannel:
    """Add or replace this creator's channel on one platform.

    An upsert rather than separate create and update, because a creator has at
    most one of each and "I have already added Instagram" is not a useful
    error. `figures_as_of` is set from the server's clock, never the client:
    it is the date we were told, and a client could otherwise claim yesterday's
    numbers were gathered today.
    """
    check_profile_url(platform, profile_url)

    channel = db.scalars(
        select(CreatorChannel).where(
            CreatorChannel.creator_id == creator.id,
            CreatorChannel.platform == platform,
        )
    ).first()

    if channel is None:
        channel = CreatorChannel(creator_id=creator.id, platform=platform)
        db.add(channel)

    channel.profile_url = profile_url
    channel.followers = followers
    channel.average_views = average_views
    channel.figures_as_of = today
    db.commit()
    db.refresh(channel)
    return channel


def delete_channel(db: Session, creator: Creator, platform: str) -> None:
    channel = db.scalars(
        select(CreatorChannel).where(
            CreatorChannel.creator_id == creator.id,
            CreatorChannel.platform == platform,
        )
    ).first()
    if channel is None:
        raise ChannelNotFound()
    db.delete(channel)
    db.commit()


# --- packages --------------------------------------------------------------


def list_packages(db: Session, creator: Creator) -> list[CreatorPackage]:
    return list(
        db.scalars(
            select(CreatorPackage)
            .where(CreatorPackage.creator_id == creator.id)
            .order_by(CreatorPackage.position, CreatorPackage.id)
        ).all()
    )


def _owned_package(
    db: Session, creator: Creator, package_id: uuid.UUID
) -> CreatorPackage:
    """Another creator's package is 404, never 403.

    403 would confirm the id exists, which would let anyone walk the table.
    """
    package = db.scalars(
        select(CreatorPackage).where(
            CreatorPackage.id == package_id,
            CreatorPackage.creator_id == creator.id,
        )
    ).first()
    if package is None:
        raise PackageNotFound()
    return package


def create_package(db: Session, creator: Creator, **fields: object) -> CreatorPackage:
    """Add a package, up to the limit."""
    count = (
        db.scalar(
            select(func.count(CreatorPackage.id)).where(
                CreatorPackage.creator_id == creator.id
            )
        )
        or 0
    )
    if count >= MAX_PACKAGES_PER_CREATOR:
        raise PackageLimitReached(
            f"You already have {MAX_PACKAGES_PER_CREATOR} packages. "
            f"Change or remove one before adding another."
        )

    package = CreatorPackage(creator_id=creator.id, **fields)
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


def update_package(
    db: Session, creator: Creator, package_id: uuid.UUID, changes: dict[str, object]
) -> CreatorPackage:
    package = _owned_package(db, creator, package_id)
    for field, value in changes.items():
        setattr(package, field, value)
    db.commit()
    db.refresh(package)
    return package


def delete_package(db: Session, creator: Creator, package_id: uuid.UUID) -> None:
    package = _owned_package(db, creator, package_id)
    db.delete(package)
    db.commit()


# --- the consent switch ----------------------------------------------------


def publish_rate_card(db: Session, creator: Creator, now: datetime) -> Creator:
    """Show prices on the public Passport. The first date is kept.

    A second tap on a slow connection is not a second decision, and rewriting
    the date would falsify when the creator actually chose (D-036 point 2).
    """
    if creator.rate_card_public_at is None:
        creator.rate_card_public_at = now
        db.commit()
        db.refresh(creator)
    # No rollback on the no-op branch, deliberately, and this differs from
    # profiles.publish_passport. There is nothing to undo, and a rollback here
    # discards whatever else the caller had pending in the same session —
    # which is exactly what it did to a test that published before anything
    # had been committed. Doing nothing is the honest no-op.
    return creator


def unpublish_rate_card(db: Session, creator: Creator) -> Creator:
    """Take prices off the public page. Never refused, and immediate.

    Somebody who wants to stop showing what they charge should not have to
    argue with us.
    """
    if creator.rate_card_public_at is not None:
        creator.rate_card_public_at = None
        db.commit()
        db.refresh(creator)
    # As above: nothing to undo, so nothing is rolled back.
    return creator

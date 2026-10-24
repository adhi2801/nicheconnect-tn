"""Who appears on the public Creator Passport, and when (D-036, D-055).

The rules behind the one page anyone on the internet can read. They lived in
its router until 12 October 2026, against `backend.md` section 1: a router
parses, calls and returns, and the rules live here.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.auth import suspension
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.auth.models.creator import Creator
from app.modules.profiles.models import CreatorChannel, CreatorPackage
from app.modules.safety.exceptions import ContentWithheld
from app.modules.safety.takedowns import is_withheld, not_withheld


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


def public_creator(db: Session, handle: str) -> Creator:
    """The creator behind a public Passport link, if it may be shown.

    Raises ProfileNotFound when there is no such handle, the Passport is not
    published, or the account is suspended: all three look the same from
    outside (D-061), so a stranger learns nothing by trying handles. Raises
    ContentWithheld (451) for a published Passport withheld by a takedown
    (item 52): it was public, and saying why it is gone is the honest answer.
    """
    creator = db.scalars(select(Creator).where(Creator.handle == handle)).first()
    if (
        creator is None
        or not passport_is_public(creator)
        or suspension.is_suspended(db, creator.account_id)
    ):
        raise ProfileNotFound()
    if is_withheld(db, "creator", creator.id):
        raise ContentWithheld()
    return creator


# --- offered to search engines (item 85, D-121) ------------------------------------------


@dataclass(frozen=True)
class IndexablePassport:
    """One published Passport, as the website's sitemap needs it."""

    creator_id: uuid.UUID
    handle: str
    created_at: datetime
    last_modified: datetime


def last_modified_sql() -> ColumnElement[datetime]:
    """When what a Passport's reader sees last changed, worked out in SQL.

    The latest of the profile's own change, its publishing, its channels'
    changes and, only while prices are public, its packages' changes and
    their publishing: the same rule `structured_data.last_modified` applies
    to a Passport already read, which a test holds the two to. A deleted
    channel or package does not move it; Google reads `lastmod` as a hint.
    """
    channels = (
        select(func.max(CreatorChannel.updated_at))
        .where(CreatorChannel.creator_id == Creator.id)
        .scalar_subquery()
    )
    packages = (
        select(func.max(CreatorPackage.updated_at))
        .where(CreatorPackage.creator_id == Creator.id)
        .scalar_subquery()
    )
    prices_public = Creator.rate_card_public_at.is_not(None)
    return func.greatest(
        Creator.updated_at,
        Creator.passport_published_at,
        channels,
        case((prices_public, Creator.rate_card_public_at)),
        case((prices_public, packages)),
    )


def indexable_passports(
    db: Session, *, limit: int, cursor: str | None
) -> Slice[IndexablePassport]:
    """Every Passport the open internet may read, newest first, a keyset page. One query.

    Published, its account not suspended, and not withheld by a takedown:
    exactly the Passports `public_creator` would show. Empty while
    `PASSPORT_INDEXING` is off. Raises InvalidCursor.
    """
    if not settings.passport_indexing:
        return Slice(rows=[], next_cursor=None)
    modified = last_modified_sql().label("last_modified")
    statement = select(Creator.id, Creator.handle, Creator.created_at, modified).where(
        Creator.passport_published_at.is_not(None),
        suspension.account_is_active(Creator.account_id),
        not_withheld("creator", Creator.id),
    )
    if cursor is not None:
        statement = statement.where(
            older_than_cursor(Creator.created_at, Creator.id, cursor)
        )
    rows = db.execute(
        statement.order_by(Creator.created_at.desc(), Creator.id.desc()).limit(limit + 1)
    ).all()
    found = [
        IndexablePassport(
            creator_id=row.id,
            handle=row.handle,
            created_at=row.created_at,
            last_modified=row.last_modified,
        )
        for row in rows
    ]
    return build_slice(found, limit, key=lambda item: (item.created_at, item.creator_id))

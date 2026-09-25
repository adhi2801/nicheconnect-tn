"""A creator's channels and their prices (D-055, proposal section 4).

`docs/COMPETITIVE_LANDSCAPE.md` ranks this first of everything left to build,
for a reason no competitor can copy: **we can put the price next to the
proof.** Collabstr sells packages, YouTube gives every creator a media kit,
Passionfroot sells bookable storefronts — none of them holds the creator's
delivery record (D-038) or the brand's payment record (D-034), so none of
them can show a price and a record of whether the work actually happened on
one screen.

Two tables rather than a JSONB column on `creator`, because these are lists
with rules: a price must be positive, a platform must be one we know, a
creator has one Instagram rather than four. The database enforces what it can
(`database.md` section 3), and fair-rate guidance later needs to query across
them, which JSON makes miserable.

**Nothing here is verified and nothing pretends to be.** Every follower count
is the creator's own claim with the date they made it. About two in three
Indian creators inflate them, so the word "verified" appears nowhere, the
public page links to the channel itself rather than republishing our copy of
a number (D-042), and there is no `source` column until verification exists —
a CHECK listing a value nobody writes is a claim we have not kept.

No `deleted_at`: a removed package is deleted outright, because the retention
answer waits on the validation pack (constraint 6). Revisit when anything
references a package.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY
from app.db.base import Base

# The two platforms Tamil Nadu creators actually work on. Adding one is a
# migration, deliberately: the public page checks the link's domain against
# this, so an unknown platform cannot smuggle an arbitrary URL onto a page.
CHANNEL_PLATFORMS: tuple[str, ...] = ("instagram", "youtube")

# What a package can be. "other" exists so a creator is never blocked by our
# vocabulary, and it is last so nobody reaches for it first.
PACKAGE_FORMATS: tuple[str, ...] = (
    "post",
    "reel",
    "story",
    "short",
    "video",
    "live",
    "other",
)

PROFILE_URL_MAX_LENGTH = 300
PACKAGE_TITLE_MAX_LENGTH = 80
PACKAGE_DESCRIPTION_MAX_LENGTH = 500

# The same ceiling the deal memo uses for usage rights, so a package cannot
# promise something a memo could not then record.
MAX_USAGE_RIGHTS_DAYS = 3650
MAX_DELIVERY_DAYS = 90

# Enforced in the API, not here: a database cannot count rows in a CHECK.
# `position` is capped at 19 so a reordering has room to breathe.
MAX_PACKAGES_PER_CREATOR = 10
MAX_PACKAGE_POSITION = 19


class CreatorChannel(Base):
    """One row per creator per platform. Self-reported, always dated."""

    __tablename__ = "creator_channel"
    __table_args__ = (
        CheckConstraint(
            f"platform IN {CHANNEL_PLATFORMS}", name="platform_allowed"
        ),
        # https only, and the API additionally checks the domain matches the
        # platform: a public page must not carry an arbitrary link.
        CheckConstraint("profile_url LIKE 'https://%'", name="profile_url_https"),
        CheckConstraint("followers >= 0", name="followers_not_negative"),
        CheckConstraint(
            "average_views IS NULL OR average_views >= 0",
            name="average_views_not_negative",
        ),
        # One Instagram, one YouTube. The unique index serves the foreign key.
        UniqueConstraint("creator_id", "platform", name="uq_creator_channel_platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    profile_url: Mapped[str] = mapped_column(
        String(PROFILE_URL_MAX_LENGTH), nullable=False
    )
    followers: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable because plenty of creators genuinely do not know it, and a
    # required field would only teach them to invent one.
    average_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The Tamil Nadu date the creator last stated these numbers. Shown beside
    # them, because a follower count without a date is not a fact.
    figures_as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreatorPackage(Base):
    """One offer: what the creator will make, for how much, by when."""

    __tablename__ = "creator_package"
    __table_args__ = (
        CheckConstraint(f"platform IN {CHANNEL_PLATFORMS}", name="platform_allowed"),
        CheckConstraint(f"format IN {PACKAGE_FORMATS}", name="format_allowed"),
        CheckConstraint("char_length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            f"description IS NULL OR char_length(description) <= "
            f"{PACKAGE_DESCRIPTION_MAX_LENGTH}",
            name="description_length",
        ),
        # Paise, and positive: a free package is not a price, it is a
        # conversation, and zero would quietly break fair-rate guidance later.
        CheckConstraint("price_paise > 0", name="price_positive"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        CheckConstraint(
            f"delivery_days BETWEEN 1 AND {MAX_DELIVERY_DAYS}", name="delivery_days_range"
        ),
        CheckConstraint(
            f"usage_rights_days IS NULL OR usage_rights_days BETWEEN 0 AND "
            f"{MAX_USAGE_RIGHTS_DAYS}",
            name="usage_rights_days_range",
        ),
        CheckConstraint(
            f"position BETWEEN 0 AND {MAX_PACKAGE_POSITION}", name="position_range"
        ),
        # The only query is "this creator's packages, in order", and this
        # serves the foreign key too.
        Index("ix_creator_package_creator_position", "creator_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(PACKAGE_TITLE_MAX_LENGTH), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=CURRENCY
    )
    delivery_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    usage_rights_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

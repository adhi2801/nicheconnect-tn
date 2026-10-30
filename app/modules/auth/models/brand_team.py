import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Team seats for brands (item 13, D-148; docs/PROPOSAL_TEAM_SEATS.md).
#
# The owner is `brand.account_id`, never a row here: ownership is stored
# once. Everyone else who acts for a brand has a `brand_member` row with one
# of these roles. What each role may do is `auth.brand_acts`.
TEAM_ROLES: tuple[str, ...] = ("admin", "campaigns", "finance")
# The roles a person can hold in a brand, the owner included.
BRAND_ROLES: tuple[str, ...] = ("owner", *TEAM_ROLES)
# Live members a brand may have, the owner not counted.
MAX_TEAM_MEMBERS = 20
# An invite not answered in this long lapses.
INVITE_LIFETIME = timedelta(days=7)
FIRST_NAME_MAX_LENGTH = 40
PHONE_HASH_PATTERN = r"^[0-9a-f]{64}$"

_FIRST_NAME_SHAPE = (
    f"char_length(first_name) BETWEEN 1 AND {FIRST_NAME_MAX_LENGTH}"
    " AND first_name = btrim(first_name) AND first_name !~ '[[:cntrl:]]'"
)


class BrandMember(Base):
    """Someone other than the owner who acts for a brand, in one role."""

    __tablename__ = "brand_member"
    __table_args__ = (
        CheckConstraint(f"role IN {TEAM_ROLES}", name="role_allowed"),
        CheckConstraint(_FIRST_NAME_SHAPE, name="first_name_shape"),
        CheckConstraint(
            "removed_at IS NULL OR removed_at >= created_at", name="removed_after_joined"
        ),
        # One live membership per brand and person; a removed one stays, so
        # who acted on an old deal is still known.
        Index(
            "uq_brand_member_live",
            "brand_id",
            "account_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
        # The brand's team, oldest first; its leading column indexes the
        # foreign key, which the partial index above cannot (database.md 5).
        Index("ix_brand_member_brand_id_created_at", "brand_id", "created_at", "id"),
        # The brands a person acts for.
        Index("ix_brand_member_account_id_created_at", "account_id", "created_at", "id"),
        Index("ix_brand_member_invited_by_account_id", "invited_by_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a team means nothing without its brand.
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand.id", ondelete="CASCADE"), nullable=False
    )
    # CASCADE: a membership is the person's own. Erasure ends it first in
    # any case, since accounts are emptied rather than deleted.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # The name creators see beside the brand's ("Sent by Ravi at ..."), as
    # the person gave it when they joined. Never a phone number.
    first_name: Mapped[str] = mapped_column(String(FIRST_NAME_MAX_LENGTH), nullable=False)
    # SET NULL: who invited them outlives that person's account.
    invited_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # They left, or were removed. NULL while they act for the brand.
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BrandInvite(Base):
    """An invitation to join a brand's team, waiting for its number to sign in.

    Only a keyed hash of the invited number is kept, never the number: the
    person was never asked. No message is sent to it; the inviter tells the
    person, and the invite is shown when that number signs in as a brand.
    """

    __tablename__ = "brand_invite"
    __table_args__ = (
        CheckConstraint(f"role IN {TEAM_ROLES}", name="role_allowed"),
        CheckConstraint(_FIRST_NAME_SHAPE, name="first_name_shape"),
        CheckConstraint(f"phone_hash ~ '{PHONE_HASH_PATTERN}'", name="phone_hash_format"),
        CheckConstraint(
            "expires_at > created_at"
            f" AND expires_at <= created_at + interval '{INVITE_LIFETIME.days} days'",
            name="lifetime_within_limit",
        ),
        # An invite ends one way at most: accepted, declined or revoked.
        CheckConstraint(
            "num_nonnulls(accepted_at, declined_at, revoked_at) <= 1",
            name="ends_once",
        ),
        # Who accepted may be forgotten (SET NULL), the fact never alone.
        CheckConstraint(
            "accepted_by_account_id IS NULL OR accepted_at IS NOT NULL",
            name="accepted_by_only_when_accepted",
        ),
        # One open invite per brand and number.
        Index(
            "uq_brand_invite_open",
            "brand_id",
            "phone_hash",
            unique=True,
            postgresql_where=text(
                "accepted_at IS NULL AND declined_at IS NULL AND revoked_at IS NULL"
            ),
        ),
        Index("ix_brand_invite_brand_id_created_at", "brand_id", "created_at", "id"),
        # Found by the number's hash when it signs in.
        Index("ix_brand_invite_phone_hash", "phone_hash"),
        Index("ix_brand_invite_invited_by_account_id", "invited_by_account_id"),
        Index("ix_brand_invite_accepted_by_account_id", "accepted_by_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # The name the inviter knows them by, which they may change on joining.
    first_name: Mapped[str] = mapped_column(String(FIRST_NAME_MAX_LENGTH), nullable=False)
    # HMAC-SHA256 of the E.164 number under its own label (`auth.brand_team`).
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    # The invited person said no. NULL otherwise.
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The brand took it back, or replaced it with a new one once it lapsed.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set from the service's clock, so the lifetime check holds in tests too.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

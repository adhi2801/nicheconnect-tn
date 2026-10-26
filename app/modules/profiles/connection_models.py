"""Connected Instagram and YouTube accounts (item 29, D-134).

A creator connects an account they can sign into; we keep the platform's
own id and handle, the latest follower or subscriber count the platform
reported and when (choice b A: no history), and the tokens to read it
again, encrypted at rest under PLATFORM_TOKEN_KEY (`connection_secrets`).
A token never leaves the database except to the platform that issued it.

`connection_attempt` holds one sign-in in flight: the `state` the platform
hands back, only as its hash, and Google's PKCE verifier, sealed; single
use, 10 minutes. `platform_deletion_request` records each deletion Meta
asked for (its confirmation code and when), which Meta's status page reads;
it holds nothing about the person.

CASCADE on the creator and the account: each row is the person's own.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PLATFORMS: tuple[str, ...] = ("instagram", "youtube")
CONNECTION_STATUSES: tuple[str, ...] = ("active", "expired")
HANDLE_MAX_LENGTH = 100
PLATFORM_USER_ID_MAX_LENGTH = 64
SHA256_HEX_LENGTH = 64
# Meta's confirmation codes are ours to make: 24 url-safe characters.
CONFIRMATION_CODE_LENGTH = 24


class ConnectionAttempt(Base):
    __tablename__ = "connection_attempt"
    __table_args__ = (
        CheckConstraint(f"platform IN {PLATFORMS}", name="platform_allowed"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        # The account's foreign key's index, and its attempts newest first.
        Index("ix_connection_attempt_account_id_created_at", "account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 of the `state` sent to the platform: the value itself is only
    # ever in the person's browser.
    state_sha256: Mapped[str] = mapped_column(
        String(SHA256_HEX_LENGTH), nullable=False, unique=True
    )
    # Google's PKCE verifier, sealed. NULL for Instagram, whose Login does
    # not document PKCE; its code needs our app secret instead.
    code_verifier_sealed: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL until used; a used attempt never completes again.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConnectedAccount(Base):
    __tablename__ = "connected_account"
    __table_args__ = (
        CheckConstraint(f"platform IN {PLATFORMS}", name="platform_allowed"),
        CheckConstraint(f"status IN {CONNECTION_STATUSES}", name="status_allowed"),
        CheckConstraint(
            "verified_followers IS NULL OR verified_followers >= 0",
            name="followers_not_negative",
        ),
        CheckConstraint(
            "(verified_followers IS NULL) = (verified_as_of IS NULL)",
            name="followers_with_their_date",
        ),
        CheckConstraint("char_length(btrim(handle)) > 0", name="handle_not_blank"),
        # One account a platform per creator; also the foreign key's index.
        UniqueConstraint("creator_id", "platform", name="uq_connected_account_creator"),
        # One platform account for one creator: two people cannot both
        # claim a channel.
        UniqueConstraint(
            "platform", "platform_user_id", name="uq_connected_account_platform_user"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creator.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    # The platform's own id for the account, and its handle as it says.
    platform_user_id: Mapped[str] = mapped_column(
        String(PLATFORM_USER_ID_MAX_LENGTH), nullable=False
    )
    handle: Mapped[str] = mapped_column(String(HANDLE_MAX_LENGTH), nullable=False)
    access_token_sealed: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # Google's; Instagram refreshes its access token itself. NULL then.
    refresh_token_sealed: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # When the access token stops working. NULL if the platform did not say.
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'active'")
    )
    # The notice the creator read before connecting (legal.md rule 5).
    notice_version: Mapped[str] = mapped_column(String(40), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # The latest count the platform reported, and when. NULL until read.
    verified_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PlatformDeletionRequest(Base):
    __tablename__ = "platform_deletion_request"
    __table_args__ = (
        CheckConstraint(f"platform IN {PLATFORMS}", name="platform_allowed"),
        CheckConstraint("removed >= 0", name="removed_counted"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    confirmation_code: Mapped[str] = mapped_column(
        String(CONFIRMATION_CODE_LENGTH), nullable=False, unique=True
    )
    # How many connections it removed: 0 when we held none for that person.
    removed: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

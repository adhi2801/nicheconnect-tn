"""Where a person's phones receive push notifications (item 9, D-095).

One row per push token: the address Firebase (Android) or Apple (iPhone,
and a Live Activity on the lock screen) gives an app install, which our push
sender will use once delivery is built (E1). Registering now lets the apps
be built around it.

A token belongs to one account at a time. When a phone changes hands and
the new person signs in, the token moves to them, so the last person's
notifications stop arriving on a phone they no longer hold.

A push token is personal data. It is never logged, never sent in a URL, and
only its platform and dates go in the person's export.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

DEVICE_PLATFORMS: tuple[str, ...] = ("android", "ios", "ios_live_activity")
# Firebase tokens are about 160 characters, Apple's 64 or more hex digits;
# room for both to grow, a ceiling so a row stays small.
TOKEN_MIN_LENGTH = 32
TOKEN_MAX_LENGTH = 1024
TOKEN_PATTERN = r"^[A-Za-z0-9:_.-]+$"  # noqa: S105 - a shape, not a secret
APP_VERSION_MAX_LENGTH = 32
# The most recently seen phones kept per account; registering one more
# forgets the longest unseen. Reinstalls make new tokens, and an account
# with dozens of dead ones would be pushed to dozens of nowhere.
MAX_DEVICES_PER_ACCOUNT = 10


class DeviceToken(Base):
    __tablename__ = "device_token"
    __table_args__ = (
        CheckConstraint(f"platform IN {DEVICE_PLATFORMS}", name="platform_allowed"),
        CheckConstraint(
            f"char_length(token) BETWEEN {TOKEN_MIN_LENGTH} AND {TOKEN_MAX_LENGTH}"
            f" AND token ~ '{TOKEN_PATTERN}'",
            name="token_shape",
        ),
        CheckConstraint(
            f"app_version IS NULL OR char_length(app_version) BETWEEN 1 AND {APP_VERSION_MAX_LENGTH}",
            name="app_version_length",
        ),
        # An account's phones, most recently seen first: for the cap and the
        # sender. Also the index the foreign key needs (database.md section 5).
        Index("ix_device_token_account_id_last_seen_at", "account_id", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a person's own phones go with their account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    # Unique: one install, one owner at a time.
    token: Mapped[str] = mapped_column(
        String(TOKEN_MAX_LENGTH), nullable=False, unique=True
    )
    # The app build that registered it, for knowing what a phone can show.
    # NULL when the app did not say.
    app_version: Mapped[str | None] = mapped_column(
        String(APP_VERSION_MAX_LENGTH), nullable=True
    )
    # When the app last registered it: apps re-register on every start.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

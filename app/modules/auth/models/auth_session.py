import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.config import settings
from app.db.base import Base

# Refresh-token sessions (D-008, D-011). Each refresh rotates the token: the
# old row gets used_at, and a new row joins the same family. Presenting a
# token whose row already has used_at means theft: revoke the whole family.
# Only a SHA-256 of the token is stored, never the token itself.


# An admin can suspend people, read phone numbers and withhold anyone's
# content, so a stolen admin session must be short (D-061, D-105). NIST SP
# 800-63B-4 section 2.2 for AAL2: re-authenticate after at most 1 hour idle,
# and 24 hours overall; we take 12, AAL3's overall limit. Each refresh is
# activity, so an admin at work never notices the first; nobody escapes the
# second, however often they refresh.
ADMIN_IDLE_LIMIT = timedelta(hours=1)
ADMIN_SESSION_LIMIT = timedelta(hours=12)


def refresh_token_expiry(
    role: str, now: datetime, second_factor_at: datetime | None
) -> datetime:
    """When a refresh token issued at `now` stops working.

    Settings decide it for brands and creators (D-008). An admin's lasts an
    hour, and never past 12 hours from the moment both factors were proven.
    """
    if role != "admin":
        return now + timedelta(days=settings.refresh_token_expire_days)
    idle_end = now + ADMIN_IDLE_LIMIT
    if second_factor_at is None:
        return idle_end
    return min(idle_end, second_factor_at + ADMIN_SESSION_LIMIT)


TOKEN_HASH_PATTERN = r"^[0-9a-f]{64}$"  # noqa: S105 - a format check, not a secret


class AuthSession(Base):
    __tablename__ = "auth_session"
    __table_args__ = (
        CheckConstraint(f"token_hash ~ '{TOKEN_HASH_PATTERN}'", name="token_hash_format"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # CASCADE: sessions mean nothing without their account.
    # Indexed for "log out of all devices".
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Groups one login's chain of rotated tokens. Indexed for family revocation.
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Set by the service from its injectable clock (refresh_token_expiry()).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When the login behind this session proved a second factor, carried
    # unchanged through every rotation, so the 12-hour limit counts from the
    # login, not the last refresh (D-105). NULL means one factor: every
    # brand's and creator's session, and no admin's.
    second_factor_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the login behind this session was proven by a passkey, carried
    # through every rotation like `second_factor_at`, so every token of the
    # session says so (D-113). NULL means a phone code.
    passkey_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nullable on purpose: empty until this token is rotated.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nullable on purpose: empty until logout or suspected theft.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

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


# An admin can suspend people and read phone numbers, so a stolen admin
# session must not last a month (D-061).
ADMIN_REFRESH_TOKEN_DAYS = 1


def refresh_token_ttl(role: str) -> timedelta:
    """How long a refresh token lasts. One source: settings (D-008), or a day for admins."""
    if role == "admin":
        return timedelta(days=ADMIN_REFRESH_TOKEN_DAYS)
    return timedelta(days=settings.refresh_token_expire_days)


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
    # Set by the service from its injectable clock (issue time + refresh_token_ttl()).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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

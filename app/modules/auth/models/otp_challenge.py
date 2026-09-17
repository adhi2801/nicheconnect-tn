import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.account import PHONE_PATTERN

# One-time login codes (D-007, D-011). Deliberately not linked to account:
# a code is sent the same way whether or not the number is registered.
# The plain code is never stored, only its HMAC-SHA256 (keyed by OTP_HASH_KEY).

OTP_TTL = timedelta(minutes=5)
MAX_OTP_ATTEMPTS = 5
CODE_HASH_PATTERN = r"^[0-9a-f]{64}$"


class OtpChallenge(Base):
    __tablename__ = "otp_challenge"
    __table_args__ = (
        CheckConstraint(f"phone ~ '{PHONE_PATTERN}'", name="phone_format"),
        CheckConstraint(f"code_hash ~ '{CODE_HASH_PATTERN}'", name="code_hash_format"),
        CheckConstraint(
            f"attempts BETWEEN 0 AND {MAX_OTP_ATTEMPTS}", name="attempts_range"
        ),
        # Latest code for a phone, and send-limit counts per phone.
        Index(
            "ix_otp_challenge_phone_created_at",
            "phone",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    phone: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    # Set by the service from its injectable clock (created time + OTP_TTL).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Nullable on purpose: empty until the code is used (single use).
    consumed_at: Mapped[datetime | None] = mapped_column(
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

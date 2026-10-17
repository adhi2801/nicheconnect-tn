import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.otp_challenge import CODE_HASH_PATTERN, MAX_OTP_ATTEMPTS

# A second check before a risky change (item 82, D-107): a code sent to the
# account's phone, good for one action and, where the action has one, one
# exact new value. A code asked for to set one UPI ID cannot set another
# (the EU's dynamic linking, RTS Article 5, applied to an account change).
#
# Only keyed hashes are kept: the code's (as for login codes, D-011) and the
# value's, so the table never holds the new UPI ID itself.

STEP_UP_ACTIONS: tuple[str, ...] = (
    "set_upi_id",
    "download_export",
    "log_out_everywhere",
    # Moving the account onto a new phone number (item 80, D-108): the
    # value is the new number, so the code cannot move it anywhere else.
    "change_phone",
)
STEP_UP_TTL = timedelta(minutes=5)
MAX_STEP_UP_ATTEMPTS = MAX_OTP_ATTEMPTS
VALUE_HASH_PATTERN = CODE_HASH_PATTERN


class StepUpChallenge(Base):
    __tablename__ = "step_up_challenge"
    __table_args__ = (
        CheckConstraint(f"action IN {STEP_UP_ACTIONS}", name="action_allowed"),
        CheckConstraint(f"value_hash ~ '{VALUE_HASH_PATTERN}'", name="value_hash_format"),
        CheckConstraint(f"code_hash ~ '{CODE_HASH_PATTERN}'", name="code_hash_format"),
        CheckConstraint(
            f"attempts BETWEEN 0 AND {MAX_STEP_UP_ATTEMPTS}", name="attempts_range"
        ),
        CheckConstraint(
            "expires_at = created_at + interval '5 minutes'",
            name="expires_five_minutes_after_created",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="consumed_after_created",
        ),
        # The account's latest code, and the send and guess caps counted per
        # account; its first column also serves the foreign key.
        Index(
            "ix_step_up_challenge_account_id_created_at",
            "account_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a code means nothing without its account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # HMAC-SHA256 of the action and its new value (the empty string for an
    # action without one), keyed by OTP_HASH_KEY.
    value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL until the code is used (single use).
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set by the service from its injectable clock, which the caps read.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

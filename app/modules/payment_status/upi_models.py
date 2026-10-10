"""Where a creator is paid: their UPI ID, given with consent (D-085).

One row per creator, written only when they add one. It is personal data
kept for one purpose: so the brand on a deal can pay them without copying
an ID by hand. It is shown only to that brand, only while a payment is open
(`upi_service.pay_details`).

The money still goes from the brand's bank to the creator's bank; nothing
here receives or moves it (constraint 1).

Kept out of `creator`, so search, matching and the embedding text, which
read that row, never come near it (constraint 2).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# name@handle, as NPCI's linking specification and every UPI app use it.
# Stored lowercase: UPI IDs are not case-sensitive, and one spelling keeps
# comparisons honest. The handle is the payment app's or bank's suffix.
UPI_ID_PATTERN = r"^[a-z0-9._-]{2,64}@[a-z][a-z0-9]{1,63}$"
UPI_ID_MAX_LENGTH = 128
# A UPI ID whose name part is a mobile number gives the number away. NPCI
# asks apps to mask such IDs and to offer a chosen name instead (September
# 2026), and we never show one side's phone number to the other.
PHONE_LIKE_NAME = r"^(91)?[6-9][0-9]{9}$"
NOTICE_VERSION_MAX_LENGTH = 40


class CreatorUpi(Base):
    __tablename__ = "creator_upi"
    __table_args__ = (
        CheckConstraint(f"upi_id ~ '{UPI_ID_PATTERN}'", name="upi_id_format"),
        CheckConstraint(
            f"split_part(upi_id, '@', 1) !~ '{PHONE_LIKE_NAME}'",
            name="upi_id_not_a_phone_number",
        ),
        CheckConstraint(
            "char_length(btrim(notice_version)) > 0", name="notice_version_not_blank"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a person's own detail goes with their profile.
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    upi_id: Mapped[str] = mapped_column(String(UPI_ID_MAX_LENGTH), nullable=False)
    # The consent, as an event (security.md section 7): when it was given,
    # and which version of the notice the creator was shown. Given again on
    # every change of the ID.
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notice_version: Mapped[str] = mapped_column(
        String(NOTICE_VERSION_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

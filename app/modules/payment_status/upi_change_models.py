"""A new UPI ID waiting its 24 hours before brands see it (item 82, D-107).

A code sent to the phone stops a stolen session from changing where a
creator is paid, but not a SIM swap or a hijacked WhatsApp: the code goes to
whoever holds the number. So a new ID waits, as a bank's new payee and a UPI
app's new device do. Until `usable_at`, brands are shown the creator's
previous ID, or none for a first one, and the creator sees the change and
can cancel it.

One row per creator, at most: a second change replaces the first and starts
its 24 hours again. Once `usable_at` has passed, the change is in effect
whether or not this row has been folded into `creator_upi` yet: which ID is
in effect is worked out on read against `now` (`upi_holds.in_effect`), and
the next write folds it in.

The waiting ID is kept with its own consent, given when it was asked for,
under the same rules as `creator_upi`: never a phone number.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.payment_status.upi_models import (
    NOTICE_VERSION_MAX_LENGTH,
    PHONE_LIKE_NAME,
    UPI_ID_MAX_LENGTH,
    UPI_ID_PATTERN,
)

# As long as a UPI app limits a new device (NPCI's convention, as SBI and
# Razorpay describe it, read 17 October 2026), and the same 24 hours the
# brand is already warned for after a change (upi_service.RECENT_CHANGE).
UPI_CHANGE_HOLD = timedelta(hours=24)


class CreatorUpiChange(Base):
    __tablename__ = "creator_upi_change"
    __table_args__ = (
        CheckConstraint(f"upi_id ~ '{UPI_ID_PATTERN}'", name="upi_id_format"),
        CheckConstraint(
            f"split_part(upi_id, '@', 1) !~ '{PHONE_LIKE_NAME}'",
            name="upi_id_not_a_phone_number",
        ),
        CheckConstraint(
            "char_length(btrim(notice_version)) > 0", name="notice_version_not_blank"
        ),
        CheckConstraint(
            "usable_at = consented_at + interval '24 hours'",
            name="usable_a_day_after_consent",
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
    # The consent for this ID, given when the change was asked for.
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notice_version: Mapped[str] = mapped_column(
        String(NOTICE_VERSION_MAX_LENGTH), nullable=False
    )
    # When brands start to see it.
    usable_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""A new phone number waiting its 72 hours before it replaces the old (item 80, D-108).

The phone is the whole login, so changing it is binding a new authenticator
(NIST SP 800-63B-4 section 3.1.3.3): it needs a code from the current number
(a step-up code bound to the new one) and a login code from the new number,
and then it waits. Until `takes_effect_at` the old number still logs in, so
an owner whose number was SIM-swapped can get it back from their carrier,
log in, see the change and cancel it, with no code. A job then moves the
account onto the new number, ends every session and tells the owner; the
old number is let go, so whoever is given it next, once it is recycled
(TRAI: after 90 days), finds a new account, not this one.

One row per account, at most: a second change replaces the first and starts
its 72 hours again. The row is deleted when the change is made or
cancelled, so a past number is never kept. While it waits, no other account
may wait on the same number, and login refuses to make a new account on it.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.account import PHONE_PATTERN

# Upwork's 3-day hold on a new payout method, the closest equivalent risk
# (D-109). In front of it, a change needs a login at least a week old, which
# a SIM swapper never has, so a swap must go unnoticed for about 10 days.
PHONE_CHANGE_WAIT = timedelta(hours=72)


class AccountPhoneChange(Base):
    __tablename__ = "account_phone_change"
    __table_args__ = (
        CheckConstraint(f"new_phone ~ '{PHONE_PATTERN}'", name="new_phone_format"),
        CheckConstraint(
            "takes_effect_at = requested_at + interval '72 hours'",
            name="takes_effect_three_days_after_request",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a waiting change means nothing without its account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Unique: two accounts cannot wait to move onto the same number.
    new_phone: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    # When both codes were given; a replacement starts again from its own.
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    takes_effect_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

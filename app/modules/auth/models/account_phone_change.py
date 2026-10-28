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

Someone whose current number is already gone may ask without its code, from
a login at least 30 days old (D-110): that change waits 7 days, and a login
with the current number meanwhile cancels it.

One row per account, at most: a second change replaces the first and starts
its wait again. The row is deleted when the change is made or
cancelled, so a past number is never kept. While it waits, no other account
may wait on the same number, and login refuses to make a new account on it.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.account import PHONE_PATTERN

# Upwork's 3-day hold on a new payout method, the closest equivalent risk
# (D-109). In front of it, a change needs a login at least a week old, which
# a SIM swapper never has, so a swap must go unnoticed for about 10 days.
PHONE_CHANGE_WAIT = timedelta(hours=72)
# Without a code from the current number (D-110): only from a login at least
# LOST_NUMBER_LOGIN old, and longer, since the owner, if it was not them,
# still holds the number and has only to log in once to cancel it.
PHONE_CHANGE_WAIT_WITHOUT_CURRENT = timedelta(days=7)


def wait_for(without_current_number: bool) -> timedelta:
    """How long a change waits: 7 days without the current number, else 72 hours."""
    return (
        PHONE_CHANGE_WAIT_WITHOUT_CURRENT if without_current_number else PHONE_CHANGE_WAIT
    )


class AccountPhoneChange(Base):
    __tablename__ = "account_phone_change"
    __table_args__ = (
        CheckConstraint(f"new_phone ~ '{PHONE_PATTERN}'", name="new_phone_format"),
        CheckConstraint(
            "takes_effect_at = requested_at + CASE WHEN without_current_number "
            "THEN interval '7 days' ELSE interval '72 hours' END",
            name="takes_effect_after_its_wait",
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
    # Asked for without a code from the current number, which its owner says
    # is lost (D-110): it waits 7 days, and any login with the current number
    # after it was asked for cancels it.
    without_current_number: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

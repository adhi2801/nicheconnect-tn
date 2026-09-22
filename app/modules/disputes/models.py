"""A dispute about a payment: we record it, we do not judge it (D-028).

We hold no money and have no legal standing, so deciding who is right would
create liability we cannot carry and a promise we cannot keep. What we can be
is the honest record-keeper: who raised what, when, what the other side said,
and how it ended. That record is worth more to a marketplace than a verdict
it has no right to give.

**No stored state, for the same reason as `payment_status`.** `unresolved`
is not something anybody does — it is what thirty days of nothing looks like.
Storing it would need a scheduled job, and a row could then say `open` long
after everyone walked away. It is read from the dates instead.

States, all read from the facts:

    open          → raised, still inside the thirty days
    unresolved    → thirty days passed with no outcome. A fact on both
                    records, never a verdict against either side
    resolved_paid        → the money arrived after all
    resolved_withdrawn   → whoever raised it withdrew it
    resolved_informally  → settled between themselves, usually by phone

`resolved_informally` exists because most of these end with a phone call,
and forcing a WhatsApp-native audience to wait out a thirty-day clock for
something already settled would be a worse product than no dispute system
at all.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Either side may raise one: a creator saying the money never came, or a
# brand saying the work was never delivered as agreed.
DISPUTE_PARTIES: tuple[str, ...] = ("brand", "creator")

# Outcomes somebody chooses. `unresolved` is deliberately not here: nobody
# chooses it, so it is derived rather than stored.
DISPUTE_OUTCOMES: tuple[str, ...] = (
    "resolved_paid",
    "resolved_withdrawn",
    "resolved_informally",
)

# The other side has this long to put their account on the record (D-028).
RESPONSE_WINDOW_DAYS = 7
# After this, silence is recorded as silence.
UNRESOLVED_AFTER_DAYS = 30

REASON_MIN_LENGTH = 20
REASON_MAX_LENGTH = 2000


class Dispute(Base):
    """One dispute per payment record."""

    __tablename__ = "dispute"
    __table_args__ = (
        CheckConstraint(
            f"opened_by IN {tuple(DISPUTE_PARTIES)}", name="opened_by_allowed"
        ),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN {tuple(DISPUTE_OUTCOMES)}",
            name="outcome_allowed",
        ),
        # An outcome and the moment it was reached are one fact. Having
        # either without the other would leave a dispute that is closed but
        # undated, or dated but still open.
        CheckConstraint(
            "(outcome IS NULL) = (closed_at IS NULL)",
            name="outcome_matches_closed_at",
        ),
        CheckConstraint(
            f"char_length(btrim(reason)) >= {REASON_MIN_LENGTH}"
            f" AND char_length(reason) <= {REASON_MAX_LENGTH}",
            name="reason_length",
        ),
        # Open disputes, oldest first: the ones somebody is waiting on.
        Index(
            "ix_dispute_open",
            "created_at",
            postgresql_where=text("outcome IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # One per payment record. RESTRICT: a dispute about money must never
    # disappear as a side effect of deleting something else.
    payment_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payment_status.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    opened_by: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Opened plus the response window, in Tamil Nadu's calendar, stored so a
    # later change of policy cannot move a deadline somebody is relying on.
    response_due_on: Mapped[date] = mapped_column(Date, nullable=False)

    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

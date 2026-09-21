"""The record of a payment a brand says it made and a creator confirms (D-027).

NicheConnect TN never receives, pools or holds campaign money. Brands pay
creators directly. This table is the product's memory of that happening: what
was owed, by when, what the brand says it sent, and whether the creator agrees
it arrived.

**There is no status column, and that is deliberate.**

Every other table here stores its status. This one stores only facts —
`due_on`, `marked_paid_at`, `confirmed_at` — and `service.derive_state()`
reads a state out of them against today's date.

The reason is that `late` and `unpaid` are not events anybody causes. Nothing
happens on day 8 except that the day arrives. A stored status would need a
scheduled job to flip it, and we have not chosen a job runner; worse, a row
could then say `due` while a creator has been waiting a month, because a cron
failed quietly. A derived state cannot be stale. It is the same reasoning that
made proof auto-approval lazy rather than scheduled.

The trade is that "show me every late payment" is a query with a `WHERE`
clause rather than an equality check. The partial index below exists for it.

States, all read from the facts:

    due          → not yet paid, on or before due_on
    late         → not yet paid, past due_on
    unpaid       → not yet paid, past due_on + UNPAID_AFTER_DAYS, no dispute
    paid         → brand marked it paid, creator has not confirmed
    confirmed    → creator confirmed it arrived
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY
from app.db.base import Base

# How a brand says it sent the money (D-027). Only UPI carries a reference
# with a fixed machine-checkable shape, which is why only UPI can ever be
# matched automatically; the other two rest on the creator's confirmation.
PAYMENT_METHODS: tuple[str, ...] = ("upi", "bank_transfer", "cash")

# Silence this long after the due date is a different problem from being a
# few days late, so it gets its own, stronger state (D-027).
UNPAID_AFTER_DAYS = 21

# Indian payment references are not one shape: a UPI or IMPS RRN is 12 digits,
# a NEFT UTR is 16 characters, an RTGS UTR is 22. Cash has no formal reference,
# so the field carries whatever note identifies the handover. 32 covers all of
# them; per-method rules live in the service, where they can say something
# useful when they fail.
REFERENCE_MAX_LENGTH = 32


class PaymentStatus(Base):
    """One payment record per deal memo. Never a transfer, only a record."""

    __tablename__ = "payment_status"
    __table_args__ = (
        CheckConstraint(
            f"method IS NULL OR method IN {tuple(PAYMENT_METHODS)}",
            name="method_allowed",
        ),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
        # A claim of payment always says how it was sent and what identifies
        # it. "I paid you" with no method and no reference is not a record.
        CheckConstraint(
            "marked_paid_at IS NULL OR (method IS NOT NULL AND reference IS NOT NULL)",
            name="paid_needs_method_and_reference",
        ),
        # Nobody can confirm receiving money that was never said to be sent.
        CheckConstraint(
            "confirmed_at IS NULL OR marked_paid_at IS NOT NULL",
            name="confirmed_needs_marked_paid",
        ),
        # And it cannot have arrived before it was sent.
        CheckConstraint(
            "confirmed_at IS NULL OR confirmed_at >= marked_paid_at",
            name="confirmed_after_marked_paid",
        ),
        CheckConstraint(
            "reference IS NULL OR char_length(btrim(reference)) > 0",
            name="reference_not_blank",
        ),
        # The hot question this table is asked: who has not been paid, and how
        # overdue are they. Partial, because a settled payment is never the
        # answer to it (database.md section 5).
        Index(
            "ix_payment_status_outstanding",
            "due_on",
            postgresql_where=text("marked_paid_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # One payment record per memo (database.md section 3). RESTRICT, matching
    # deliverable_proof: a record of money moving must never disappear as a
    # side effect of deleting something else.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    # Copied from the memo rather than read through it, so the record stays
    # true to what was agreed even if the memo is later amended.
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=CURRENCY
    )
    # Approval date plus the memo's own payment_due_days, worked out once at
    # creation. Storing the date means a later change of policy cannot move a
    # deadline somebody is already counting on.
    due_on: Mapped[date] = mapped_column(Date, nullable=False)

    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reference: Mapped[str | None] = mapped_column(
        String(REFERENCE_MAX_LENGTH), nullable=True
    )
    # What the brand says. Only the brand may set this (security.md section 2).
    marked_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # What the creator says. Only the creator may set this.
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

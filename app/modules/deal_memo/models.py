import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.taxonomy import CURRENCY
from app.db.base import Base

# What the two sides agreed, for one accepted application (D-024 to D-027).
# One memo per application: the deal is the thing, not the paperwork.
#
# Status flow:
#
#     draft ──send──> sent ──accept──> accepted
#       │              │  ↑                │
#       │              │  └─change_requested (creator asks, brand re-sends)
#       │              └──decline──> declined
#       └──────────────cancel──────────────┴──> cancelled
#
# Cancelling records HOW it ended, which decides whether it counts against
# anyone's record (D-026): before any work was submitted it is withdrawn_early
# and costs nothing.

MEMO_STATUSES: tuple[str, ...] = (
    "draft",
    "sent",
    "change_requested",
    "accepted",
    "declined",
    "cancelled",
)
CANCELLATION_KINDS: tuple[str, ...] = (
    "withdrawn_early",  # no work submitted yet: not counted (D-026)
    "cancelled_by_brand",
    "cancelled_by_creator",
)

# Defaults from D-025 and D-027, stored per memo so changing the policy later
# never rewrites what people already agreed to.
DEFAULT_APPROVAL_WINDOW_DAYS = 7
DEFAULT_PAYMENT_DUE_DAYS = 7
MAX_WINDOW_DAYS = 30
MAX_USAGE_RIGHTS_DAYS = 3650
DELIVERABLES_MAX_LENGTH = 2000
TERMS_MAX_LENGTH = 2000
# The creator's own words when sending a memo back (item 25).
CHANGE_REQUEST_MIN_LENGTH = 5
CHANGE_REQUEST_MAX_LENGTH = 1000


class DealMemo(Base):
    __tablename__ = "deal_memo"
    __table_args__ = (
        CheckConstraint(f"status IN {tuple(MEMO_STATUSES)}", name="status_allowed"),
        CheckConstraint(
            f"cancellation_kind IS NULL OR cancellation_kind IN {tuple(CANCELLATION_KINDS)}",
            name="cancellation_kind_allowed",
        ),
        # A cancellation always says how it ended; nothing else may.
        CheckConstraint(
            "(status = 'cancelled') = (cancellation_kind IS NOT NULL)",
            name="cancellation_kind_matches_status",
        ),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_allowed"),
        # Barter memos carry no fee; a fee, when present, is real money.
        CheckConstraint(
            "fee_amount_paise IS NULL OR fee_amount_paise > 0", name="fee_positive"
        ),
        CheckConstraint(
            "cancellation_fee_paise >= 0", name="cancellation_fee_not_negative"
        ),
        CheckConstraint(
            f"approval_window_days BETWEEN 1 AND {MAX_WINDOW_DAYS}",
            name="approval_window_range",
        ),
        CheckConstraint(
            f"payment_due_days BETWEEN 1 AND {MAX_WINDOW_DAYS}", name="payment_due_range"
        ),
        CheckConstraint(
            f"usage_rights_days IS NULL"
            f" OR usage_rights_days BETWEEN 1 AND {MAX_USAGE_RIGHTS_DAYS}",
            name="usage_rights_range",
        ),
        CheckConstraint("revision_count >= 0", name="revision_count_not_negative"),
        CheckConstraint(
            "char_length(btrim(deliverables)) > 0"
            f" AND char_length(deliverables) <= {DELIVERABLES_MAX_LENGTH}",
            name="deliverables_length",
        ),
        CheckConstraint(
            f"extra_terms IS NULL OR char_length(extra_terms) <= {TERMS_MAX_LENGTH}",
            name="extra_terms_length",
        ),
        # A decline has a date, and nothing else does (item 24). Memos declined
        # before the column existed keep it empty: a date is never invented.
        CheckConstraint(
            "declined_at IS NULL OR status = 'declined'",
            name="declined_at_only_if_declined",
        ),
        # Only a memo that was sent back carries the creator's words (item 25).
        CheckConstraint(
            "change_request_message IS NULL OR (revision_count > 0"
            " AND char_length(btrim(change_request_message))"
            f" BETWEEN {CHANGE_REQUEST_MIN_LENGTH} AND {CHANGE_REQUEST_MAX_LENGTH})",
            name="change_request_message_needs_request",
        ),
        # The brand's and creator's memo lists, newest first.
        Index("ix_deal_memo_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # One memo per application (database.md section 3), and neither side can be
    # deleted out from under the record.
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    deliverables: Mapped[str] = mapped_column(Text, nullable=False)
    # Paise (D-015). Empty for barter, where the payment is goods.
    fee_amount_paise: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text(f"'{CURRENCY}'")
    )
    # Recorded, never collected by us (D-026).
    cancellation_fee_paise: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    # Agreed windows, kept per memo so a later policy change cannot rewrite
    # what these two people agreed (D-025, D-027).
    approval_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text(str(DEFAULT_APPROVAL_WINDOW_DAYS))
    )
    payment_due_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text(str(DEFAULT_PAYMENT_DUE_DAYS))
    )
    # How long the brand may use the content. Empty means not agreed.
    usage_rights_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # The creator confirms the ad disclosure when submitting proof; whether the
    # wording is compliant is an ASCI question for the validation pack.
    disclosure_required: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("true")
    )
    extra_terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'")
    )
    # Only one change request restarts the approval clock (D-025).
    revision_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set by the first draft, script or proof: the line between a cancellation
    # that counts and one that does not (D-026).
    work_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # When the creator declined. NULL on any other memo, and on memos declined
    # before 12 October 2026, when it was first kept (item 24).
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # What the creator asked to change, in their words: the latest request,
    # kept after the brand sends the memo again so both can see what was
    # asked. NULL until a request, and on requests made before it was kept.
    change_request_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

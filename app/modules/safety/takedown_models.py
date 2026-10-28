"""One item withheld by an admin, on a legal order or a report (item 52, D-104).

The IT Rules, as amended on 10 February 2026, give a platform 3 hours from a
court order, or a government notice from an authorised officer, to remove or
disable access to the content it names (rule 3(1)(d), legal.md section 3.3).
Suspending the whole account was the only tool before: too blunt when the
order names one campaign. A takedown withholds exactly one item, a creator's
profile, a brand or a campaign, the three things a report can name:

- everyone else stops seeing it, and opening it answers 451, "Unavailable
  For Legal Reasons" (RFC 7725), as GitHub does;
- its owner keeps their account and still sees it; deals already agreed
  carry on, as for a suspension (D-061).

**The row is the record the law asks us to keep.** Rule 3(1)(g) keeps
removed content and its records for 180 days, so `preserved` holds the
item's visible text as it stood when it was withheld: an edit afterwards
cannot destroy the evidence. The app's own database login may add and lift
takedowns, never delete one (the migration revokes it).

Who withheld and lifted it are on the row; why is in the sealed admin log.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# The three things a report can name (admin's REPORT_SUBJECTS, held equal at
# import by admin/schemas.py: this layer cannot import that one).
TAKEDOWN_SUBJECTS: tuple[str, ...] = ("creator", "brand", "campaign")
# court_order and government_notice: rule 3(1)(d), 3 hours. report: an admin
# withholding a reported item while the report's own clock runs (item 51).
TAKEDOWN_BASES: tuple[str, ...] = ("court_order", "government_notice", "report")
ORDER_TEXT_MAX_LENGTH = 200
PRESERVED_MAX_LENGTH = 20_000


class Takedown(Base):
    __tablename__ = "takedown"
    __table_args__ = (
        CheckConstraint(
            f"subject_kind IN {TAKEDOWN_SUBJECTS}", name="subject_kind_allowed"
        ),
        CheckConstraint(f"basis IN {TAKEDOWN_BASES}", name="basis_allowed"),
        # An order names who issued it and its number; a report-based
        # takedown has neither, and nothing to seal.
        CheckConstraint(
            "(basis = 'report') = (issued_by IS NULL)"
            " AND (basis = 'report') = (order_reference IS NULL)"
            " AND (basis <> 'report' OR legal_provision IS NULL)"
            " AND (basis <> 'report' OR NOT reference_sealed)",
            name="order_details_only_for_orders",
        ),
        # Rule 3(1)(d): 3 hours from receiving the order.
        CheckConstraint(
            "basis = 'report' OR due_at = received_at + interval '3 hours'",
            name="order_due_in_three_hours",
        ),
        # A report keeps its own clock (item 51): at most 7 days.
        CheckConstraint(
            "basis <> 'report'"
            " OR (due_at > received_at AND due_at <= received_at + interval '7 days')",
            name="report_due_within_seven_days",
        ),
        # Received before it was acted on; an order at most 30 days before,
        # so a mistyped year cannot make a late takedown look on time.
        CheckConstraint(
            "received_at <= withheld_at"
            " AND (basis = 'report' OR received_at >= withheld_at - interval '30 days')",
            name="received_before_withheld",
        ),
        CheckConstraint(
            "(lifted_at IS NULL) = (lifted_by_account_id IS NULL)",
            name="lifted_by_someone",
        ),
        CheckConstraint(
            "lifted_at IS NULL OR lifted_at >= withheld_at", name="lifted_after_withheld"
        ),
        CheckConstraint(
            f"issued_by IS NULL OR char_length(issued_by) BETWEEN 3 AND {ORDER_TEXT_MAX_LENGTH}",
            name="issued_by_length",
        ),
        CheckConstraint(
            "order_reference IS NULL OR char_length(order_reference)"
            f" BETWEEN 1 AND {ORDER_TEXT_MAX_LENGTH}",
            name="order_reference_length",
        ),
        CheckConstraint(
            "legal_provision IS NULL OR char_length(legal_provision)"
            f" BETWEEN 3 AND {ORDER_TEXT_MAX_LENGTH}",
            name="legal_provision_length",
        ),
        CheckConstraint(
            "jsonb_typeof(preserved) = 'object'"
            f" AND char_length(preserved::text) <= {PRESERVED_MAX_LENGTH}",
            name="preserved_small_object",
        ),
        # One active takedown per item, and the index every "is it withheld?"
        # condition reads (takedowns.py).
        Index(
            "uq_takedown_active_subject",
            "subject_kind",
            "subject_id",
            unique=True,
            postgresql_where=text("lifted_at IS NULL"),
        ),
        # An owner's own takedowns, newest first (GET /me/takedowns).
        Index(
            "ix_takedown_owner_account_id_created_at", "owner_account_id", "created_at"
        ),
        # The admin list, newest first.
        Index("ix_takedown_created_at", "created_at"),
        # Every foreign key indexed (database.md section 5).
        Index("ix_takedown_withheld_by_account_id", "withheld_by_account_id"),
        Index(
            "ix_takedown_lifted_by_account_id",
            "lifted_by_account_id",
            postgresql_where=text("lifted_by_account_id IS NOT NULL"),
        ),
        Index(
            "ix_takedown_report_id",
            "report_id",
            postgresql_where=text("report_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    subject_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # No foreign keys to the item or its owner: the record must outlive both
    # for as long as the law keeps it, like the admin log.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    basis: Mapped[str] = mapped_column(String(20), nullable=False)
    # The court, or the authority and its officer's designation. NULL for a
    # report-based takedown.
    issued_by: Mapped[str | None] = mapped_column(
        String(ORDER_TEXT_MAX_LENGTH), nullable=True
    )
    # The order's or notice's number. NULL for a report-based takedown.
    order_reference: Mapped[str | None] = mapped_column(
        String(ORDER_TEXT_MAX_LENGTH), nullable=True
    )
    # The law it cites, where it cites one. NULL when it names none.
    legal_provision: Mapped[str | None] = mapped_column(
        String(ORDER_TEXT_MAX_LENGTH), nullable=True
    )
    # True when the order may not be shown to the owner (a sealed order).
    reference_sealed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # SET NULL: if the reporter's account goes, the takedown stays. NULL
    # otherwise means it was not linked to a report.
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="SET NULL"), nullable=True
    )
    # When the order reached us (as the admin read it from the order), or
    # the report was filed. The clock runs from here.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set by the server when the admin acts: never typed, so never backdated.
    withheld_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # RESTRICT, both: an admin who acted can never be deleted out from under it.
    withheld_by_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    # NULL means still withheld.
    lifted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lifted_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    # The item's visible text when it was withheld (rule 3(1)(g)).
    preserved: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

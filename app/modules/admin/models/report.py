"""Users flagging a creator, a brand or a campaign for an admin to look at (D-061).

Each report carries the deadline the IT Rules give it (item 51,
report_clocks.py), fixed when it is filed, and when the admins were warned
that it was due soon and that it was late.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.auth.models.account import REPORT_CATEGORIES

REPORT_SUBJECTS: tuple[str, ...] = ("creator", "brand", "campaign")
REPORT_STATUSES: tuple[str, ...] = ("open", "actioned", "dismissed")
NOTE_MAX_LENGTH = 1000


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint(
            f"subject_kind IN {REPORT_SUBJECTS}", name="subject_kind_allowed"
        ),
        CheckConstraint(f"category IN {REPORT_CATEGORIES}", name="category_allowed"),
        CheckConstraint(f"status IN {REPORT_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"note IS NULL OR char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"
        ),
        CheckConstraint(
            f"resolution_note IS NULL OR char_length(resolution_note) <= {NOTE_MAX_LENGTH}",
            name="resolution_note_length",
        ),
        # Resolved exactly when it is no longer open.
        CheckConstraint(
            "(status = 'open') = (resolved_at IS NULL)", name="resolved_when_closed"
        ),
        # One open report per person per subject: a second is the same report.
        Index(
            "uq_report_open_per_reporter",
            "reporter_account_id",
            "subject_kind",
            "subject_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        # A deadline after filing, and never later than the law's longest
        # clock, 7 days (report_clocks.LONGEST), whatever the code does.
        CheckConstraint(
            "due_at > created_at AND due_at <= created_at + interval '7 days'",
            name="due_within_seven_days",
        ),
        # Warned that it is late only once it is.
        CheckConstraint(
            "overdue_alerted_at IS NULL OR overdue_alerted_at > due_at",
            name="overdue_alert_once_due",
        ),
        # The admin queue, nearest deadline first; and the alert job's search
        # for open reports due soon (item 51).
        Index("ix_report_status_due_at", "status", "due_at"),
        # A reporter's own reports, newest first, and the foreign key: the
        # open-only index above cannot find a closed report (item 98).
        Index("ix_report_reporter_created_at", "reporter_account_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a report is the reporter's own statement; it goes with them.
    reporter_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    subject_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # No foreign key: it points into one of three tables, named by subject_kind.
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'open'")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The deadline under the IT Rules, from the category, when it was filed.
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL means the admins were not warned (yet): it was answered first.
    due_soon_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL means it never went past its deadline unanswered (yet).
    overdue_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""Everything an admin did, and every look at someone's phone number (D-061).

Append-only: the database refuses UPDATE, DELETE and TRUNCATE (the migration
adds the trigger), like the deal record. No `updated_at`, for the same reason.
It is how a founder can answer "who looked at my number, and why?".
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

ADMIN_ACTIONS: tuple[str, ...] = ("view_account", "suspend", "restore", "resolve_report")
NOTE_MAX_LENGTH = 1000


class AdminAction(Base):
    __tablename__ = "admin_action"
    __table_args__ = (
        CheckConstraint(f"action IN {ADMIN_ACTIONS}", name="action_allowed"),
        CheckConstraint(
            f"note IS NULL OR char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"
        ),
        Index("ix_admin_action_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # RESTRICT: an admin who acted can never be deleted out from under the log.
    admin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # No foreign keys: the log outlives what it points at.
    subject_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

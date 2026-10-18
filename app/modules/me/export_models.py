"""A data export asked for, built in the background, downloaded once (D-111).

Building an export reads every table an account appears in, so it grows with
the account's whole history and no fixed time budget can hold it in a
request. As GitHub and Google do, the person asks, a job builds the file, and
they are told when it is ready. The file itself is never in the database: it
is stored encrypted (the bucket's own KMS key) under `exports/<id>.json`,
handed over once, and destroyed then, or after EXPORT_KEPT_FOR unclaimed.

What a row is in is worked out from its times, never stored as a status:
preparing (no `ready_at`, no `failed_at`), failed, ready, downloaded, or
expired (ready, never downloaded, `expires_at` passed).
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Long enough to come back for it the same day; short enough that a copy of
# someone's whole record does not sit in storage.
EXPORT_KEPT_FOR = timedelta(hours=24)


class DataExport(Base):
    __tablename__ = "data_export"
    __table_args__ = (
        # Ready means a file, its size and when it goes, all together.
        CheckConstraint(
            "(ready_at IS NULL) = (expires_at IS NULL)"
            " AND (ready_at IS NULL) = (size_bytes IS NULL)",
            name="ready_has_a_file",
        ),
        CheckConstraint(
            "expires_at IS NULL OR expires_at = ready_at + interval '24 hours'",
            name="expires_a_day_after_ready",
        ),
        CheckConstraint("size_bytes IS NULL OR size_bytes > 0", name="size_positive"),
        CheckConstraint(
            "ready_at IS NULL OR ready_at >= requested_at", name="ready_after_asked"
        ),
        CheckConstraint(
            "downloaded_at IS NULL OR (ready_at IS NOT NULL AND downloaded_at >= ready_at"
            " AND downloaded_at < expires_at)",
            name="downloaded_while_ready",
        ),
        CheckConstraint(
            "failed_at IS NULL OR (ready_at IS NULL AND failed_at >= requested_at)",
            name="failed_never_ready",
        ),
        CheckConstraint(
            "file_deleted_at IS NULL OR ready_at IS NOT NULL",
            name="deleted_only_once_made",
        ),
        # At most one being prepared per account; it also serves the
        # job's search for work.
        Index(
            "uq_data_export_one_preparing",
            "account_id",
            unique=True,
            postgresql_where=text("ready_at IS NULL AND failed_at IS NULL"),
        ),
        # The account's exports, newest first; its first column serves the
        # foreign key.
        Index(
            "ix_data_export_account_id_requested_at",
            "account_id",
            text("requested_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a person's own copy goes with their account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # NULL while it is being prepared, and for one that failed.
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL until ready; then ready_at + EXPORT_KEPT_FOR.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL until ready: the file's size, in bytes.
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL until the one download.
    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL unless building it failed; then it is never ready.
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL while the file is stored: set when it is downloaded or expires.
    file_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def object_key(export_id: uuid.UUID) -> str:
    """Where the file is stored: a random id under its own prefix."""
    return f"exports/{export_id}.json"

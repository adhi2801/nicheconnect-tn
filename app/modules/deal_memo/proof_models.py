import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# The creator's evidence that the work was done (D-024).
#
# The public link is the primary evidence, because only re-checking it proves
# the post stayed up. Media attachments (a screenshot for static posts, a short
# screen recording for video and Stories) wait for the storage decision; the
# columns for them are deliberately not here yet rather than half-built.
#
#     submitted ──approve──> approved        (by the brand, or by time: D-025)
#         └──request revision──> revision_requested ──(new submission)

PROOF_STATUSES: tuple[str, ...] = ("submitted", "approved", "revision_requested")
# Formats decide what evidence is needed once attachments exist.
PROOF_FORMATS: tuple[str, ...] = ("post", "reel", "story", "video", "other")
URL_MAX_LENGTH = 500
NOTE_MAX_LENGTH = 1000


class DeliverableProof(Base):
    __tablename__ = "deliverable_proof"
    __table_args__ = (
        CheckConstraint(f"status IN {tuple(PROOF_STATUSES)}", name="status_allowed"),
        CheckConstraint(f"format IN {tuple(PROOF_FORMATS)}", name="format_allowed"),
        # A public link, and nothing that is not one.
        CheckConstraint(
            f"content_url ~ '^https://' AND char_length(content_url) <= {URL_MAX_LENGTH}",
            name="content_url_https",
        ),
        CheckConstraint(
            f"note IS NULL OR char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"
        ),
        CheckConstraint(
            f"revision_note IS NULL OR char_length(revision_note) <= {NOTE_MAX_LENGTH}",
            name="revision_note_length",
        ),
        # Approval always has a time, and only an approval has one.
        CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL)",
            name="approved_at_matches_status",
        ),
        # Automatic approval is a kind of approval, never anything else.
        CheckConstraint(
            "NOT auto_approved OR status = 'approved'", name="auto_approved_is_approved"
        ),
        # One submission awaiting review per memo: a creator fixes and resubmits,
        # they do not queue up parallel attempts.
        Index(
            "uq_deliverable_proof_open",
            "deal_memo_id",
            unique=True,
            postgresql_where=text("status = 'submitted'"),
        ),
        Index("ix_deliverable_proof_memo_created_at", "deal_memo_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # RESTRICT: proof is the record of work done, so the memo stays with it.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content_url: Mapped[str] = mapped_column(String(URL_MAX_LENGTH), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The creator's own statement that the ad disclosure is on the post.
    # Whether the wording is compliant is an ASCI question (validation pack).
    disclosure_confirmed: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'submitted'")
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # True when the approval window ran out rather than the brand approving.
    auto_approved: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    revision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when a link check finds the post gone (D-024, D-030).
    content_removed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

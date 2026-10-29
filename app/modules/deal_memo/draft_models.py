import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# A draft of the content, shown to the brand before it is posted (item 27,
# D-140). Only on a memo whose agreed terms say `draft_review`: proof cannot
# be submitted until a draft is approved.
#
#     submitted ──approve──> approved        (by the brand, or by time: D-025)
#         └──request changes──> changes_requested ──(a new draft)
#
# The brand has the memo's approval window to answer, on proof's own clock
# (`review_clock`), so a brand that goes silent cannot hold the creator up.
DRAFT_STATUSES: tuple[str, ...] = ("submitted", "approved", "changes_requested")
# The caption or the script: what will be posted, in words.
BODY_MAX_LENGTH = 5000
NOTE_MAX_LENGTH = 1000
URL_MAX_LENGTH = 500


class ContentDraft(Base):
    __tablename__ = "content_draft"
    __table_args__ = (
        CheckConstraint(f"status IN {DRAFT_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"char_length(btrim(body)) BETWEEN 1 AND {BODY_MAX_LENGTH}",
            name="body_length",
        ),
        # A link to the draft itself (a video on Drive, say), and nothing
        # that is not one.
        CheckConstraint(
            "content_url IS NULL OR (content_url ~ '^https://'"
            f" AND char_length(content_url) <= {URL_MAX_LENGTH})",
            name="content_url_https",
        ),
        CheckConstraint(
            f"note IS NULL OR char_length(note) <= {NOTE_MAX_LENGTH}", name="note_length"
        ),
        # The brand's reason, exactly when it asked for changes.
        CheckConstraint(
            "(status = 'changes_requested') = (changes_note IS NOT NULL)",
            name="changes_note_matches_status",
        ),
        CheckConstraint(
            f"changes_note IS NULL OR char_length(btrim(changes_note))"
            f" BETWEEN 5 AND {NOTE_MAX_LENGTH}",
            name="changes_note_length",
        ),
        # Approval always has a time, and only an approval has one.
        CheckConstraint(
            "(status = 'approved') = (approved_at IS NOT NULL)",
            name="approved_at_matches_status",
        ),
        # Answered exactly when it no longer waits: by the brand, or by the
        # clock at its deadline. What the brand's waiting is measured by.
        CheckConstraint(
            "(status = 'submitted') = (answered_at IS NULL)",
            name="answered_at_matches_status",
        ),
        # Approval by the clock is a kind of approval, never anything else.
        CheckConstraint(
            "NOT auto_approved OR status = 'approved'", name="auto_approved_is_approved"
        ),
        # Which attempt this is, counted from 1: rounds of changes are seen.
        CheckConstraint("round >= 1", name="round_positive"),
        # Images become viewable once cleaned, never before the draft was shown,
        # and nothing is approved that the brand could not yet open (piece 2).
        CheckConstraint(
            "images_ready_at IS NULL OR images_ready_at >= created_at",
            name="images_ready_after_shown",
        ),
        CheckConstraint(
            "status <> 'approved' OR images_ready_at IS NOT NULL",
            name="approved_when_images_ready",
        ),
        # One draft waiting for the brand per memo, as with proof.
        Index(
            "uq_content_draft_open",
            "deal_memo_id",
            unique=True,
            postgresql_where=text("status = 'submitted'"),
        ),
        # One approved draft per memo: once approved, the work goes ahead.
        Index(
            "uq_content_draft_approved",
            "deal_memo_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
        # Each attempt has its own number. Also the foreign key's index, and
        # how a memo's drafts are read in order.
        Index("uq_content_draft_round", "deal_memo_id", "round", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # RESTRICT: what was shown and approved is part of the deal's record.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    round: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_url: Mapped[str | None] = mapped_column(String(URL_MAX_LENGTH), nullable=True)
    # The creator's own words beside the draft.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'submitted'")
    )
    # What the brand asked to change.
    changes_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the brand answered, or the clock did (its deadline).
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When every image on the draft was cleaned or refused, so the brand
    # could open what there was to see; the moment it was shown for a draft
    # without images. NULL while any image is still being cleaned: the
    # brand's 2-day minimum counts from here, and nothing approves before it.
    images_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # True when the window ran out rather than the brand approving.
    auto_approved: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

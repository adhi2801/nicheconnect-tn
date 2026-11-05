import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A campaign brief drafted by Claude from a brand's own words (item 40, D-156).
# The brand asks; a job drafts it out of the request (CLAUDE.md section 3: a
# request never waits on an outside call); the brand reads the draft and, if
# it likes it, creates the campaign itself. Nothing here is a campaign.
BRIEF_STATUSES: tuple[str, ...] = ("waiting", "ready", "failed")
IDEA_MIN_LENGTH = 20
IDEA_MAX_LENGTH = 1500
# Kept a week: long enough to come back to, short enough to hold little.
BRIEF_KEPT_DAYS = 7


class CampaignBriefDraft(Base):
    __tablename__ = "campaign_brief_draft"
    __table_args__ = (
        CheckConstraint(f"status IN {BRIEF_STATUSES}", name="status_allowed"),
        CheckConstraint(
            f"char_length(idea) BETWEEN {IDEA_MIN_LENGTH} AND {IDEA_MAX_LENGTH}",
            name="idea_length",
        ),
        # A draft exactly when ready; a reason exactly when failed.
        CheckConstraint(
            "(status = 'ready') = (draft IS NOT NULL)", name="draft_when_ready"
        ),
        CheckConstraint(
            "(status = 'failed') = (failure IS NOT NULL)", name="failure_when_failed"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="attempts_bounded"),
        # The brand's own list, newest first.
        Index("ix_campaign_brief_draft_brand_id_created_at", "brand_id", "created_at"),
        # The job's queue: only the drafts still waiting.
        Index(
            "ix_campaign_brief_draft_waiting",
            "created_at",
            postgresql_where=text("status = 'waiting'"),
        ),
        Index(
            "ix_campaign_brief_draft_requested_by_account_id", "requested_by_account_id"
        ),
        # The daily ceiling counts drafts made in the last 24 hours.
        Index(
            "ix_campaign_brief_draft_drafted_at",
            "drafted_at",
            postgresql_where=text("drafted_at IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a draft means nothing without its brand.
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL: who on the team asked outlives their account.
    requested_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="SET NULL"), nullable=True
    )
    # The brand's own words: what it wants made. Sent to the model, never shown to anyone else.
    idea: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="waiting"
    )
    # The drafted fields, shaped as a campaign is created (CampaignCreate).
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    failure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drafted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

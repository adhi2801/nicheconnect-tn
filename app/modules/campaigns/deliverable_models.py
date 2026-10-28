"""Deliverables as a list (item 26, D-127): what a campaign asks for, one row each.

"2 Instagram reels and a story" as rows a reader can count: a platform, a
format from the rate card's own words (D-055), how many, and a short note.
The free-text `deliverables` field stays, as the summary both sides read
(choice 3A). A campaign's list pre-fills the memo's (choice 1A); the memo's
own list is what both sides agree and the deal record seals
(`deal_memo.deliverable_models`). Proof still works per deal (choice 2B).

CASCADE on the campaign: the brief's own lines. Campaigns are never deleted
in practice (applications hold them), so nothing is lost.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.profiles.models import CHANNEL_PLATFORMS, PACKAGE_FORMATS

# Shared with memos: one vocabulary for what is asked and what is agreed.
DELIVERABLE_PLATFORMS = CHANNEL_PLATFORMS
DELIVERABLE_FORMATS = PACKAGE_FORMATS
MAX_DELIVERABLES = 10
MAX_DELIVERABLE_QUANTITY = 20
DELIVERABLE_NOTE_MAX_LENGTH = 200


def deliverable_checks() -> tuple[CheckConstraint, ...]:
    """The rules every deliverable row holds, on campaigns and memos alike."""
    return (
        CheckConstraint(f"platform IN {DELIVERABLE_PLATFORMS}", name="platform_allowed"),
        CheckConstraint(f"format IN {DELIVERABLE_FORMATS}", name="format_allowed"),
        CheckConstraint(
            f"quantity BETWEEN 1 AND {MAX_DELIVERABLE_QUANTITY}", name="quantity_range"
        ),
        CheckConstraint(
            f"position BETWEEN 0 AND {MAX_DELIVERABLES - 1}", name="position_range"
        ),
        CheckConstraint(
            f"note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND {DELIVERABLE_NOTE_MAX_LENGTH}",
            name="note_length",
        ),
    )


class CampaignDeliverable(Base):
    __tablename__ = "campaign_deliverable"
    __table_args__ = (
        *deliverable_checks(),
        # One row a place; also the foreign key's index.
        UniqueConstraint("campaign_id", "position", name="uq_campaign_deliverable_place"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    # Where it sits in the list, from 0: the order the brand wrote it.
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # A few words: "60 seconds, in Tamil". NULL when there are none.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

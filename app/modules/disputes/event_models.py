"""The evidence timeline: what each side put on the record, and when (D-028).

A dispute is not a verdict, so what it holds is not evidence *for* a finding.
It is a dated account from both sides that either of them can export and take
wherever they need to — to the other party, to a lawyer, to nobody at all.

Timestamps are the whole point. An account given on the day is worth more
than one given a month later, and the order in which two people said things
is often the only thing anybody can agree on afterwards.

**Attachments are links, not files, for now.** D-028 expects screenshots to
join the timeline, and where uploaded files live is still an open decision.
Rather than guess at storage we cannot change later, an entry carries a link
the person already has. When media storage is decided, a file reference
joins this table beside the link; nothing here has to move.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.disputes.models import DISPUTE_PARTIES

# What an entry is. `opened` and `closed` are written by the service so the
# timeline reads as a whole story rather than starting mid-conversation.
EVENT_KINDS: tuple[str, ...] = ("opened", "response", "evidence", "closed")

NOTE_MAX_LENGTH = 2000
URL_MAX_LENGTH = 500


class DisputeEvent(Base):
    """One dated entry on a dispute's timeline."""

    __tablename__ = "dispute_event"
    __table_args__ = (
        CheckConstraint(f"kind IN {tuple(EVENT_KINDS)}", name="kind_allowed"),
        CheckConstraint(
            f"actor_role IN {tuple(DISPUTE_PARTIES)}", name="actor_role_allowed"
        ),
        # An entry that says nothing and shows nothing is not a record.
        CheckConstraint(
            "note IS NOT NULL OR evidence_url IS NOT NULL", name="says_something"
        ),
        CheckConstraint(
            f"note IS NULL OR (char_length(btrim(note)) > 0"
            f" AND char_length(note) <= {NOTE_MAX_LENGTH})",
            name="note_length",
        ),
        CheckConstraint(
            "evidence_url IS NULL OR evidence_url LIKE 'https://%'",
            name="evidence_url_is_https",
        ),
        Index("ix_dispute_event_dispute_created_at", "dispute_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # CASCADE: an entry means nothing without the dispute it belongs to.
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dispute.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_role: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(
        String(URL_MAX_LENGTH), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

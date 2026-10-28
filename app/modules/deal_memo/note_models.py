"""Deal notes: what the two sides said about a deal, on the record (item 17, D-128).

In place of a chat whose messages prove nothing: once a memo is sent,
either party writes a plain note, and each is sealed onto the deal record
as a `note_added` entry carrying its fingerprint (`record_service`), so
"what was said" can be proven later, by either side, from their export.

**Sealed like the deal record and dispute events** (D-057, item 99): the
database refuses any UPDATE, DELETE or TRUNCATE by trigger, and the app's
own login may only read and add (D-100). A note once written stays as
written; a correction is another note. Hence no `updated_at`.

RESTRICT on the memo: a record of what was said, which must never vanish
as a side effect.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

NOTE_SIDES: tuple[str, ...] = ("brand", "creator")
NOTE_MAX_LENGTH = 1000


class DealNote(Base):
    __tablename__ = "deal_note"
    __table_args__ = (
        CheckConstraint(f"author_side IN {NOTE_SIDES}", name="author_side_allowed"),
        CheckConstraint(
            f"char_length(btrim(body)) BETWEEN 1 AND {NOTE_MAX_LENGTH}",
            name="body_length",
        ),
        # A deal's thread, newest first, and the foreign key's index.
        Index("ix_deal_note_deal_memo_id_created_at", "deal_memo_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Which party wrote it. Each side of a deal is one account, so the side
    # says who, without a second link to the account.
    author_side: Mapped[str] = mapped_column(String(10), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

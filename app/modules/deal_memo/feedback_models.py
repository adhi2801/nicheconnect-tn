"""Feedback on a finished deal (item 77, D-136): one answer from each side.

Three scores, 1 to 5 (`feedback_rules.SCORES`), and an optional note.
Written once and never changed: the table refuses UPDATE, DELETE and
TRUNCATE by trigger and the app's role may only read and add, like the deal
record (D-057, D-100). Each answer is sealed onto the deal record by its
fingerprint too. `window_ends_at` is fixed when it is written, so whether it
may be seen is worked out on read (`feedback_rules.revealed`), and nothing
sealed ever needs changing.

ON DELETE RESTRICT on the memo: what each side said must never vanish as a
side effect.
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.deal_memo.feedback_rules import SCORE_MAX, SCORE_MIN

FEEDBACK_SIDES: tuple[str, ...] = ("brand", "creator")
FEEDBACK_NOTE_MAX_LENGTH = 500


def _score(name: str) -> CheckConstraint:
    return CheckConstraint(
        f"{name} BETWEEN {SCORE_MIN} AND {SCORE_MAX}", name=f"{name}_in_range"
    )


class DealFeedback(Base):
    __tablename__ = "deal_feedback"
    __table_args__ = (
        CheckConstraint(f"author_side IN {FEEDBACK_SIDES}", name="author_side_allowed"),
        _score("brief"),
        _score("reliability"),
        _score("easy"),
        CheckConstraint(
            f"note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND {FEEDBACK_NOTE_MAX_LENGTH}",
            name="note_length",
        ),
        CheckConstraint("window_ends_at > created_at", name="window_after_written"),
        # One answer a side a deal; also the foreign key's index.
        UniqueConstraint("deal_memo_id", "author_side", name="uq_deal_feedback_side"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Who answered; the answer is about the other side.
    author_side: Mapped[str] = mapped_column(String(10), nullable=False)
    brief: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reliability: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    easy: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the deal's window closes; after it, this answer may be seen even
    # if the other side never answered.
    window_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

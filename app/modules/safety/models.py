"""One account blocking another (item 59, trust-and-safety.md rule 7).

A creator blocks a brand, or a brand blocks a creator. From then on the two
cannot start anything new with each other in either direction: no
invitation, repeat or application, and neither appears in the other's
search, matches or campaign discovery. What they already agreed carries on,
since a block cannot undo a contract; the deal record and its notifications
stay as they are.

The blocked account is never told, and nothing it can call reveals the
block: an attempt reads as "not found", as for someone suspended (D-061).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class AccountBlock(Base):
    __tablename__ = "account_block"
    __table_args__ = (
        UniqueConstraint(
            "blocker_account_id", "blocked_account_id", name="uq_account_block_pair"
        ),
        CheckConstraint("blocker_account_id <> blocked_account_id", name="not_oneself"),
        # "Has anyone blocked me?" is asked from the blocked side too.
        Index("ix_account_block_blocked_account_id", "blocked_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE on both: a block means nothing once either account is gone.
    blocker_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    blocked_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

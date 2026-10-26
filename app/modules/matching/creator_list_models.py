"""A brand's saved creator lists (item 66, D-129): "Diwali food creators".

A brand keeps names it found in search or matches, across campaigns. A
list is the brand's own, private: a creator is never told they are on one,
and reading a list shows only creators the brand could find in search
today (`search_service.visible`), so a creator who unpublished, left,
was suspended or withheld, or blocked either way, drops out of view.

CASCADE on both: a list is the brand's own thing, and an entry its line.
Deleting an account (D-122) erases the brand's lists and every line about
a creator who left (`creator_list_service.erase_for_*`).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

LIST_NAME_MAX_LENGTH = 60
MAX_LISTS_PER_BRAND = 50
MAX_CREATORS_PER_LIST = 200


class CreatorList(Base):
    __tablename__ = "creator_list"
    __table_args__ = (
        CheckConstraint(
            f"char_length(btrim(name)) BETWEEN 1 AND {LIST_NAME_MAX_LENGTH}",
            name="name_length",
        ),
        # A brand's names are its own and distinct; also the foreign key's index.
        UniqueConstraint("brand_id", "name", name="uq_creator_list_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brand.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(LIST_NAME_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CreatorListEntry(Base):
    __tablename__ = "creator_list_entry"
    __table_args__ = (
        # A creator once a list; also the list's foreign key's index.
        UniqueConstraint("list_id", "creator_id", name="uq_creator_list_entry_once"),
        # The creator's foreign key's index, for erasing a creator who left.
        Index("ix_creator_list_entry_creator_id", "creator_id"),
        # A list's creators, newest first.
        Index("ix_creator_list_entry_list_id_created_at", "list_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator_list.id", ondelete="CASCADE"),
        nullable=False,
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("creator.id", ondelete="CASCADE"), nullable=False
    )
    # When the brand saved them. Never updated: a line is added or removed.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

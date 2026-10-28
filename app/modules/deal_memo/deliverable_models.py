"""A memo's deliverables, one row each (item 26, D-127): what both sides agree.

The same rules as a campaign's (`campaigns.deliverable_models`). Unlike the
campaign's, these are terms: they change only while the memo is editable
(draft, or sent back with a change request), and from terms version 2 the
deal record's fingerprint covers them (`record_service.terms_fingerprint`).

RESTRICT on the memo: a record of what was agreed, which must never vanish
as a side effect.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
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
from app.modules.campaigns.deliverable_models import deliverable_checks


class MemoDeliverable(Base):
    __tablename__ = "memo_deliverable"
    __table_args__ = (
        *deliverable_checks(),
        # One row a place; also the foreign key's index.
        UniqueConstraint("deal_memo_id", "position", name="uq_memo_deliverable_place"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

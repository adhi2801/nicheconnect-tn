"""Daily checkpoints of the deal record, stamped by outside authorities (D-060).

Once a day one Merkle root is computed over every deal's latest seal, and
two independent RFC 3161 timestamp authorities sign "this value existed at
this time". After that, rewriting a deal's history would mean forging their
signatures, not only ours.

The leaves are not stored. The deal record is append-only, so "each deal's
latest seal as of `covers_until`" can always be recomputed exactly; only the
root, the cut-off and the signed tokens are kept.

Both tables are append-only, refused UPDATE, DELETE and TRUNCATE by a
trigger, and neither has `updated_at`: the same two departures from
`database.md` as the deal record itself (D-057), for the same reasons.

A checkpoint with no timestamp rows is a visible gap, not a hidden one: the
authorities were unreachable and the next run tries again.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Run by different companies, so no single outage or compromise matters.
TIMESTAMP_AUTHORITIES: tuple[str, ...] = ("digicert", "sectigo")
ROOT_BYTES = 32  # SHA-256


class DealRecordCheckpoint(Base):
    """One day's Merkle root over every deal's latest seal."""

    __tablename__ = "deal_record_checkpoint"
    __table_args__ = (
        UniqueConstraint("covers_until", name="uq_deal_record_checkpoint_covers_until"),
        CheckConstraint("leaf_count >= 0", name="leaf_count_not_negative"),
        CheckConstraint(
            f"octet_length(merkle_root) = {ROOT_BYTES}", name="merkle_root_length"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # Every entry recorded at or before this moment is covered. Midnight in
    # Tamil Nadu, stored in UTC like every time in the schema.
    covers_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    leaf_count: Mapped[int] = mapped_column(Integer, nullable=False)
    merkle_root: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class DealRecordTimestamp(Base):
    """One authority's signed statement that a checkpoint's root existed."""

    __tablename__ = "deal_record_timestamp"
    __table_args__ = (
        UniqueConstraint(
            "checkpoint_id", "authority", name="uq_deal_record_timestamp_authority"
        ),
        CheckConstraint(
            f"authority IN {tuple(TIMESTAMP_AUTHORITIES)}", name="authority_allowed"
        ),
        CheckConstraint("octet_length(token) > 0", name="token_not_empty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # RESTRICT: a checkpoint that has been stamped can never be removed.
    checkpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_record_checkpoint.id", ondelete="RESTRICT"),
        nullable=False,
    )
    authority: Mapped[str] = mapped_column(String(40), nullable=False)
    # The signed RFC 3161 token exactly as issued (DER), so anyone can check it
    # with `openssl ts -verify` without trusting how we parsed it.
    token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # The authority's own time, read from the token.
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

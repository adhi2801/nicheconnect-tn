"""The deal record: every step of a deal, each sealed to the one before (D-057).

Rows here are never changed. The database refuses UPDATE, DELETE and TRUNCATE
with a trigger (the migration creates it), so append-only is a property of
the table and not a promise of the code.

Each entry carries the SHA-256 of the entry before it. Change any earlier
entry and every fingerprint after it stops matching. How the fingerprint is
computed lives in `record_service`, and `docs/DEAL_RECORD_VERIFY.md` explains
it to anyone who wants to check it without trusting us.

Two deliberate departures from `database.md`, approved with the table:

- **No `updated_at`.** A row that is never updated would carry a column that
  always equals `recorded_at`, and would invite the question of what
  updates it.
- **A trigger**, the first in the schema: the only way to make the database
  itself refuse to rewrite history.

**Nothing a person typed is stored here.** Terms, proof links, notes and
payment references appear only as SHA-256 fingerprints in `facts`. The text
stays in the ordinary tables, where it can be corrected or erased.
"""

import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

RECORD_KINDS: tuple[str, ...] = (
    # Opening entry for a deal that had history before the record existed.
    "record_started",
    "memo_sent",
    "memo_change_requested",
    "memo_accepted",
    "memo_declined",
    "memo_cancelled",
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_opened",
    "payment_marked_paid",
    "payment_confirmed",
    "dispute_opened",
    "dispute_entry_added",
    "dispute_closed",
)
# "system" is us acting on the deal's own rules, such as approving work at the
# end of the review window (D-025) or opening the payment record it causes.
RECORD_ACTORS: tuple[str, ...] = ("brand", "creator", "system")

HASH_BYTES = 32  # SHA-256
GENESIS_HASH = bytes(HASH_BYTES)  # what the first entry's previous_hash holds


class DealRecordEntry(Base):
    """One dated, sealed step in one deal's life."""

    __tablename__ = "deal_record_entry"
    __table_args__ = (
        # Two writers cannot fork a chain: the second fails and retries. The
        # index behind it also serves every read, by deal, in order.
        UniqueConstraint(
            "deal_memo_id", "sequence", name="uq_deal_record_entry_sequence"
        ),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint(f"kind IN {tuple(RECORD_KINDS)}", name="kind_allowed"),
        CheckConstraint(
            f"actor_role IN {tuple(RECORD_ACTORS)}", name="actor_role_allowed"
        ),
        # Only "system" acts without an account.
        CheckConstraint(
            "(actor_role = 'system') = (actor_account_id IS NULL)",
            name="actor_account_matches_role",
        ),
        CheckConstraint(
            f"octet_length(previous_hash) = {HASH_BYTES}", name="previous_hash_length"
        ),
        CheckConstraint(
            f"octet_length(entry_hash) = {HASH_BYTES}", name="entry_hash_length"
        ),
        # The first entry, and only the first, starts from the zero hash.
        CheckConstraint(
            f"(sequence = 1) = (previous_hash = '\\x{'00' * HASH_BYTES}'::bytea)",
            name="genesis_only_first",
        ),
        CheckConstraint("jsonb_typeof(facts) = 'object'", name="facts_is_object"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    # RESTRICT: a deal with a record can never be deleted out from under it.
    deal_memo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deal_memo.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(10), nullable=False)
    # No foreign key, on purpose: a deleted account must never block the
    # record or change a sealed row.
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # When it took effect, and when we wrote it down. They differ when work
    # is approved at the end of its window but noticed later (D-025).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    previous_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    entry_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

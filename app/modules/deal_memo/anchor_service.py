"""The daily checkpoint: one root over every deal, stamped from outside (D-060).

Each day's checkpoint is named by its date in Tamil Nadu and covers every
entry recorded before midnight at the start of that date. Its leaves are
each deal's latest seal as of then, in order of deal id:

    leaf = deal memo id (16 bytes) + that deal's latest seal (32 bytes)

The leaves are not stored. The record is append-only, so they can always be
recomputed from it, and a proof recomputes them rather than trusting a copy.

A checkpoint is written before it is stamped. If an authority cannot be
reached, the checkpoint stands unstamped, which is a visible gap, and the
next run tries again for up to `RESTAMP_DAYS` days.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import IST, india_date
from app.modules.deal_memo import merkle
from app.modules.deal_memo.anchor_models import DealRecordCheckpoint, DealRecordTimestamp
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.timestamp_authority import Stamp, TimestampFailed

logger = logging.getLogger(__name__)

# How far back a missing stamp is retried. After that the gap is permanent,
# and is shown as such rather than filled in late.
RESTAMP_DAYS = 7


class Authority(Protocol):
    name: str

    def stamp(self, fingerprint: bytes) -> Stamp: ...


def covers_until(day: date) -> datetime:
    """Midnight in Tamil Nadu at the start of `day`."""
    return datetime.combine(day, time(0, 0), tzinfo=IST)


def leaf(memo_id: uuid.UUID, seal: bytes) -> bytes:
    return memo_id.bytes + seal


def leaves_at(db: Session, cutoff: datetime) -> list[tuple[uuid.UUID, bytes]]:
    """Each deal's latest seal recorded before `cutoff`, in order of deal id."""
    rows = db.execute(
        select(DealRecordEntry.deal_memo_id, DealRecordEntry.entry_hash)
        .where(DealRecordEntry.recorded_at < cutoff)
        .distinct(DealRecordEntry.deal_memo_id)
        .order_by(DealRecordEntry.deal_memo_id, DealRecordEntry.sequence.desc())
    ).all()
    # Sorted by the id's bytes, which is how the leaf is written, so the
    # order never depends on how a database compares UUIDs.
    return sorted(((memo_id, seal) for memo_id, seal in rows), key=lambda r: r[0].bytes)


def checkpoint_for(db: Session, day: date) -> DealRecordCheckpoint | None:
    return db.scalars(
        select(DealRecordCheckpoint).where(
            DealRecordCheckpoint.covers_until == covers_until(day)
        )
    ).first()


def create_checkpoint(db: Session, day: date) -> DealRecordCheckpoint:
    """The checkpoint for `day`, written once; later calls return it."""
    existing = checkpoint_for(db, day)
    if existing is not None:
        return existing
    leaves = [leaf(m, s) for m, s in leaves_at(db, covers_until(day))]
    row = DealRecordCheckpoint(
        covers_until=covers_until(day),
        leaf_count=len(leaves),
        merkle_root=merkle.root(leaves),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Another run wrote it first. Its root is the same by construction.
        db.rollback()
        found = checkpoint_for(db, day)
        if found is None:
            raise
        return found
    return row


def stamp_checkpoint(
    db: Session, checkpoint: DealRecordCheckpoint, authorities: Iterable[Authority]
) -> list[str]:
    """Ask each authority that has not stamped it yet. Returns those that did."""
    done = set(
        db.scalars(
            select(DealRecordTimestamp.authority).where(
                DealRecordTimestamp.checkpoint_id == checkpoint.id
            )
        ).all()
    )
    stamped = []
    for authority in authorities:
        if authority.name in done:
            continue
        try:
            stamp = authority.stamp(checkpoint.merkle_root)
        except TimestampFailed as exc:
            # Only the authority and the reason: there is nothing personal here.
            logger.warning(
                "checkpoint.stamp_failed authority=%s reason=%s", authority.name, exc
            )
            continue
        db.add(
            DealRecordTimestamp(
                checkpoint_id=checkpoint.id,
                authority=authority.name,
                token=stamp.token,
                signed_at=stamp.signed_at,
            )
        )
        db.commit()
        stamped.append(authority.name)
    return stamped


@dataclass(frozen=True)
class DailyRun:
    checkpoint_day: date
    leaf_count: int
    stamped: dict[date, list[str]]


def run_daily(db: Session, now: datetime, authorities: Sequence[Authority]) -> DailyRun:
    """Today's checkpoint, and any missing stamps from the last few days."""
    today = india_date(now)
    checkpoint = create_checkpoint(db, today)
    stamped: dict[date, list[str]] = {}
    for back in range(RESTAMP_DAYS, -1, -1):
        day = today - timedelta(days=back)
        row = checkpoint if back == 0 else checkpoint_for(db, day)
        if row is not None:
            got = stamp_checkpoint(db, row, authorities)
            if got:
                stamped[day] = got
    return DailyRun(
        checkpoint_day=today, leaf_count=checkpoint.leaf_count, stamped=stamped
    )


# --- a deal's proof ------------------------------------------------------------


@dataclass(frozen=True)
class Proof:
    checkpoint: DealRecordCheckpoint
    leaf_index: int
    seal: bytes
    audit_path: list[bytes]
    timestamps: list[DealRecordTimestamp]


class NotInCheckpoint(LookupError):
    """The deal had no entries before that checkpoint's cut-off."""


def latest_checkpoint_with(
    db: Session, memo_id: uuid.UUID
) -> DealRecordCheckpoint | None:
    """The newest checkpoint whose cut-off falls after the deal's first entry."""
    first = db.scalar(
        select(DealRecordEntry.recorded_at)
        .where(DealRecordEntry.deal_memo_id == memo_id)
        .order_by(DealRecordEntry.sequence)
        .limit(1)
    )
    if first is None:
        return None
    return db.scalars(
        select(DealRecordCheckpoint)
        .where(DealRecordCheckpoint.covers_until > first)
        .order_by(DealRecordCheckpoint.covers_until.desc())
        .limit(1)
    ).first()


def proof_for(db: Session, memo_id: uuid.UUID, checkpoint: DealRecordCheckpoint) -> Proof:
    """This deal's place in the checkpoint, and the path from it to the root.

    Recomputes the leaves and checks they still give the stored root, so a
    proof is never issued against a record that no longer matches.
    """
    rows = leaves_at(db, checkpoint.covers_until)
    ids = [m for m, _ in rows]
    if memo_id not in ids:
        raise NotInCheckpoint()
    leaves = [leaf(m, s) for m, s in rows]
    if merkle.root(leaves) != checkpoint.merkle_root:
        raise RuntimeError("the record no longer matches a stamped checkpoint")
    index = ids.index(memo_id)
    timestamps = list(
        db.scalars(
            select(DealRecordTimestamp)
            .where(DealRecordTimestamp.checkpoint_id == checkpoint.id)
            .order_by(DealRecordTimestamp.authority)
        ).all()
    )
    return Proof(
        checkpoint=checkpoint,
        leaf_index=index,
        seal=rows[index][1],
        audit_path=merkle.audit_path(index, leaves),
        timestamps=timestamps,
    )

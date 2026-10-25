"""Deal notes on the record (item 17, D-128): writing one, reading the thread, proving them.

Once a memo is sent, either party writes a plain note (choice A). The note
and its sealed `note_added` record entry are written in one transaction:
the record's own lock on the deal's row (`record_service.append`) orders
notes and every other step of the deal, and a note that fails to seal is
never kept. The table refuses changes at the database (`note_models`), and
`unchanged` checks each note against the fingerprint sealed for it, so a
note rewritten by someone who switched the triggers off still shows.

Threat model: only the two parties reach a deal's notes
(`dependencies.visible_memo_for_account`, 404 to anyone else); a note is
plain text with its flags worked out on read; a daily ceiling per account
stops anyone burying the other in notes (trust-and-safety.md rule 2). An
agreed deal carries on across a block (item 59), so its notes do too.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.pagination import Slice, build_slice, older_than_cursor
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo.exceptions import NotesClosed
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.note_models import DealNote
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.service import memos_for_account, notify_party

# From sending on (choice A). A draft is the brand's alone; a declined or
# cancelled deal has ended, and its notes so far stay on the record.
OPEN_STATUSES = frozenset({"sent", "change_requested", "accepted"})

EXPORTED_TABLES = frozenset({"deal_note"})
EXPORT_FIELDS = allow("id", "deal_memo_id", "author_side", "body", "created_at")


def add(db: Session, memo: DealMemo, side: str, body: str, now: datetime) -> DealNote:
    """Write a note and seal it onto the deal record, then tell the other side. Commits.

    Raises NotesClosed (a draft, or a deal that has ended).
    """
    db.refresh(memo, attribute_names=["status"], with_for_update=True)
    if memo.status not in OPEN_STATUSES:
        db.rollback()
        raise NotesClosed()
    note = DealNote(deal_memo_id=memo.id, author_side=side, body=body, created_at=now)
    db.add(note)
    db.flush()
    record.append(
        db,
        memo,
        kind="note_added",
        actor_role=side,
        now=now,
        facts={"note_id": str(note.id), "note_sha256": record.fingerprint(body)},
    )
    notify_party(
        db,
        memo,
        to="creator" if side == "brand" else "brand",
        notification_type="note_added",
        now=now,
    )
    db.commit()
    db.refresh(note)
    return note


def page(
    db: Session, memo: DealMemo, *, limit: int, cursor: str | None
) -> Slice[DealNote]:
    """A deal's notes, newest first, in keyset pages (backend.md section 2)."""
    query = select(DealNote).where(DealNote.deal_memo_id == memo.id)
    if cursor is not None:
        query = query.where(older_than_cursor(DealNote.created_at, DealNote.id, cursor))
    rows = list(
        db.scalars(
            query.order_by(DealNote.created_at.desc(), DealNote.id.desc()).limit(
                limit + 1
            )
        ).all()
    )
    return build_slice(rows, limit, key=lambda row: (row.created_at, row.id))


def unchanged(db: Session, memo: DealMemo) -> bool | None:
    """Whether every note still matches the fingerprint sealed for it. None: no notes.

    Two queries, whatever the number of notes.
    """
    notes = {
        str(note.id): note
        for note in db.scalars(select(DealNote).where(DealNote.deal_memo_id == memo.id))
    }
    sealed = {
        facts["note_id"]: facts["note_sha256"]
        for facts in db.scalars(
            select(DealRecordEntry.facts).where(
                DealRecordEntry.deal_memo_id == memo.id,
                DealRecordEntry.kind == "note_added",
            )
        )
    }
    if not notes and not sealed:
        return None
    return set(notes) == set(sealed) and all(
        record.fingerprint(note.body) == sealed[note_id]
        for note_id, note in notes.items()
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The notes on this account's deals, written by either side."""
    memo_ids = {
        memo.id
        for memo in memos_for_account(db, account_id, limit=MAX_ROWS_PER_SECTION + 1)
    }
    notes = (
        list(
            db.scalars(
                select(DealNote)
                .where(DealNote.deal_memo_id.in_(memo_ids))
                .order_by(DealNote.created_at, DealNote.id)
                .limit(MAX_ROWS_PER_SECTION + 1)
            ).all()
        )
        if memo_ids
        else []
    )
    return [
        build_section(
            "deal_notes",
            table="deal_note",
            purpose=(
                "Notes you and the other side wrote on your deals, each sealed "
                "onto the deal's record by its fingerprint, so either of you "
                "can prove what was said."
            ),
            objects=notes,
            fields=EXPORT_FIELDS,
        )
    ]

"""Removing deal record entries that a test really committed. Tests only.

The database refuses to delete a deal record entry (D-057), which is the
point of the table. A few tests have to commit for real, because they race
separate connections against each other, and they must still leave the
database as they found it.

`session_replication_role = replica` switches off user triggers, and with
them foreign-key checks, **for this one transaction only**. It needs a
superuser, which the local and CI databases have and the running service
must never be given. It is the same bypass step 1 of the proposal names as
its honest limit: someone with full control of the database can rewrite the
record, and only step 2's outside timestamps would catch it.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.modules.deal_memo.record_models import DealRecordEntry


def remove_deal_records(session: Session, memo_ids: Iterable[uuid.UUID]) -> None:
    """Delete these deals' entries, inside the caller's transaction.

    The bypass is switched off again straight after, for the caller's later
    deletes need their cascades. Left on, deleting an account skipped
    ON DELETE CASCADE and left its notifications behind, pointing at
    nothing: found 10 October 2026, when a migration's downgrade tripped on
    them.
    """
    session.execute(text("SET LOCAL session_replication_role = replica"))
    session.execute(
        delete(DealRecordEntry).where(DealRecordEntry.deal_memo_id.in_(list(memo_ids)))
    )
    session.execute(text("SET LOCAL session_replication_role = origin"))

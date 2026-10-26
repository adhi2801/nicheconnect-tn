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

from sqlalchemy import delete, select, text

from app.modules.deal_memo.note_models import DealNote
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.shipment_models import BarterShipment
from app.modules.disputes.event_models import DisputeEvent
from app.modules.disputes.models import Dispute
from app.modules.payment_status.models import PaymentStatus
from tests.owner import owner_engine


def remove_deal_records(memo_ids: Iterable[uuid.UUID]) -> None:
    """Delete these deals' record entries, notes and dispute events, and commit.

    Dispute events are sealed too, since item 99. The bypass needs a
    superuser, which the app's own login never is (item 97), so this runs on
    the owner's connection, in a transaction of its own, before the caller
    deletes the deals themselves. Left on for the caller's deletes, the
    bypass skipped ON DELETE CASCADE and left notifications pointing at
    nothing: found 10 October 2026, when a migration's downgrade tripped on
    them. So it never touches the caller's session.
    """
    memos = list(memo_ids)
    with owner_engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(
            delete(DealRecordEntry).where(DealRecordEntry.deal_memo_id.in_(memos))
        )
        # Deal notes are sealed the same way (D-128).
        connection.execute(delete(DealNote).where(DealNote.deal_memo_id.in_(memos)))
        # A barter shipment holds its memo by RESTRICT too (D-131).
        connection.execute(
            delete(BarterShipment).where(BarterShipment.deal_memo_id.in_(memos))
        )
        connection.execute(
            delete(DisputeEvent).where(
                DisputeEvent.dispute_id.in_(
                    select(Dispute.id)
                    .join(PaymentStatus, PaymentStatus.id == Dispute.payment_status_id)
                    .where(PaymentStatus.deal_memo_id.in_(memos))
                )
            )
        )

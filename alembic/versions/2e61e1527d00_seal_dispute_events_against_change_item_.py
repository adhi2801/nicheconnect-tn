"""seal dispute events against change (item 99)

A dispute's timeline is a dated account from both sides (D-028): its worth
is that nobody can change what was said, or when, afterwards. The app only
ever inserts dispute events, and each is fingerprinted in the deal record
(D-057), but until 14 October 2026 the table itself refused nothing, though
docs/standards/database.md said it did (gap 3, approved by Adhi the same
day, D-100).

This gives dispute_event the deal record's seal: the existing
append_only_refuse_change() function, fired BEFORE UPDATE OR DELETE on each
row and BEFORE TRUNCATE. dispute_event keeps its updated_at column, which
always equals created_at; dropping it would change the API's history for
nothing.

What it changes: ON DELETE CASCADE from dispute can no longer remove events,
so a dispute with events cannot be deleted. Nothing deletes disputes (D-028),
and payments, deals and the record above them already refuse deletion.
Tests that commit for real remove their events through
tests/record_cleanup.py, the one test-only bypass.

No data changes. The downgrade drops the two triggers, which loses nothing.

Revision ID: 2e61e1527d00
Revises: 1a04f9d7e1fe
Create Date: 2026-10-14 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2e61e1527d00'
down_revision: Union[str, None] = '1a04f9d7e1fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TRIGGER dispute_event_no_update_or_delete "
        "BEFORE UPDATE OR DELETE ON dispute_event "
        "FOR EACH ROW EXECUTE FUNCTION append_only_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER dispute_event_no_truncate "
        "BEFORE TRUNCATE ON dispute_event "
        "FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER dispute_event_no_truncate ON dispute_event")
    op.execute("DROP TRIGGER dispute_event_no_update_or_delete ON dispute_event")

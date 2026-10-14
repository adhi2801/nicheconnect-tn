"""a reporter told the outcome: report_resolved notifications (item 102)

docs/standards/trust-and-safety.md rule 9 promised that a reporter learns
the outcome of a report; until 14 October 2026 nothing told them (gap 1,
approved by Adhi the same day, D-100). An admin resolving a report now
notifies the reporter, so notification.notification_type allows
'report_resolved', and so does the list of types a person may mute (it is
not urgent: no deadline runs against the reporter).

Each list is widened the way database.md section 6 asks: the old check is
dropped and the wider one added NOT VALID in one transaction, then validated
after it commits, so existing rows are scanned without blocking writes
(Squawk, D-050). The lists are written out here, frozen, rather than read
from the models, so this migration means the same thing forever.

Downgrade: report_resolved notifications are deleted and the type is taken
out of muted lists, then the narrower checks return. Nothing is lost that
cannot be recovered: each such notification restates a report's status and
resolved_at, which stay in the report table, and a mute is a choice the
person can make again.

Revision ID: 068ad68f4079
Revises: 2e61e1527d00
Create Date: 2026-10-14 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '068ad68f4079'
down_revision: Union[str, None] = '2e61e1527d00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'proof_submitted', 'invitation_accepted', 'invitation_declined', 'application_shortlisted', 'application_accepted', 'application_rejected', 'memo_sent', 'proof_approved', 'proof_auto_approved', 'proof_revision_requested', 'payment_marked_paid', 'invitation_received', 'invitation_withdrawn', 'memo_cancelled', 'payment_confirmed')
NEW_TYPES = OLD_TYPES + ('report_resolved',)
OLD_MUTABLE = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'invitation_accepted', 'invitation_declined', 'application_shortlisted', 'application_accepted', 'application_rejected', 'proof_approved', 'proof_auto_approved', 'invitation_received', 'invitation_withdrawn', 'memo_cancelled', 'payment_confirmed')
NEW_MUTABLE = OLD_MUTABLE + ('report_resolved',)

TYPE_CHECK = ("notification", "ck_notification_type_allowed")
MUTE_CHECK = ("notification_preference", "ck_notification_preference_muted_types_allowed")


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap(types: tuple[str, ...], mutable: tuple[str, ...]) -> None:
    """Replace both checks, NOT VALID, inside the migration's transaction."""
    for (table, name), condition in (
        (TYPE_CHECK, f"notification_type IN {types}"),
        (MUTE_CHECK, f"muted_types <@ {_array(mutable)}"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")


def _validate() -> None:
    with op.get_context().autocommit_block():
        for table, name in (TYPE_CHECK, MUTE_CHECK):
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    _swap(NEW_TYPES, NEW_MUTABLE)
    _validate()


def downgrade() -> None:
    op.execute("DELETE FROM notification WHERE notification_type = 'report_resolved'")
    op.execute(
        "UPDATE notification_preference "
        "SET muted_types = array_remove(muted_types, 'report_resolved') "
        "WHERE 'report_resolved' = ANY (muted_types)"
    )
    _swap(OLD_TYPES, OLD_MUTABLE)
    _validate()

"""add invitations and repeat deals to application (D-084)

A brand may now invite a creator to an open campaign, and "work together
again" is an invitation that names the earlier deal it repeats (approved by
Adhi in session, 10 October 2026, option A). An invitation is a row in
`application`, so it keeps the one-row-per-creator-per-campaign rule and
everything that hangs off an application (the memo, its stage, the export)
works unchanged.

On `application`:

- `origin` ('applied' or 'invited'), NOT NULL with a constant default.
  Every existing row is an application, so the default is the truth for all
  of them, and PostgreSQL 11 and later add such a column without rewriting
  the table.
- `pitch` becomes nullable: an invited creator has nothing to pitch. A new
  check ties it to the origin both ways. The length check needs no change:
  on NULL it is unknown, which passes.
- `invitation_note`, `decline_reason`: nullable, set only on invitations,
  each with its own checks.
- `repeat_of_application_id`: the earlier deal's application, which has
  exactly one memo. ON DELETE RESTRICT: both rows are records of deals.
  Indexed only where set, since only repeats carry it.
- The status list gains 'invited' and 'declined'. An invitation may only be
  invited, accepted, declined or withdrawn.

On `notification` and `notification_preference`: the four invitation types
are added to the allowed types, and to the types a person may mute. None is
urgent; nothing runs against a deadline.

Every new or widened check is added NOT VALID inside the transaction and
validated after it commits, and the index is built CONCURRENTLY, so no step
holds a lock that blocks writes while it scans (database.md section 6,
Squawk, D-050). The old status, type and mute checks are dropped in the same
transaction their wider replacements are added in, so no moment is
unchecked to any other session.

The downgrade refuses while any invitation exists: an invitation has no
pitch and cannot be written back as an application, and it is a record of a
deal. With none, it removes the invitation types from people's muted lists,
which is a preference they can set again, and restores the narrower checks.

Revision ID: 2c3bf71783d2
Revises: f74cbe0d42c9
Create Date: 2026-10-10 06:49:37.742742

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c3bf71783d2'
down_revision: Union[str, None] = 'f74cbe0d42c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUSES = ('submitted', 'shortlisted', 'accepted', 'rejected', 'withdrawn')
NEW_STATUSES = (*OLD_STATUSES, 'invited', 'declined')
INVITATION_TYPES = (
    'invitation_accepted',
    'invitation_declined',
    'invitation_received',
    'invitation_withdrawn',
)
OLD_TYPES = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'proof_submitted', 'application_shortlisted', 'application_accepted', 'application_rejected', 'memo_sent', 'proof_approved', 'proof_auto_approved', 'proof_revision_requested', 'payment_marked_paid', 'memo_cancelled', 'payment_confirmed')
# In the models' order, so the database's check reads the same as theirs.
NEW_TYPES = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'proof_submitted', 'invitation_accepted', 'invitation_declined', 'application_shortlisted', 'application_accepted', 'application_rejected', 'memo_sent', 'proof_approved', 'proof_auto_approved', 'proof_revision_requested', 'payment_marked_paid', 'invitation_received', 'invitation_withdrawn', 'memo_cancelled', 'payment_confirmed')
OLD_MUTABLE = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'application_shortlisted', 'application_accepted', 'application_rejected', 'proof_approved', 'proof_auto_approved', 'memo_cancelled', 'payment_confirmed')
NEW_MUTABLE = ('application_received', 'application_withdrawn', 'memo_accepted', 'memo_declined', 'memo_change_requested', 'invitation_accepted', 'invitation_declined', 'application_shortlisted', 'application_accepted', 'application_rejected', 'proof_approved', 'proof_auto_approved', 'invitation_received', 'invitation_withdrawn', 'memo_cancelled', 'payment_confirmed')


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


# (table, constraint, condition): each added NOT VALID, then validated.
NEW_CHECKS = (
    ("application", "ck_application_status_allowed", f"status IN {NEW_STATUSES}"),
    ("application", "ck_application_origin_allowed", "origin IN ('applied', 'invited')"),
    (
        "application",
        "ck_application_pitch_matches_origin",
        "(origin = 'applied') = (pitch IS NOT NULL)",
    ),
    (
        "application",
        "ck_application_invitation_fields_need_invitation",
        "origin = 'invited' OR (invitation_note IS NULL"
        " AND status NOT IN ('invited', 'declined')"
        " AND repeat_of_application_id IS NULL)",
    ),
    (
        "application",
        "ck_application_invitation_status_allowed",
        "origin = 'applied' OR status IN ('invited', 'accepted', 'declined', 'withdrawn')",
    ),
    (
        "application",
        "ck_application_invitation_note_length",
        "invitation_note IS NULL OR char_length(invitation_note) BETWEEN 1 AND 500",
    ),
    (
        "application",
        "ck_application_decline_reason_allowed",
        "decline_reason IS NULL OR decline_reason IN ('timing', 'budget', 'not_a_fit', 'other')",
    ),
    (
        "application",
        "ck_application_decline_reason_matches_status",
        "(status = 'declined') = (decline_reason IS NOT NULL)",
    ),
    (
        "application",
        "ck_application_repeat_not_itself",
        "repeat_of_application_id IS NULL OR repeat_of_application_id <> id",
    ),
    ("notification", "ck_notification_type_allowed", f"notification_type IN {NEW_TYPES}"),
    (
        "notification_preference",
        "ck_notification_preference_muted_types_allowed",
        f"muted_types <@ {_array(NEW_MUTABLE)}",
    ),
)
# The three checks above that replace a narrower one of the same name.
WIDENED = (
    ("application", "ck_application_status_allowed"),
    ("notification", "ck_notification_type_allowed"),
    ("notification_preference", "ck_notification_preference_muted_types_allowed"),
)
FOREIGN_KEY = "fk_application_repeat_of_application_id_application"
INDEX = "ix_application_repeat_of_application_id"


def upgrade() -> None:
    op.add_column('application', sa.Column('origin', sa.String(length=10), server_default=sa.text("'applied'"), nullable=False))
    op.add_column('application', sa.Column('invitation_note', sa.Text(), nullable=True))
    op.add_column('application', sa.Column('repeat_of_application_id', sa.UUID(), nullable=True))
    op.add_column('application', sa.Column('decline_reason', sa.String(length=20), nullable=True))
    # Deliberate (D-084): an invitation has no pitch. Squawk warns that
    # readers may expect a value; the only reader is this app, which handles
    # null, and the API contract declares it nullable from this change on (no
    # frontend exists yet, D-053). One statement with its comment, so the
    # ignore applies to exactly this line, as in c45a9831e0c9.
    op.execute(
        "-- squawk-ignore ban-drop-not-null\n"
        "ALTER TABLE application ALTER COLUMN pitch DROP NOT NULL"
    )

    op.execute(
        f"ALTER TABLE application ADD CONSTRAINT {FOREIGN_KEY} "
        "FOREIGN KEY (repeat_of_application_id) REFERENCES application (id) "
        "ON DELETE RESTRICT NOT VALID"
    )
    for table, name in WIDENED:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    for table, name, condition in NEW_CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")

    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE application VALIDATE CONSTRAINT {FOREIGN_KEY}")
        for table, name, _ in NEW_CHECKS:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
        op.create_index(
            INDEX,
            'application',
            ['repeat_of_application_id'],
            unique=False,
            postgresql_where=sa.text('repeat_of_application_id IS NOT NULL'),
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    invitations = op.get_bind().execute(
        sa.text("SELECT count(*) FROM application WHERE origin = 'invited'")
    ).scalar_one()
    if invitations:
        raise RuntimeError(
            f"{invitations} invitation(s) exist. They are records of deals and "
            "have no pitch to fall back to; remove them deliberately before "
            "downgrading. This migration will not."
        )

    # Notifications of these types belong to invitations, and none exists,
    # so any left are rows whose invitation is gone: a cascade skipped (a
    # test cleanup did this until 10 October). They would fail the narrower
    # check, and they point at nothing.
    op.execute(
        f"DELETE FROM notification WHERE notification_type IN {INVITATION_TYPES}"
    )
    # Mute settings for types that are going away; a person can set them
    # again.
    for kind in INVITATION_TYPES:
        op.execute(
            "UPDATE notification_preference "
            f"SET muted_types = array_remove(muted_types, '{kind}') "
            f"WHERE '{kind}' = ANY (muted_types)"
        )

    op.drop_index(INDEX, table_name='application', postgresql_where=sa.text('repeat_of_application_id IS NOT NULL'))
    for table, name, _ in NEW_CHECKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.create_check_constraint(op.f('ck_application_status_allowed'), 'application', f"status IN {OLD_STATUSES}")
    op.create_check_constraint(op.f('ck_notification_type_allowed'), 'notification', f"notification_type IN {OLD_TYPES}")
    op.create_check_constraint(
        op.f('ck_notification_preference_muted_types_allowed'),
        'notification_preference',
        f"muted_types <@ {_array(OLD_MUTABLE)}",
    )
    op.drop_constraint(FOREIGN_KEY, 'application', type_='foreignkey')
    op.alter_column('application', 'pitch', existing_type=sa.TEXT(), nullable=False)
    op.drop_column('application', 'decline_reason')
    op.drop_column('application', 'repeat_of_application_id')
    op.drop_column('application', 'invitation_note')
    op.drop_column('application', 'origin')

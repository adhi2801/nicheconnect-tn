"""phone change: a new number waits 72 hours before it takes over the login (item 80)

The phone number is the whole login, and nobody could change theirs: a
person switching numbers lost their account, and a number left behind is
reissued by the carrier after 90 days to someone who could then log into
it. Approved by Adhi on 17 October 2026, option A (D-108): a change needs a
code from each number, then waits 72 hours, cancellable with no code, before
a job moves the account and ends every session. This migration:

- creates `account_phone_change`: at most one per account, the new number
  (held to the phone format, and unique, so two accounts cannot wait on the
  same number), when it was asked for, and when it takes over (exactly 72
  hours later). Deleted when the change is made or cancelled;
- adds `change_phone` to the actions a step-up code may be asked for;
- adds four notification types, every one urgent and so never mutable:
  `phone_change_requested`, `phone_change_cancelled`, `phone_changed` and
  `phone_change_failed`. The muted-types list is unchanged, since no new
  type may be muted.

The new table is empty, so its constraints are created whole (database.md
section 6). Both widened lists are swapped NOT VALID in the migration's
transaction and validated after it commits, so writes are never blocked
(Squawk, D-050).

ON DELETE: CASCADE, since a waiting change means nothing without its
account. The unique constraint on `account_id` serves its foreign key.

Data impact: none on existing rows.

Downgrade: refuses while any change is waiting, since each is a person's
request, proven with two codes, that would be silently dropped. Otherwise
it deletes the four new kinds of notification and the step-up codes asked
for `change_phone` (short-lived, as the table's own were in 44fc99b873a7),
restores both narrower lists and drops the table.

Revision ID: d18c285488f0
Revises: 44fc99b873a7
Create Date: 2026-10-17 20:19:09.648312

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d18c285488f0"
down_revision: Union[str, None] = "44fc99b873a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_TYPES = (
    "application_received",
    "application_withdrawn",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "proof_submitted",
    "invitation_accepted",
    "invitation_declined",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_marked_paid",
    "invitation_received",
    "invitation_withdrawn",
    "memo_cancelled",
    "payment_confirmed",
    "report_resolved",
    "report_received",
    "report_due_soon",
    "report_overdue",
    "content_withheld",
    "content_restored",
    "admin_signed_in",
    "admin_second_factor_refused",
    "admin_second_factor_changed",
    "upi_change_pending",
    "upi_change_cancelled",
    "data_exported",
    "logged_out_everywhere",
)
ADDED_TYPES = (
    "phone_change_requested",
    "phone_change_cancelled",
    "phone_changed",
    "phone_change_failed",
)
NEW_TYPES = OLD_TYPES + ADDED_TYPES
TYPE_CHECK = "ck_notification_type_allowed"

OLD_ACTIONS = ("set_upi_id", "download_export", "log_out_everywhere")
NEW_ACTIONS = OLD_ACTIONS + ("change_phone",)
ACTION_CHECK = "ck_step_up_challenge_action_allowed"


def _swap(table: str, check: str, column: str, values: tuple[str, ...]) -> None:
    """Replace an allowed-values check, NOT VALID, then validate after the transaction."""
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {check}")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {check} "
        f"CHECK ({column} IN {values}) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {check}")


def upgrade() -> None:
    op.create_table(
        "account_phone_change",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("new_phone", sa.String(length=16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("takes_effect_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "new_phone ~ '^\\+91[6-9][0-9]{9}$'",
            name=op.f("ck_account_phone_change_new_phone_format"),
        ),
        sa.CheckConstraint(
            "takes_effect_at = requested_at + interval '72 hours'",
            name=op.f("ck_account_phone_change_takes_effect_three_days_after_request"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_account_phone_change_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_phone_change")),
        sa.UniqueConstraint(
            "account_id", name=op.f("uq_account_phone_change_account_id")
        ),
        sa.UniqueConstraint("new_phone", name=op.f("uq_account_phone_change_new_phone")),
    )
    _swap("step_up_challenge", ACTION_CHECK, "action", NEW_ACTIONS)
    _swap("notification", TYPE_CHECK, "notification_type", NEW_TYPES)


def downgrade() -> None:
    waiting = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM account_phone_change"))
        .scalar_one()
    )
    if waiting:
        raise RuntimeError(
            f"{waiting} accounts are waiting to move to a new phone number, each "
            "asked for with a code from both numbers. Dropping them would undo "
            "those requests without anyone deciding to; remove them "
            "deliberately, as the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    op.execute("DELETE FROM step_up_challenge WHERE action = 'change_phone'")
    _swap("notification", TYPE_CHECK, "notification_type", OLD_TYPES)
    _swap("step_up_challenge", ACTION_CHECK, "action", OLD_ACTIONS)
    op.drop_table("account_phone_change")

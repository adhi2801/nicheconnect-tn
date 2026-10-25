"""account deletion (item 6, D-122)

Apple and Google reject apps that let people make an account but not delete
it, and DPDP Rule 8 asks for erasure. Approved by Adhi on 25 October 2026
(D-122: deletion refused while a deal is unfinished, a 30-day wait the owner
can cancel, the counterparty keeping the deal's facts). This migration:

- adds `account.deletion_requested_at`, `deletion_takes_effect_at` and
  `deleted_at`, nullable with no default, so adding them rewrites nothing;
- lets `account.phone` be NULL, which only a deleted account may be, so the
  number is free for whoever holds it next;
- holds them by four checks, added NOT VALID and validated after the
  transaction, so writes are never blocked;
- widens the step-up actions, on codes and passkey challenges alike, with
  `delete_account`, and the notification types with `deletion_requested`,
  `deletion_cancelled` and `deletion_held_by_deals`.

Data impact: none on existing rows.

Downgrade: refuses while any account has asked to be deleted or has been,
since the phone column could not become required again for a deleted
account, and a waiting request would be silently dropped. Otherwise it
deletes the step-up codes and challenges asked for `delete_account`, and the
three kinds of notification, restores the narrower lists, makes the phone
required again and drops the columns.

Revision ID: b7e026caa4a9
Revises: c80694db3a26
Create Date: 2026-10-25 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e026caa4a9"
down_revision: Union[str, None] = "c80694db3a26"
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
    "phone_change_requested",
    "phone_change_cancelled",
    "phone_changed",
    "phone_change_failed",
    "data_export_ready",
    "data_export_failed",
    "passkey_added",
    "passkey_removed",
    "passkey_reset_requested",
    "passkey_reset_cancelled",
    "passkey_only_changed",
    "session_ended",
)
ADDED_TYPES = ("deletion_requested", "deletion_cancelled", "deletion_held_by_deals")
NEW_TYPES = OLD_TYPES + ADDED_TYPES
TYPE_CHECK = "ck_notification_type_allowed"

OLD_ACTIONS = (
    "set_upi_id",
    "download_export",
    "log_out_everywhere",
    "change_phone",
    "add_passkey",
    "remove_passkey",
    "passkey_only",
    "end_session",
)
ADDED_ACTION = "delete_account"
NEW_ACTIONS = OLD_ACTIONS + (ADDED_ACTION,)
STEP_UP_ACTION_CHECK = "ck_step_up_challenge_action_allowed"
PASSKEY_ACTION_CHECK = "ck_passkey_challenge_action_allowed"

CHECKS = {
    "ck_account_deletion_requested_with_its_date": (
        "(deletion_requested_at IS NULL) = (deletion_takes_effect_at IS NULL)"
    ),
    "ck_account_deletion_takes_effect_thirty_days_after": (
        "deletion_takes_effect_at = deletion_requested_at + interval '30 days'"
    ),
    "ck_account_deleted_only_after_a_request": (
        "deleted_at IS NULL OR deletion_requested_at IS NOT NULL"
    ),
    "ck_account_phone_until_deleted": "(deleted_at IS NULL) = (phone IS NOT NULL)",
}


def _swap(table: str, check: str, condition: str) -> None:
    """Replace a check, NOT VALID, then validate after the transaction."""
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {check}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK ({condition}) NOT VALID")
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {check}")


def _action_lists(values: tuple[str, ...]) -> None:
    _swap("step_up_challenge", STEP_UP_ACTION_CHECK, f"action IN {values}")
    _swap(
        "passkey_challenge",
        PASSKEY_ACTION_CHECK,
        f"action IS NULL OR action IN {values}",
    )


def upgrade() -> None:
    for name in ("deletion_requested_at", "deletion_takes_effect_at", "deleted_at"):
        op.add_column("account", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.alter_column("account", "phone", existing_type=sa.String(length=16), nullable=True)
    for name, condition in CHECKS.items():
        op.execute(f"ALTER TABLE account ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
    _action_lists(NEW_ACTIONS)
    _swap("notification", TYPE_CHECK, f"notification_type IN {NEW_TYPES}")
    with op.get_context().autocommit_block():
        for name in CHECKS:
            op.execute(f"ALTER TABLE account VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    asked = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM account WHERE deletion_requested_at IS NOT NULL"))
        .scalar_one()
    )
    if asked:
        raise RuntimeError(
            f"{asked} accounts have asked to be deleted, or have been. A deleted "
            "account has no phone number, so the number could not be required "
            "again, and a waiting request would be silently dropped; settle each "
            "deliberately, as the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    op.execute(f"DELETE FROM step_up_challenge WHERE action = '{ADDED_ACTION}'")
    op.execute(f"DELETE FROM passkey_challenge WHERE action = '{ADDED_ACTION}'")
    _swap("notification", TYPE_CHECK, f"notification_type IN {OLD_TYPES}")
    _action_lists(OLD_ACTIONS)
    for name in CHECKS:
        op.execute(f"ALTER TABLE account DROP CONSTRAINT {name}")
    op.alter_column("account", "phone", existing_type=sa.String(length=16), nullable=False)
    for name in ("deleted_at", "deletion_takes_effect_at", "deletion_requested_at"):
        op.drop_column("account", name)

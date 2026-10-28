"""connection expired notice (item 29, D-134)

Approved by Adhi on 26 October 2026 (D-134, piece 2: a connection that
stops answering tells its creator). This migration widens the notification
types, and the types a person may mute, with `connection_expired`, each
check swapped NOT VALID and validated after the transaction.

Data impact: none on existing rows.

Downgrade: removes `connection_expired` notifications and mutes, then
narrows both checks again.

Revision ID: 3e711c2efcc6
Revises: 3734d5492968
Create Date: 2026-10-26 18:49:32.603989

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3e711c2efcc6"
down_revision: Union[str, None] = "3734d5492968"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADDED = "connection_expired"

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
    "deletion_requested",
    "deletion_cancelled",
    "deletion_held_by_deals",
    "offer_received",
    "offer_accepted",
    "offer_declined",
    "offer_withdrawn",
    "note_added",
    "campaign_alert",
    "product_shipped",
    "product_received",
)

OLD_MUTABLE = (
    "application_received",
    "application_withdrawn",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "invitation_accepted",
    "invitation_declined",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "proof_approved",
    "proof_auto_approved",
    "invitation_received",
    "invitation_withdrawn",
    "memo_cancelled",
    "payment_confirmed",
    "report_resolved",
    "report_received",
    "content_restored",
    "offer_received",
    "offer_accepted",
    "offer_declined",
    "offer_withdrawn",
    "note_added",
    "campaign_alert",
    "product_shipped",
    "product_received",
)


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_lists(types: tuple[str, ...], mutable: tuple[str, ...]) -> None:
    """Replace both lists' checks, NOT VALID, then validate after the transaction."""
    checks = (
        ("notification", "ck_notification_type_allowed", f"notification_type IN {types}"),
        (
            "notification_preference",
            "ck_notification_preference_muted_types_allowed",
            f"muted_types <@ {_array(mutable)}",
        ),
    )
    for table, name, condition in checks:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
    with op.get_context().autocommit_block():
        for table, name, _ in checks:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    _swap_lists(OLD_TYPES + (ADDED,), OLD_MUTABLE + (ADDED,))


def downgrade() -> None:
    op.execute(f"DELETE FROM notification WHERE notification_type = '{ADDED}'")
    op.execute(
        "UPDATE notification_preference"
        f" SET muted_types = array_remove(muted_types, '{ADDED}')"
        f" WHERE '{ADDED}' = ANY (muted_types)"
    )
    _swap_lists(OLD_TYPES, OLD_MUTABLE)

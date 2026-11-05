"""brand changed hands notice (item 13, D-151)

Approved by Adhi on 4 November 2026 (D-151; docs/decided/PROPOSAL_HAND_OVER_NOTICE.md):
when a brand is handed to a new owner, each creator with a deal still
unfinished with it is told. This migration widens the notification types
with `brand_changed_hands`. It says who holds a business's account on a deal
in progress, so it is urgent, and the types a person may mute are unchanged.
The check is swapped NOT VALID and validated after the transaction, as
D-148's was, so the table is never held locked while it is read.

Data impact: none on existing rows.

Downgrade: refuses while any `brand_changed_hands` notice exists, since each
is the record that a creator was told; otherwise narrows the check back.

Revision ID: 7ac9c63d532e
Revises: 6de6ca38de81
Create Date: 2026-11-04 18:06:47.954781

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7ac9c63d532e"
down_revision: Union[str, None] = "6de6ca38de81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTICE = "brand_changed_hands"

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_TYPES = (
    "application_received", "application_withdrawn", "memo_accepted", "memo_declined",
    "memo_change_requested", "proof_submitted", "invitation_accepted",
    "invitation_declined", "application_shortlisted", "application_accepted",
    "application_rejected", "memo_sent", "proof_approved", "proof_auto_approved",
    "proof_revision_requested", "payment_marked_paid", "invitation_received",
    "invitation_withdrawn", "memo_cancelled", "payment_confirmed", "report_resolved",
    "report_received", "report_due_soon", "report_overdue", "content_withheld",
    "content_restored", "admin_signed_in", "admin_second_factor_refused",
    "admin_second_factor_changed", "upi_change_pending", "upi_change_cancelled",
    "data_exported", "logged_out_everywhere", "phone_change_requested",
    "phone_change_cancelled", "phone_changed", "phone_change_failed", "data_export_ready",
    "data_export_failed", "passkey_added", "passkey_removed", "passkey_reset_requested",
    "passkey_reset_cancelled", "passkey_only_changed", "session_ended",
    "deletion_requested", "deletion_cancelled", "deletion_held_by_deals", "offer_received",
    "offer_accepted", "offer_declined", "offer_withdrawn", "note_added", "campaign_alert",
    "product_shipped", "product_received", "connection_expired", "feedback_received",
    "agent_token_created", "draft_submitted", "draft_approved", "draft_auto_approved",
    "draft_changes_requested", "team_invite_received", "team_joined", "team_role_changed",
    "team_removed",
)
TYPE_CHECK = "ck_notification_type_allowed"


def _swap(condition: str) -> None:
    """Replace the check, NOT VALID, then validate after the transaction."""
    op.execute(f"ALTER TABLE notification DROP CONSTRAINT {TYPE_CHECK}")
    op.execute(
        f"ALTER TABLE notification ADD CONSTRAINT {TYPE_CHECK} CHECK ({condition}) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE notification VALIDATE CONSTRAINT {TYPE_CHECK}")


def upgrade() -> None:
    _swap(f"notification_type IN {OLD_TYPES + (NOTICE,)}")


def downgrade() -> None:
    told = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM notification WHERE notification_type = :notice"),
            {"notice": NOTICE},
        )
        .scalar_one()
    )
    if told:
        raise RuntimeError(
            f"{told} creators were told a brand changed hands. Each notice is the "
            "record that they were; settle them deliberately if that is really intended."
        )
    _swap(f"notification_type IN {OLD_TYPES}")

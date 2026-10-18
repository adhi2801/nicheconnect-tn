"""data export: a failed build retries, then the owner is told (D-112)

A build that failed was marked failed at once and nobody was told, against
backend.md section 7 (failed jobs retry, then fail where someone can see).
Approved by Adhi on 18 October 2026 (D-112, option A). This migration:

- adds `data_export.attempts`, the tries at building it that failed (0 to 3,
  a constant default, so adding it rewrites nothing);
- holds that an export is failed only once all 3 tries are spent. Rows
  already failed are counted as having spent them first, so the rule holds
  for them too; the checks are added NOT VALID and validated after the
  transaction, so writes are never blocked;
- adds the notification type `data_export_failed`, urgent and so never
  mutable.

Data impact: exports already failed get `attempts = 3`; none exist outside
development.

Downgrade: deletes the new kind of notification, restores the narrower
list, and drops the two checks and the column. Nothing a person gave us is
lost: a count of failed tries.

Revision ID: 046f91e53bb4
Revises: 928b6af0172c
Create Date: 2026-10-18 16:07:50.082692

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "046f91e53bb4"
down_revision: Union[str, None] = "928b6af0172c"
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
)
NEW_TYPES = (*OLD_TYPES, "data_export_failed")
TYPE_CHECK = "ck_notification_type_allowed"
ATTEMPTS_RANGE = "ck_data_export_attempts_range"
FAILED_AFTER_EVERY_TRY = "ck_data_export_failed_after_every_try"


def _swap_types(types: tuple[str, ...]) -> None:
    """Replace the allowed types, NOT VALID, then validate after the transaction."""
    op.execute(f"ALTER TABLE notification DROP CONSTRAINT {TYPE_CHECK}")
    op.execute(
        f"ALTER TABLE notification ADD CONSTRAINT {TYPE_CHECK} "
        f"CHECK (notification_type IN {types}) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE notification VALIDATE CONSTRAINT {TYPE_CHECK}")


def upgrade() -> None:
    op.add_column(
        "data_export",
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.execute("UPDATE data_export SET attempts = 3 WHERE failed_at IS NOT NULL")
    op.execute(
        f"ALTER TABLE data_export ADD CONSTRAINT {ATTEMPTS_RANGE} "
        "CHECK (attempts BETWEEN 0 AND 3) NOT VALID"
    )
    op.execute(
        f"ALTER TABLE data_export ADD CONSTRAINT {FAILED_AFTER_EVERY_TRY} "
        "CHECK (failed_at IS NULL OR attempts = 3) NOT VALID"
    )
    _swap_types(NEW_TYPES)
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE data_export VALIDATE CONSTRAINT {ATTEMPTS_RANGE}")
        op.execute(f"ALTER TABLE data_export VALIDATE CONSTRAINT {FAILED_AFTER_EVERY_TRY}")


def downgrade() -> None:
    op.execute("DELETE FROM notification WHERE notification_type = 'data_export_failed'")
    _swap_types(OLD_TYPES)
    op.execute(f"ALTER TABLE data_export DROP CONSTRAINT {FAILED_AFTER_EVERY_TRY}")
    op.execute(f"ALTER TABLE data_export DROP CONSTRAINT {ATTEMPTS_RANGE}")
    op.drop_column("data_export", "attempts")

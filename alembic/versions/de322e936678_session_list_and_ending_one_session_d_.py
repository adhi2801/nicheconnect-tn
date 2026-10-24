"""sessions: seeing where you are logged in, and ending one (item 81, D-114)

Nobody could see their sessions, or end one without ending them all, and
nothing told one session from another. Approved by Adhi on 24 October 2026
(D-114, option A: no address or location stored). This migration:

- adds `auth_session.client_platform` (`android`, `ios` or `web`) and
  `auth_session.client_label` (what the app said it is, 1 to 60 characters,
  trimmed, no control characters), both NULL or both set. Nullable, with no
  default, so adding them rewrites nothing; their checks are added NOT VALID
  and validated after the transaction, so writes are never blocked;
- widens the step-up actions, on step-up codes and passkey challenges alike,
  with `end_session`;
- adds one notification type, urgent: `session_ended`.

No index: listing reads an account's sessions by `ix_auth_session_account_id`,
and the per-request check reads one session by `ix_auth_session_family_id`.

Data impact: none on existing rows. Sessions from before this show no
device until their next sign-in.

Downgrade: refuses while any `session_ended` notice exists, since dropping
it would silently remove a person's record that one of their sessions was
ended. Otherwise it deletes the step-up codes and passkey challenges asked
for `end_session` (5-minute lives), restores the narrower lists and drops
the two columns: the device labels are lost, which only describe devices.

Revision ID: de322e936678
Revises: ceeda50f8c0b
Create Date: 2026-10-24 18:09:32.954163

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "de322e936678"
down_revision: Union[str, None] = "ceeda50f8c0b"
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
)
ADDED_TYPE = "session_ended"
NEW_TYPES = OLD_TYPES + (ADDED_TYPE,)
TYPE_CHECK = "ck_notification_type_allowed"

OLD_ACTIONS = (
    "set_upi_id",
    "download_export",
    "log_out_everywhere",
    "change_phone",
    "add_passkey",
    "remove_passkey",
    "passkey_only",
)
ADDED_ACTION = "end_session"
NEW_ACTIONS = OLD_ACTIONS + (ADDED_ACTION,)
STEP_UP_ACTION_CHECK = "ck_step_up_challenge_action_allowed"
PASSKEY_ACTION_CHECK = "ck_passkey_challenge_action_allowed"

PLATFORM_CHECK = "ck_auth_session_client_platform_allowed"
LABEL_CHECK = "ck_auth_session_client_label_shape"
TOGETHER_CHECK = "ck_auth_session_client_platform_and_label_together"
NEW_CHECKS = {
    PLATFORM_CHECK: "client_platform IS NULL OR client_platform IN ('android', 'ios', 'web')",
    LABEL_CHECK: (
        "client_label IS NULL OR (char_length(client_label) BETWEEN 1 AND 60"
        " AND client_label = btrim(client_label)"
        " AND client_label !~ '[[:cntrl:]]')"
    ),
    TOGETHER_CHECK: "(client_platform IS NULL) = (client_label IS NULL)",
}


def _swap(table: str, check: str, condition: str) -> None:
    """Replace a check, NOT VALID, then validate after the transaction."""
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {check}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK ({condition}) NOT VALID")
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {check}")


def _actions(values: tuple[str, ...]) -> tuple[str, str]:
    return f"action IN {values}", f"action IS NULL OR action IN {values}"


def upgrade() -> None:
    op.add_column(
        "auth_session",
        sa.Column("client_platform", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "auth_session",
        sa.Column("client_label", sa.String(length=60), nullable=True),
    )
    for name, condition in NEW_CHECKS.items():
        op.execute(
            f"ALTER TABLE auth_session ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )
    step_up, passkey = _actions(NEW_ACTIONS)
    _swap("step_up_challenge", STEP_UP_ACTION_CHECK, step_up)
    _swap("passkey_challenge", PASSKEY_ACTION_CHECK, passkey)
    _swap("notification", TYPE_CHECK, f"notification_type IN {NEW_TYPES}")
    with op.get_context().autocommit_block():
        for name in NEW_CHECKS:
            op.execute(f"ALTER TABLE auth_session VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    held = (
        op.get_bind()
        .execute(
            sa.text("SELECT count(*) FROM notification WHERE notification_type = :kind"),
            {"kind": ADDED_TYPE},
        )
        .scalar_one()
    )
    if held:
        raise RuntimeError(
            f"{held} notices tell people that one of their sessions was ended. "
            "Dropping them would silently remove that record from their "
            "accounts; delete them deliberately, as the owner, if that is "
            "really intended."
        )
    op.execute(f"DELETE FROM step_up_challenge WHERE action = '{ADDED_ACTION}'")
    op.execute(f"DELETE FROM passkey_challenge WHERE action = '{ADDED_ACTION}'")
    _swap("notification", TYPE_CHECK, f"notification_type IN {OLD_TYPES}")
    step_up, passkey = _actions(OLD_ACTIONS)
    _swap("passkey_challenge", PASSKEY_ACTION_CHECK, passkey)
    _swap("step_up_challenge", STEP_UP_ACTION_CHECK, step_up)
    for name in NEW_CHECKS:
        op.execute(f"ALTER TABLE auth_session DROP CONSTRAINT {name}")
    op.drop_column("auth_session", "client_label")
    op.drop_column("auth_session", "client_platform")

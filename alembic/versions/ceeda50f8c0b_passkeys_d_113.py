"""passkeys: signing in and approving changes with a key on the person's device (D-113)

A login code goes to whoever holds the number, so a SIM swapper gets every
code; nothing on a brand's or creator's account could stop one for good.
Approved by Adhi on 18 October 2026 (D-113, option B; fido2 2.2.1): passkeys,
bound to our domain, that log in, and that alone prove every risky change
once an account has one; a 7-day reset for someone who lost them all, and
optional passkey-only sign-in. Then "Add the column" twice, "Yes, its own
alert" and "Phone and code, no login" to the details stated before building.
This migration:

- creates `passkey`: the public half of each key a person added, its
  authenticator's make, its counter, whether it syncs, a name and its last
  use. Never a fingerprint, a face or a private key, which never leave the
  phone. Each credential id is unique;
- creates `passkey_challenge`: each challenge sent, used once within 5
  minutes, and, for a change, bound to its action and an HMAC of its value;
- creates `passkey_reset`: at most one per account, taking effect exactly 7
  days after it was asked for;
- adds `account.passkey_only` (false), `auth_session.passkey_at` (NULL), and
  `step_up_challenge.method` ('phone_code'), each with a constant default,
  so adding them rewrites nothing;
- widens the step-up actions with `add_passkey`, `remove_passkey` and
  `passkey_only`, holds `step_up_challenge.method` to its two values, and
  adds five notification types, every one urgent: `passkey_added`,
  `passkey_removed`, `passkey_reset_requested`, `passkey_reset_cancelled`,
  `passkey_only_changed`. Each list is swapped NOT VALID and validated after
  the transaction, so writes are never blocked.

ON DELETE: CASCADE throughout, since keys, challenges and resets mean
nothing without their account. Each foreign key is served by an index whose
first column is it (the reset's by its unique constraint).

Data impact: none on existing rows.

Downgrade: refuses while any passkey exists, since dropping them would
silently weaken those accounts back to a phone code alone. Otherwise it
deletes the new kinds of notification and the step-up codes asked for the
new actions or proven by a passkey, restores the narrower lists and drops
the columns and tables.

Revision ID: ceeda50f8c0b
Revises: 046f91e53bb4
Create Date: 2026-10-18 19:42:35.919494

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ceeda50f8c0b"
down_revision: Union[str, None] = "046f91e53bb4"
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
)
ADDED_TYPES = (
    "passkey_added",
    "passkey_removed",
    "passkey_reset_requested",
    "passkey_reset_cancelled",
    "passkey_only_changed",
)
NEW_TYPES = OLD_TYPES + ADDED_TYPES
TYPE_CHECK = "ck_notification_type_allowed"

OLD_ACTIONS = ("set_upi_id", "download_export", "log_out_everywhere", "change_phone")
ADDED_ACTIONS = ("add_passkey", "remove_passkey", "passkey_only")
NEW_ACTIONS = OLD_ACTIONS + ADDED_ACTIONS
ACTION_CHECK = "ck_step_up_challenge_action_allowed"
METHOD_CHECK = "ck_step_up_challenge_method_allowed"


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
        "passkey",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("aaguid", sa.UUID(), nullable=False),
        sa.Column("backup_eligible", sa.Boolean(), nullable=False),
        sa.Column("backup_state", sa.Boolean(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
            "backup_eligible OR NOT backup_state",
            name=op.f("ck_passkey_backed_up_only_if_eligible"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) > 0", name=op.f("ck_passkey_name_not_blank")
        ),
        sa.CheckConstraint(
            "last_used_at IS NULL OR last_used_at >= created_at",
            name=op.f("ck_passkey_used_after_added"),
        ),
        sa.CheckConstraint(
            "octet_length(credential_id) BETWEEN 16 AND 1023",
            name=op.f("ck_passkey_credential_id_length"),
        ),
        sa.CheckConstraint(
            "octet_length(public_key) BETWEEN 1 AND 1024",
            name=op.f("ck_passkey_public_key_length"),
        ),
        sa.CheckConstraint(
            "sign_count >= 0", name=op.f("ck_passkey_sign_count_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_passkey_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkey_credential_id")),
    )
    op.create_index("ix_passkey_account_id", "passkey", ["account_id"], unique=False)
    op.create_table(
        "passkey_challenge",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=True),
        sa.Column("value_hash", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
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
            "(purpose = 'step_up') = (action IS NOT NULL) AND (action IS NULL) = (value_hash IS NULL)",
            name=op.f("ck_passkey_challenge_change_only_for_step_up"),
        ),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('set_upi_id', 'download_export', 'log_out_everywhere', 'change_phone', 'add_passkey', 'remove_passkey', 'passkey_only')",
            name=op.f("ck_passkey_challenge_action_allowed"),
        ),
        sa.CheckConstraint(
            "expires_at = created_at + interval '5 minutes'",
            name=op.f("ck_passkey_challenge_expires_five_minutes_after_created"),
        ),
        sa.CheckConstraint(
            "purpose = 'login' OR account_id IS NOT NULL",
            name=op.f("ck_passkey_challenge_account_unless_login"),
        ),
        sa.CheckConstraint(
            "purpose IN ('register', 'login', 'step_up')",
            name=op.f("ck_passkey_challenge_purpose_allowed"),
        ),
        sa.CheckConstraint(
            "value_hash IS NULL OR value_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_passkey_challenge_value_hash_format"),
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name=op.f("ck_passkey_challenge_consumed_after_created"),
        ),
        sa.CheckConstraint(
            "octet_length(challenge) = 32",
            name=op.f("ck_passkey_challenge_challenge_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_passkey_challenge_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey_challenge")),
        sa.UniqueConstraint("challenge", name=op.f("uq_passkey_challenge_challenge")),
    )
    op.create_index(
        "ix_passkey_challenge_account_id_created_at",
        "passkey_challenge",
        ["account_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_passkey_challenge_expires_at",
        "passkey_challenge",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "passkey_reset",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
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
            "takes_effect_at = requested_at + interval '7 days'",
            name=op.f("ck_passkey_reset_takes_effect_seven_days_after_request"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_passkey_reset_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkey_reset")),
        sa.UniqueConstraint("account_id", name=op.f("uq_passkey_reset_account_id")),
    )
    op.add_column(
        "account",
        sa.Column(
            "passkey_only", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "auth_session", sa.Column("passkey_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "step_up_challenge",
        sa.Column(
            "method",
            sa.String(length=12),
            server_default=sa.text("'phone_code'"),
            nullable=False,
        ),
    )
    op.execute(
        f"ALTER TABLE step_up_challenge ADD CONSTRAINT {METHOD_CHECK} "
        "CHECK (method IN ('phone_code', 'passkey')) NOT VALID"
    )
    _swap("step_up_challenge", ACTION_CHECK, "action", NEW_ACTIONS)
    _swap("notification", TYPE_CHECK, "notification_type", NEW_TYPES)
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE step_up_challenge VALIDATE CONSTRAINT {METHOD_CHECK}")


def downgrade() -> None:
    held = op.get_bind().execute(sa.text("SELECT count(*) FROM passkey")).scalar_one()
    if held:
        raise RuntimeError(
            f"{held} passkeys are on people's accounts, guarding their risky "
            "changes. Dropping them would weaken those accounts back to a phone "
            "code alone without anyone deciding to; remove them deliberately, as "
            "the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    op.execute(
        f"DELETE FROM step_up_challenge WHERE action IN {ADDED_ACTIONS} "
        "OR method = 'passkey'"
    )
    _swap("notification", TYPE_CHECK, "notification_type", OLD_TYPES)
    _swap("step_up_challenge", ACTION_CHECK, "action", OLD_ACTIONS)
    op.execute(f"ALTER TABLE step_up_challenge DROP CONSTRAINT {METHOD_CHECK}")
    op.drop_column("step_up_challenge", "method")
    op.drop_column("auth_session", "passkey_at")
    op.drop_column("account", "passkey_only")
    op.drop_table("passkey_reset")
    op.drop_index("ix_passkey_challenge_expires_at", table_name="passkey_challenge")
    op.drop_index(
        "ix_passkey_challenge_account_id_created_at", table_name="passkey_challenge"
    )
    op.drop_table("passkey_challenge")
    op.drop_index("ix_passkey_account_id", table_name="passkey")
    op.drop_table("passkey")

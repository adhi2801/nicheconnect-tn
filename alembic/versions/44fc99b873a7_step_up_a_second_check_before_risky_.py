"""step up: a second check before risky changes, and a new UPI ID's wait (item 82)

A stolen session could set a creator's UPI ID, take their data export or
log them out everywhere with the access token alone. Approved by Adhi on 17
October 2026, option A (D-107): a code sent to the phone for each risky
change, good for that change only, and a 24-hour wait on a new UPI ID,
since a SIM swap gets the code too. This migration:

- creates `step_up_challenge`: one row per code asked for, holding the
  account, the action, an HMAC of the action and its new value, an HMAC of
  the code, the wrong tries (at most 5), when it expires (exactly 5 minutes
  after it was made) and when it was used. Never the code or the value;
- creates `creator_upi_change`: at most one per creator, a new UPI ID with
  its own consent and the moment brands start to see it (exactly 24 hours
  after the consent), under the same checks as `creator_upi`, so it is never
  malformed and never a phone number. `creator_upi` itself is unchanged;
- adds four notification types, every one urgent and so never mutable:
  `upi_change_pending`, `upi_change_cancelled`, `data_exported` and
  `logged_out_everywhere`. The muted-types list is unchanged, since no new
  type may be muted.

New, empty tables: their constraints and indexes are created whole
(database.md section 6). The widened type list is swapped NOT VALID in the
migration's transaction and validated after it commits, so writes are never
blocked (Squawk, D-050).

ON DELETE: both CASCADE, since a code means nothing without its account and
a waiting UPI ID is the creator's own. The step-up index on (account_id,
created_at DESC) serves its foreign key; the waiting ID's unique constraint
serves its.

Data impact: none on existing rows. After it, setting a UPI ID, the export
and logging out everywhere need a code (the code that ships with it).

Downgrade: refuses while any new UPI ID is waiting, since each is a consent
record and dropping it would quietly undo a creator's change. Otherwise it
deletes the four new kinds of notification, restores the narrower list and
drops both tables; the step-up codes are short-lived and go with their
table.

Revision ID: 44fc99b873a7
Revises: 8a974ebde203
Create Date: 2026-10-17 17:52:26.567106

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "44fc99b873a7"
down_revision: Union[str, None] = "8a974ebde203"
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
)
ADDED_TYPES = (
    "upi_change_pending",
    "upi_change_cancelled",
    "data_exported",
    "logged_out_everywhere",
)
NEW_TYPES = OLD_TYPES + ADDED_TYPES
TYPE_CHECK = "ck_notification_type_allowed"


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
    op.create_table(
        "step_up_challenge",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("value_hash", sa.String(length=64), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
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
            "action IN ('set_upi_id', 'download_export', 'log_out_everywhere')",
            name=op.f("ck_step_up_challenge_action_allowed"),
        ),
        sa.CheckConstraint(
            "code_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_step_up_challenge_code_hash_format"),
        ),
        sa.CheckConstraint(
            "expires_at = created_at + interval '5 minutes'",
            name=op.f("ck_step_up_challenge_expires_five_minutes_after_created"),
        ),
        sa.CheckConstraint(
            "value_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_step_up_challenge_value_hash_format"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5",
            name=op.f("ck_step_up_challenge_attempts_range"),
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name=op.f("ck_step_up_challenge_consumed_after_created"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_step_up_challenge_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_step_up_challenge")),
    )
    op.create_index(
        "ix_step_up_challenge_account_id_created_at",
        "step_up_challenge",
        ["account_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "creator_upi_change",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("creator_id", sa.UUID(), nullable=False),
        sa.Column("upi_id", sa.String(length=128), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notice_version", sa.String(length=40), nullable=False),
        sa.Column("usable_at", sa.DateTime(timezone=True), nullable=False),
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
            "split_part(upi_id, '@', 1) !~ '^(91)?[6-9][0-9]{9}$'",
            name=op.f("ck_creator_upi_change_upi_id_not_a_phone_number"),
        ),
        sa.CheckConstraint(
            "upi_id ~ '^[a-z0-9._-]{2,64}@[a-z][a-z0-9]{1,63}$'",
            name=op.f("ck_creator_upi_change_upi_id_format"),
        ),
        sa.CheckConstraint(
            "usable_at = consented_at + interval '24 hours'",
            name=op.f("ck_creator_upi_change_usable_a_day_after_consent"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(notice_version)) > 0",
            name=op.f("ck_creator_upi_change_notice_version_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["creator_id"],
            ["creator.id"],
            name=op.f("fk_creator_upi_change_creator_id_creator"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_creator_upi_change")),
        sa.UniqueConstraint("creator_id", name=op.f("uq_creator_upi_change_creator_id")),
    )
    _swap_types(NEW_TYPES)


def downgrade() -> None:
    waiting = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM creator_upi_change"))
        .scalar_one()
    )
    if waiting:
        raise RuntimeError(
            f"{waiting} creators have a new UPI ID waiting, each with the consent "
            "they gave for it. Dropping them would undo their changes without "
            "anyone deciding to; remove them deliberately, as the owner, if that "
            "is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    _swap_types(OLD_TYPES)
    op.drop_table("creator_upi_change")
    # Its index goes with it.
    op.drop_table("step_up_challenge")

"""admin second factor: totp_factor, sessions with two factors (item 101)

Admins logged in with one factor, the code sent to their phone, so a SIM
swap or a stolen WhatsApp was an admin session, and since item 52 an admin
can withhold anyone's content. Approved by Adhi on 16 October 2026, option
A: an authenticator app's codes now, passkeys with item 79 (D-105). This
migration:

- creates `totp_factor`: one per account, either waiting for setup (a
  founder's ticket, kept only as its SHA-256, with its expiry) or enrolled
  (the secret, kept only encrypted under SECOND_FACTOR_KEY), with the last
  step accepted (each code works once), the failures in a row and the lock
  they lead to. Its checks hold each of those pairings;
- adds `auth_session.second_factor_at`: when the login behind a session
  proved a second factor, carried through every rotation, so an admin's
  session ends 12 hours after it and the tokens say `mfa`;
- ends every admin session still open: each was made from the phone code
  alone, and would otherwise carry on for up to a day;
- adds three notification types, every one urgent and so never mutable:
  `admin_signed_in`, `admin_second_factor_refused` and
  `admin_second_factor_changed`. The muted-types list is unchanged, since
  no new type may be muted.

New, empty table: its constraints are created whole (database.md section
6). The new column is nullable with no default, so adding it rewrites
nothing. The widened type list is swapped NOT VALID in the migration's
transaction and validated after it commits, so writes are never blocked
(Squawk, D-050).

ON DELETE: `account_id` CASCADE, since a factor means nothing without its
account. Its unique constraint is the index the foreign key needs.

Data impact: open admin sessions end, so every admin logs in again, with
two factors, after a founder issues them a setup ticket
(`scripts/make_admin.py <phone> --second-factor`). Nothing else changes.

Downgrade: refuses while any authenticator is set up or waiting, since
dropping them would quietly put every admin back on one factor. On an empty
table it deletes the three new kinds of notification, restores the
narrower list, and drops the column and the table.

Revision ID: 90b4db0fd32a
Revises: 4a2f6982641f
Create Date: 2026-10-16 22:36:50.075300

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "90b4db0fd32a"
down_revision: Union[str, None] = "4a2f6982641f"
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
)
ADDED_TYPES = (
    "admin_signed_in",
    "admin_second_factor_refused",
    "admin_second_factor_changed",
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
        "totp_factor",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("ticket_hash", sa.String(length=64), nullable=True),
        sa.Column("ticket_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
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
            "ticket_hash IS NULL OR ticket_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_totp_factor_ticket_hash_format"),
        ),
        sa.CheckConstraint(
            "(locked_at IS NOT NULL) = (consecutive_failures = 10)",
            name=op.f("ck_totp_factor_locked_at_the_limit"),
        ),
        sa.CheckConstraint(
            "(secret_ciphertext IS NULL) <> (ticket_hash IS NULL)",
            name=op.f("ck_totp_factor_waiting_or_enrolled"),
        ),
        sa.CheckConstraint(
            "(secret_ciphertext IS NULL) = (enrolled_at IS NULL)",
            name=op.f("ck_totp_factor_enrolled_when_it_has_a_secret"),
        ),
        sa.CheckConstraint(
            "(ticket_hash IS NULL) = (ticket_expires_at IS NULL)",
            name=op.f("ck_totp_factor_ticket_has_an_expiry"),
        ),
        sa.CheckConstraint(
            "consecutive_failures BETWEEN 0 AND 10",
            name=op.f("ck_totp_factor_consecutive_failures_range"),
        ),
        sa.CheckConstraint(
            "last_used_step IS NULL OR last_used_step >= 0",
            name=op.f("ck_totp_factor_last_used_step_not_negative"),
        ),
        sa.CheckConstraint(
            "secret_ciphertext IS NULL OR octet_length(secret_ciphertext) = 48",
            name=op.f("ck_totp_factor_secret_ciphertext_length"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_totp_factor_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_totp_factor")),
        sa.UniqueConstraint("account_id", name=op.f("uq_totp_factor_account_id")),
    )
    op.add_column(
        "auth_session",
        sa.Column("second_factor_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Every open admin session was made from the phone code alone.
    op.execute(
        "UPDATE auth_session SET revoked_at = now(), updated_at = now() "
        "WHERE revoked_at IS NULL "
        "AND account_id IN (SELECT id FROM account WHERE role = 'admin')"
    )
    _swap_types(NEW_TYPES)


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM totp_factor"))
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} admin authenticators are set up or waiting. Dropping them "
            "would put every admin back on one factor without anyone choosing "
            "it; remove them deliberately, as the owner, if that is really "
            "intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    _swap_types(OLD_TYPES)
    op.drop_column("auth_session", "second_factor_at")
    op.drop_table("totp_factor")

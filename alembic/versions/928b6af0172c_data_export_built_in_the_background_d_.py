"""data export built in the background, downloaded once (D-111)

The data export was built inside the request: it reads every table an
account appears in, so a busy account's took 300 to 400 ms at p95, over the
300 ms budget, and only grows with its history. Approved by Adhi on 18
October 2026 (D-111): asked for, built by a job, downloaded once with a code,
the stored copy encrypted and destroyed at download or after 24 hours. Then
"As described" to this table. This migration:

- creates `data_export`: one row per export asked for, holding the account,
  when it was asked for, made ready, downloaded and destroyed, when an
  undownloaded one expires (exactly 24 hours after ready), its size, and
  whether building it failed. Never the file, which is stored encrypted
  under `exports/<id>.json`. At most one being prepared per account (a
  partial unique index, which also serves the job's search);
- adds the notification type `data_export_ready`, urgent and so never
  mutable. The muted-types list is unchanged.

A new, empty table: its constraints and indexes are created whole
(database.md section 6). The widened type list is swapped NOT VALID and
validated after the transaction commits, so writes are never blocked.

ON DELETE: CASCADE, since a person's own exports go with their account. The
index on (account_id, requested_at DESC) serves the foreign key.

Data impact: none on existing rows.

Downgrade: refuses while any export is being prepared or has a file still
stored: dropping the table would leave a copy of someone's whole record in
storage with nothing left to destroy it. Otherwise it deletes the new kind of
notification, restores the narrower list and drops the table.

Revision ID: 928b6af0172c
Revises: 8bfc55b8e5fe
Create Date: 2026-10-18 14:02:33.748985

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "928b6af0172c"
down_revision: Union[str, None] = "8bfc55b8e5fe"
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
)
ADDED_TYPES = ("data_export_ready",)
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
        "data_export",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "expires_at IS NULL OR expires_at = ready_at + interval '24 hours'",
            name=op.f("ck_data_export_expires_a_day_after_ready"),
        ),
        sa.CheckConstraint(
            "(ready_at IS NULL) = (expires_at IS NULL)"
            " AND (ready_at IS NULL) = (size_bytes IS NULL)",
            name=op.f("ck_data_export_ready_has_a_file"),
        ),
        sa.CheckConstraint(
            "downloaded_at IS NULL OR (ready_at IS NOT NULL AND downloaded_at >= "
            "ready_at AND downloaded_at < expires_at)",
            name=op.f("ck_data_export_downloaded_while_ready"),
        ),
        sa.CheckConstraint(
            "failed_at IS NULL OR (ready_at IS NULL AND failed_at >= requested_at)",
            name=op.f("ck_data_export_failed_never_ready"),
        ),
        sa.CheckConstraint(
            "file_deleted_at IS NULL OR ready_at IS NOT NULL",
            name=op.f("ck_data_export_deleted_only_once_made"),
        ),
        sa.CheckConstraint(
            "ready_at IS NULL OR ready_at >= requested_at",
            name=op.f("ck_data_export_ready_after_asked"),
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes > 0",
            name=op.f("ck_data_export_size_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("fk_data_export_account_id_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_export")),
    )
    op.create_index(
        "ix_data_export_account_id_requested_at",
        "data_export",
        ["account_id", sa.literal_column("requested_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_data_export_one_preparing",
        "data_export",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("ready_at IS NULL AND failed_at IS NULL"),
    )
    _swap_types(NEW_TYPES)


def downgrade() -> None:
    open_files = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM data_export WHERE failed_at IS NULL "
                "AND (ready_at IS NULL OR file_deleted_at IS NULL)"
            )
        )
        .scalar_one()
    )
    if open_files:
        raise RuntimeError(
            f"{open_files} data exports are being prepared or have a file still "
            "stored. Dropping the table would leave copies of people's whole "
            "records in storage with nothing to destroy them; wait for them to "
            "be downloaded or to expire, or destroy them deliberately first."
        )
    # One type, written out: a one-item tuple would print with a trailing comma.
    op.execute("DELETE FROM notification WHERE notification_type = 'data_export_ready'")
    _swap_types(OLD_TYPES)
    op.drop_table("data_export")

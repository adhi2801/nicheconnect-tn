"""deal notes on the record (item 17, D-128)

Approved by Adhi on 26 October 2026 (D-128: notes from the memo being sent;
sealed and append-only). This migration:

- creates `deal_note`, new and empty, so its checks and index are made
  whole. ON DELETE RESTRICT on the memo: what was said must never vanish as
  a side effect. The index `(deal_memo_id, created_at)` is the thread's and
  the foreign key's;
- seals it as dispute events are sealed (item 99): triggers refuse UPDATE,
  DELETE and TRUNCATE, through the existing `append_only_refuse_change()`,
  and the app's own role loses those rights (D-100), so the app's login may
  only read and add;
- widens the deal record's kinds with `note_added`, and the notification
  types and the types a person may mute with `note_added`, each check
  swapped NOT VALID and validated after the transaction.

Data impact: none on existing rows.

Downgrade: refuses while any note or `note_added` record entry exists, since
dropping either would destroy what both sides can prove was said; otherwise
it reverses each step.

Revision ID: a9188046bec4
Revises: 413468ae18cf
Create Date: 2026-10-26 01:04:21.335685

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9188046bec4"
down_revision: Union[str, None] = "413468ae18cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_WRITER = "app_writer"
ADDED = "note_added"

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_KINDS = (
    "record_started",
    "memo_sent",
    "memo_change_requested",
    "memo_accepted",
    "memo_declined",
    "memo_cancelled",
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "proof_file_cleaned",
    "proof_results_read",
    "payment_opened",
    "payment_marked_paid",
    "payment_confirmed",
    "dispute_opened",
    "dispute_entry_added",
    "dispute_closed",
)
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
)


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_lists(kinds: tuple[str, ...], types: tuple[str, ...], mutable: tuple[str, ...]) -> None:
    """Replace the three lists' checks, NOT VALID, then validate after the transaction."""
    checks = (
        ("deal_record_entry", "ck_deal_record_entry_kind_allowed", f"kind IN {kinds}"),
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
    op.create_table(
        "deal_note",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("deal_memo_id", sa.UUID(), nullable=False),
        sa.Column("author_side", sa.String(length=10), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "author_side IN ('brand', 'creator')", name=op.f("ck_deal_note_author_side_allowed")
        ),
        sa.CheckConstraint(
            "char_length(btrim(body)) BETWEEN 1 AND 1000", name=op.f("ck_deal_note_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["deal_memo_id"],
            ["deal_memo.id"],
            name=op.f("fk_deal_note_deal_memo_id_deal_memo"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deal_note")),
    )
    op.create_index(
        "ix_deal_note_deal_memo_id_created_at",
        "deal_note",
        ["deal_memo_id", "created_at"],
        unique=False,
    )
    op.execute(
        "CREATE TRIGGER deal_note_no_update_or_delete "
        "BEFORE UPDATE OR DELETE ON deal_note "
        "FOR EACH ROW EXECUTE FUNCTION append_only_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER deal_note_no_truncate "
        "BEFORE TRUNCATE ON deal_note "
        "FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse_change()"
    )
    # The default privileges gave app_writer every row right; a note is
    # only ever read and added (D-100).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON deal_note FROM {APP_WRITER}")
    _swap_lists(OLD_KINDS + (ADDED,), OLD_TYPES + (ADDED,), OLD_MUTABLE + (ADDED,))


def downgrade() -> None:
    bind = op.get_bind()
    notes = bind.execute(sa.text("SELECT count(*) FROM deal_note")).scalar_one()
    sealed = bind.execute(
        sa.text(f"SELECT count(*) FROM deal_record_entry WHERE kind = '{ADDED}'")
    ).scalar_one()
    if notes or sealed:
        raise RuntimeError(
            f"{notes} deal notes and {sealed} sealed note entries exist. They are "
            "what both sides can prove was said, and the record's entries cannot "
            "be removed at all; settle them deliberately, as the owner, if that is "
            "really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type = '{ADDED}'")
    op.execute(
        "UPDATE notification_preference"
        f" SET muted_types = array_remove(muted_types, '{ADDED}')"
        f" WHERE '{ADDED}' = ANY (muted_types)"
    )
    _swap_lists(OLD_KINDS, OLD_TYPES, OLD_MUTABLE)
    op.execute("DROP TRIGGER deal_note_no_truncate ON deal_note")
    op.execute("DROP TRIGGER deal_note_no_update_or_delete ON deal_note")
    op.drop_index("ix_deal_note_deal_memo_id_created_at", table_name="deal_note")
    op.drop_table("deal_note")

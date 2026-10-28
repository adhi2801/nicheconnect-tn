"""deal feedback (item 77, D-136)

Approved by Adhi on 26 October 2026 (D-136: fixed questions, a 14-day
window, neither side's answer seen until both answered or it closed). This
migration:

- creates `deal_feedback`, new and empty, so its checks are made whole.
  ON DELETE RESTRICT on the memo: what each side said must never vanish as a
  side effect. Its unique `(deal_memo_id, author_side)` is the foreign key's
  index;
- seals it as deal notes are sealed (D-128): triggers refuse UPDATE, DELETE
  and TRUNCATE through `append_only_refuse_change()`, and the app's own
  role loses those rights (D-100);
- widens the deal record's kinds with `feedback_given`, and the notification
  types and the types a person may mute with `feedback_received`, each check
  swapped NOT VALID and validated after the transaction.

Data impact: none on existing rows.

Downgrade: refuses while any feedback or feedback record entry exists;
otherwise it reverses each step.

Revision ID: a2a642dc46be
Revises: 3e711c2efcc6
Create Date: 2026-10-26 19:16:16.047132

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2a642dc46be"
down_revision: Union[str, None] = "3e711c2efcc6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_WRITER = "app_writer"
KIND = "feedback_given"
NOTICE = "feedback_received"

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
    "note_added",
    "product_shipped",
    "product_received",
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
    "note_added",
    "campaign_alert",
    "product_shipped",
    "product_received",
    "connection_expired",
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
    "connection_expired",
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
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('deal_feedback',
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('deal_memo_id', sa.UUID(), nullable=False),
    sa.Column('author_side', sa.String(length=10), nullable=False),
    sa.Column('brief', sa.SmallInteger(), nullable=False),
    sa.Column('reliability', sa.SmallInteger(), nullable=False),
    sa.Column('easy', sa.SmallInteger(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('window_ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("author_side IN ('brand', 'creator')", name=op.f('ck_deal_feedback_author_side_allowed')),
    sa.CheckConstraint('brief BETWEEN 1 AND 5', name=op.f('ck_deal_feedback_brief_in_range')),
    sa.CheckConstraint('easy BETWEEN 1 AND 5', name=op.f('ck_deal_feedback_easy_in_range')),
    sa.CheckConstraint('note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 500', name=op.f('ck_deal_feedback_note_length')),
    sa.CheckConstraint('reliability BETWEEN 1 AND 5', name=op.f('ck_deal_feedback_reliability_in_range')),
    sa.CheckConstraint('window_ends_at > created_at', name=op.f('ck_deal_feedback_window_after_written')),
    sa.ForeignKeyConstraint(['deal_memo_id'], ['deal_memo.id'], name=op.f('fk_deal_feedback_deal_memo_id_deal_memo'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deal_feedback')),
    sa.UniqueConstraint('deal_memo_id', 'author_side', name='uq_deal_feedback_side')
    )
    # ### end Alembic commands ###
    op.execute(
        "CREATE TRIGGER deal_feedback_no_update_or_delete "
        "BEFORE UPDATE OR DELETE ON deal_feedback "
        "FOR EACH ROW EXECUTE FUNCTION append_only_refuse_change()"
    )
    op.execute(
        "CREATE TRIGGER deal_feedback_no_truncate "
        "BEFORE TRUNCATE ON deal_feedback "
        "FOR EACH STATEMENT EXECUTE FUNCTION append_only_refuse_change()"
    )
    # The default privileges gave app_writer every row right; feedback is
    # only ever read and added (D-100).
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON deal_feedback FROM {APP_WRITER}")
    _swap_lists(OLD_KINDS + (KIND,), OLD_TYPES + (NOTICE,), OLD_MUTABLE + (NOTICE,))


def downgrade() -> None:
    bind = op.get_bind()
    given = bind.execute(sa.text("SELECT count(*) FROM deal_feedback")).scalar_one()
    sealed = bind.execute(
        sa.text(f"SELECT count(*) FROM deal_record_entry WHERE kind = '{KIND}'")
    ).scalar_one()
    if given or sealed:
        raise RuntimeError(
            f"{given} deal feedback answers and {sealed} sealed feedback entries "
            "exist. They are what each side said about a finished deal, and the "
            "record's entries cannot be removed at all; settle them deliberately, as "
            "the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type = '{NOTICE}'")
    op.execute(
        "UPDATE notification_preference"
        f" SET muted_types = array_remove(muted_types, '{NOTICE}')"
        f" WHERE '{NOTICE}' = ANY (muted_types)"
    )
    _swap_lists(OLD_KINDS, OLD_TYPES, OLD_MUTABLE)
    op.execute("DROP TRIGGER deal_feedback_no_truncate ON deal_feedback")
    op.execute("DROP TRIGGER deal_feedback_no_update_or_delete ON deal_feedback")
    op.drop_table("deal_feedback")

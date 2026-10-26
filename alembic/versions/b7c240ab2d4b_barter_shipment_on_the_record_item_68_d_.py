"""barter shipment on the record (item 68, D-131)

Approved by Adhi on 26 October 2026 (D-131: the brand records the courier
and tracking number of a barter deal's goods, only the creator says they
arrived, both sealed; no address held). This migration:

- creates `barter_shipment`, new and empty, so its checks are made whole.
  ON DELETE RESTRICT on the memo: evidence of a deal must never vanish as
  a side effect. Its unique `deal_memo_id` is the foreign key's index;
- widens the deal record's kinds with `product_shipped` and
  `product_received`, and the notification types and the types a person
  may mute with the same two, each check swapped NOT VALID and validated
  after the transaction.

Data impact: none on existing rows.

Downgrade: refuses while any shipment or shipment record entry exists,
since dropping either would destroy what both sides can prove about the
goods, and the record's entries cannot be removed at all; otherwise it
reverses each step.

Revision ID: b7c240ab2d4b
Revises: d78ed34127dd
Create Date: 2026-10-26 15:11:49.419783

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c240ab2d4b"
down_revision: Union[str, None] = "d78ed34127dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADDED = ("product_shipped", "product_received")

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
    op.create_table('barter_shipment',
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('deal_memo_id', sa.UUID(), nullable=False),
    sa.Column('carrier', sa.String(length=20), nullable=False),
    sa.Column('tracking_number', sa.String(length=20), nullable=False),
    sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("carrier <> 'india_post' OR tracking_number ~ '^[A-Z]{2}[0-9]{9}IN$'", name=op.f('ck_barter_shipment_india_post_number_shape')),
    sa.CheckConstraint("carrier IN ('india_post', 'delhivery', 'blue_dart', 'dtdc', 'ecom_express', 'xpressbees', 'shadowfax', 'ekart', 'other')", name=op.f('ck_barter_shipment_carrier_allowed')),
    sa.CheckConstraint("tracking_number ~ '^[A-Z0-9]{8,20}$'", name=op.f('ck_barter_shipment_tracking_number_shape')),
    sa.CheckConstraint('received_at IS NULL OR received_at >= shipped_at', name=op.f('ck_barter_shipment_received_after_shipped')),
    sa.ForeignKeyConstraint(['deal_memo_id'], ['deal_memo.id'], name=op.f('fk_barter_shipment_deal_memo_id_deal_memo'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_barter_shipment')),
    sa.UniqueConstraint('deal_memo_id', name=op.f('uq_barter_shipment_deal_memo_id'))
    )
    # ### end Alembic commands ###
    _swap_lists(OLD_KINDS + ADDED, OLD_TYPES + ADDED, OLD_MUTABLE + ADDED)


def downgrade() -> None:
    bind = op.get_bind()
    shipments = bind.execute(sa.text("SELECT count(*) FROM barter_shipment")).scalar_one()
    sealed = bind.execute(
        sa.text(f"SELECT count(*) FROM deal_record_entry WHERE kind IN {ADDED}")
    ).scalar_one()
    if shipments or sealed:
        raise RuntimeError(
            f"{shipments} barter shipments and {sealed} sealed shipment entries exist. "
            "They are what both sides can prove about the goods, and the record's "
            "entries cannot be removed at all; settle them deliberately, as the "
            "owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED}")
    for added in ADDED:
        op.execute(
            "UPDATE notification_preference"
            f" SET muted_types = array_remove(muted_types, '{added}')"
            f" WHERE '{added}' = ANY (muted_types)"
        )
    _swap_lists(OLD_KINDS, OLD_TYPES, OLD_MUTABLE)
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('barter_shipment')
    # ### end Alembic commands ###

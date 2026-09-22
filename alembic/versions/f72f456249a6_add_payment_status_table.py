"""add payment status table

Revision ID: f72f456249a6
Revises: 7c1f2a9be4d3
Create Date: 2026-09-20 23:08:15.640770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f72f456249a6'
down_revision: Union[str, None] = '7c1f2a9be4d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The record of a payment a brand says it made and a creator confirms
    # (D-027). We never hold the money; this is the memory of it moving.
    #
    # No status column on purpose: `late` and `unpaid` are read from due_on
    # against today, so no scheduled job is needed and a row can never claim
    # a payment is on time when it is a month overdue. See the model.
    #
    # RESTRICT on the memo, matching deliverable_proof: a record of money
    # must never vanish as a side effect of deleting something else.
    #
    # The partial index answers the one hot question — who has not been paid
    # and how overdue are they — and skips every settled row.
    op.create_table('payment_status',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('deal_memo_id', sa.UUID(), nullable=False),
    sa.Column('amount_paise', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('due_on', sa.Date(), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=True),
    sa.Column('reference', sa.String(length=32), nullable=True),
    sa.Column('marked_paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("currency = 'INR'", name=op.f('ck_payment_status_currency_allowed')),
    sa.CheckConstraint("method IS NULL OR method IN ('upi', 'bank_transfer', 'cash')", name=op.f('ck_payment_status_method_allowed')),
    sa.CheckConstraint('amount_paise > 0', name=op.f('ck_payment_status_amount_positive')),
    sa.CheckConstraint('confirmed_at IS NULL OR confirmed_at >= marked_paid_at', name=op.f('ck_payment_status_confirmed_after_marked_paid')),
    sa.CheckConstraint('confirmed_at IS NULL OR marked_paid_at IS NOT NULL', name=op.f('ck_payment_status_confirmed_needs_marked_paid')),
    sa.CheckConstraint('marked_paid_at IS NULL OR (method IS NOT NULL AND reference IS NOT NULL)', name=op.f('ck_payment_status_paid_needs_method_and_reference')),
    sa.CheckConstraint('reference IS NULL OR char_length(btrim(reference)) > 0', name=op.f('ck_payment_status_reference_not_blank')),
    sa.ForeignKeyConstraint(['deal_memo_id'], ['deal_memo.id'], name=op.f('fk_payment_status_deal_memo_id_deal_memo'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_status')),
    sa.UniqueConstraint('deal_memo_id', name=op.f('uq_payment_status_deal_memo_id'))
    )
    op.create_index('ix_payment_status_outstanding', 'payment_status', ['due_on'], unique=False, postgresql_where=sa.text('marked_paid_at IS NULL'))


def downgrade() -> None:
    # Nothing references this table yet, so it drops cleanly.
    op.drop_index('ix_payment_status_outstanding', table_name='payment_status', postgresql_where=sa.text('marked_paid_at IS NULL'))
    op.drop_table('payment_status')

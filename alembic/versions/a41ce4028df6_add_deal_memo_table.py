"""add deal memo table

Revision ID: a41ce4028df6
Revises: afd94871a10d
Create Date: 2026-09-19 20:02:06.741120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a41ce4028df6'
down_revision: Union[str, None] = 'afd94871a10d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # What the two sides agreed, one per accepted application (D-024 to D-027).
    # RESTRICT: the memo is the record of a deal, so the application behind it
    # cannot be deleted. Agreed windows are stored per memo, so a later policy
    # change never rewrites what these two people agreed.
    op.create_table('deal_memo',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('application_id', sa.UUID(), nullable=False),
    sa.Column('deliverables', sa.Text(), nullable=False),
    sa.Column('fee_amount_paise', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
    sa.Column('cancellation_fee_paise', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('approval_window_days', sa.Integer(), server_default=sa.text('7'), nullable=False),
    sa.Column('payment_due_days', sa.Integer(), server_default=sa.text('7'), nullable=False),
    sa.Column('usage_rights_days', sa.Integer(), nullable=True),
    sa.Column('content_due_on', sa.Date(), nullable=True),
    sa.Column('disclosure_required', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('extra_terms', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('revision_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('work_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancellation_kind', sa.String(length=30), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'cancelled') = (cancellation_kind IS NOT NULL)", name=op.f('ck_deal_memo_cancellation_kind_matches_status')),
    sa.CheckConstraint("cancellation_kind IS NULL OR cancellation_kind IN ('withdrawn_early', 'cancelled_by_brand', 'cancelled_by_creator')", name=op.f('ck_deal_memo_cancellation_kind_allowed')),
    sa.CheckConstraint("currency = 'INR'", name=op.f('ck_deal_memo_currency_allowed')),
    sa.CheckConstraint("status IN ('draft', 'sent', 'change_requested', 'accepted', 'declined', 'cancelled')", name=op.f('ck_deal_memo_status_allowed')),
    sa.CheckConstraint('approval_window_days BETWEEN 1 AND 30', name=op.f('ck_deal_memo_approval_window_range')),
    sa.CheckConstraint('cancellation_fee_paise >= 0', name=op.f('ck_deal_memo_cancellation_fee_not_negative')),
    sa.CheckConstraint('char_length(btrim(deliverables)) > 0 AND char_length(deliverables) <= 2000', name=op.f('ck_deal_memo_deliverables_length')),
    sa.CheckConstraint('extra_terms IS NULL OR char_length(extra_terms) <= 2000', name=op.f('ck_deal_memo_extra_terms_length')),
    sa.CheckConstraint('fee_amount_paise IS NULL OR fee_amount_paise > 0', name=op.f('ck_deal_memo_fee_positive')),
    sa.CheckConstraint('payment_due_days BETWEEN 1 AND 30', name=op.f('ck_deal_memo_payment_due_range')),
    sa.CheckConstraint('revision_count >= 0', name=op.f('ck_deal_memo_revision_count_not_negative')),
    sa.CheckConstraint('usage_rights_days IS NULL OR usage_rights_days BETWEEN 1 AND 3650', name=op.f('ck_deal_memo_usage_rights_range')),
    sa.ForeignKeyConstraint(['application_id'], ['application.id'], name=op.f('fk_deal_memo_application_id_application'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deal_memo')),
    sa.UniqueConstraint('application_id', name=op.f('uq_deal_memo_application_id'))
    )
    op.create_index('ix_deal_memo_status_created_at', 'deal_memo', ['status', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_deal_memo_status_created_at', table_name='deal_memo')
    op.drop_table('deal_memo')

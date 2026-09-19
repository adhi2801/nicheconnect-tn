"""add deliverable proof table

Revision ID: 29632d604015
Revises: 304a0b04912a
Create Date: 2026-09-19 20:19:22.637556

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29632d604015'
down_revision: Union[str, None] = '304a0b04912a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The creator's evidence that the work was done (D-024). The public link is
    # the primary evidence; attachments wait for the storage decision. The
    # partial unique index allows one submission awaiting review per memo.
    op.create_table('deliverable_proof',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('deal_memo_id', sa.UUID(), nullable=False),
    sa.Column('content_url', sa.String(length=500), nullable=False),
    sa.Column('format', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('disclosure_confirmed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'submitted'"), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('auto_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('revision_note', sa.Text(), nullable=True),
    sa.Column('content_removed_on', sa.Date(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'approved') = (approved_at IS NOT NULL)", name=op.f('ck_deliverable_proof_approved_at_matches_status')),
    sa.CheckConstraint("NOT auto_approved OR status = 'approved'", name=op.f('ck_deliverable_proof_auto_approved_is_approved')),
    sa.CheckConstraint("content_url ~ '^https://' AND char_length(content_url) <= 500", name=op.f('ck_deliverable_proof_content_url_https')),
    sa.CheckConstraint("format IN ('post', 'reel', 'story', 'video', 'other')", name=op.f('ck_deliverable_proof_format_allowed')),
    sa.CheckConstraint("status IN ('submitted', 'approved', 'revision_requested')", name=op.f('ck_deliverable_proof_status_allowed')),
    sa.CheckConstraint('note IS NULL OR char_length(note) <= 1000', name=op.f('ck_deliverable_proof_note_length')),
    sa.CheckConstraint('revision_note IS NULL OR char_length(revision_note) <= 1000', name=op.f('ck_deliverable_proof_revision_note_length')),
    sa.ForeignKeyConstraint(['deal_memo_id'], ['deal_memo.id'], name=op.f('fk_deliverable_proof_deal_memo_id_deal_memo'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deliverable_proof'))
    )
    op.create_index('ix_deliverable_proof_memo_created_at', 'deliverable_proof', ['deal_memo_id', 'created_at'], unique=False)
    op.create_index('uq_deliverable_proof_open', 'deliverable_proof', ['deal_memo_id'], unique=True, postgresql_where=sa.text("status = 'submitted'"))


def downgrade() -> None:
    op.drop_index('uq_deliverable_proof_open', table_name='deliverable_proof', postgresql_where=sa.text("status = 'submitted'"))
    op.drop_index('ix_deliverable_proof_memo_created_at', table_name='deliverable_proof')
    op.drop_table('deliverable_proof')

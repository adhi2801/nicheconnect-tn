"""add application table

Revision ID: ee268d5e08eb
Revises: b9f74ec5b426
Create Date: 2026-09-18 19:22:53.739455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee268d5e08eb'
down_revision: Union[str, None] = 'b9f74ec5b426'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A creator's answer to a campaign (D-016). One per creator per campaign;
    # RESTRICT on both links, because an application is a record of what
    # happened. All check constraints were read against the model.
    op.create_table('application',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=False),
    sa.Column('creator_id', sa.UUID(), nullable=False),
    sa.Column('pitch', sa.Text(), nullable=False),
    sa.Column('quoted_amount_paise', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'submitted'"), nullable=False),
    sa.Column('rejection_reason', sa.String(length=30), nullable=True),
    sa.Column('rejection_note', sa.Text(), nullable=True),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'rejected') = (rejection_reason IS NOT NULL)", name=op.f('ck_application_rejection_reason_matches_status')),
    sa.CheckConstraint("rejection_reason IS NULL OR rejection_reason IN ('budget_mismatch', 'audience_mismatch', 'timing', 'chose_another_creator', 'incomplete_profile', 'other')", name=op.f('ck_application_rejection_reason_allowed')),
    sa.CheckConstraint("status IN ('submitted', 'shortlisted', 'accepted', 'rejected', 'withdrawn')", name=op.f('ck_application_status_allowed')),
    sa.CheckConstraint('char_length(btrim(pitch)) BETWEEN 20 AND 1000', name=op.f('ck_application_pitch_length')),
    sa.CheckConstraint('quoted_amount_paise IS NULL OR quoted_amount_paise > 0', name=op.f('ck_application_quoted_amount_positive')),
    sa.CheckConstraint('rejection_note IS NULL OR char_length(rejection_note) <= 500', name=op.f('ck_application_rejection_note_length')),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], name=op.f('fk_application_campaign_id_campaign'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['creator_id'], ['creator.id'], name=op.f('fk_application_creator_id_creator'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_application')),
    sa.UniqueConstraint('campaign_id', 'creator_id', name='uq_application_campaign_creator')
    )
    op.create_index('ix_application_campaign_created_at', 'application', ['campaign_id', 'created_at'], unique=False)
    op.create_index('ix_application_creator_created_at', 'application', ['creator_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_application_creator_created_at', table_name='application')
    op.drop_index('ix_application_campaign_created_at', table_name='application')
    op.drop_table('application')

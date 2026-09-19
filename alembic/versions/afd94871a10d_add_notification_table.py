"""add notification table

Revision ID: afd94871a10d
Revises: 66527a152dfc
Create Date: 2026-09-19 19:49:31.717577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'afd94871a10d'
down_revision: Union[str, None] = '66527a152dfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # What happened, told to one account (D-023). Text is not stored: only the
    # type and the values needed to render it, so the app can show Tamil or
    # English. CASCADE everywhere: a notification means nothing without its
    # account, campaign or application.
    op.create_table('notification',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('notification_type', sa.String(length=40), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('application_id', sa.UUID(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("jsonb_typeof(details) = 'object' AND char_length(details::text) <= 2000", name=op.f('ck_notification_details_small_object')),
    sa.CheckConstraint("notification_type IN ('application_received', 'application_withdrawn', 'application_shortlisted', 'application_accepted', 'application_rejected')", name=op.f('ck_notification_type_allowed')),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('fk_notification_account_id_account'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['application_id'], ['application.id'], name=op.f('fk_notification_application_id_application'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], name=op.f('fk_notification_campaign_id_campaign'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification'))
    )
    op.create_index('ix_notification_account_created_at', 'notification', ['account_id', 'created_at'], unique=False)
    op.create_index('ix_notification_unread', 'notification', ['account_id'], unique=False, postgresql_where=sa.text('read_at IS NULL'))


def downgrade() -> None:
    op.drop_index('ix_notification_unread', table_name='notification', postgresql_where=sa.text('read_at IS NULL'))
    op.drop_index('ix_notification_account_created_at', table_name='notification')
    op.drop_table('notification')

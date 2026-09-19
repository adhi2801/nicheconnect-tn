"""drop unused gin indexes on campaign

Revision ID: 66527a152dfc
Revises: ee268d5e08eb
Create Date: 2026-09-19 19:00:08.482343

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66527a152dfc'
down_revision: Union[str, None] = 'ee268d5e08eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D-017: measured at 20,000 campaigns, the planner never chose these.
    # Discovery uses ix_campaign_open_created_at and filters (0.5 ms).
    op.drop_index('ix_campaign_cities', table_name='campaign', postgresql_using='gin')
    op.drop_index('ix_campaign_niches', table_name='campaign', postgresql_using='gin')


def downgrade() -> None:
    op.create_index('ix_campaign_niches', 'campaign', ['niches'], unique=False, postgresql_using='gin')
    op.create_index('ix_campaign_cities', 'campaign', ['cities'], unique=False, postgresql_using='gin')

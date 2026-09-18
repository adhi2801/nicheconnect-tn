"""add campaign table

Revision ID: b9f74ec5b426
Revises: 25932ee8f40b
Create Date: 2026-09-18 19:06:18.348280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b9f74ec5b426'
down_revision: Union[str, None] = '25932ee8f40b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # What a brand asks for (D-016). Budgets are whole paise (D-015).
    # Autogenerate captured all 12 check constraints because the table is new;
    # they were read and match the model.
    op.create_table('campaign',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('brand_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('campaign_type', sa.String(length=20), nullable=False),
    sa.Column('budget_min_paise', sa.BigInteger(), nullable=True),
    sa.Column('budget_max_paise', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
    sa.Column('cities', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('niches', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('deliverables', sa.Text(), nullable=False),
    sa.Column('applications_close_on', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("campaign_type NOT IN ('paid', 'barter', 'commission', 'local_business') OR (campaign_type = 'barter' AND budget_min_paise IS NULL) OR (campaign_type IN ('paid', 'local_business') AND budget_min_paise IS NOT NULL) OR campaign_type = 'commission'", name=op.f('ck_campaign_budget_matches_type')),
    sa.CheckConstraint("campaign_type IN ('paid', 'barter', 'commission', 'local_business')", name=op.f('ck_campaign_type_allowed')),
    sa.CheckConstraint("currency = 'INR'", name=op.f('ck_campaign_currency_allowed')),
    sa.CheckConstraint("niches <@ ARRAY['food', 'fashion', 'beauty', 'tech', 'travel', 'fitness', 'education', 'entertainment', 'finance', 'lifestyle']::text[]", name=op.f('ck_campaign_niches_allowed')),
    sa.CheckConstraint("status IN ('draft', 'open', 'closed', 'cancelled')", name=op.f('ck_campaign_status_allowed')),
    sa.CheckConstraint('(budget_min_paise IS NULL AND budget_max_paise IS NULL) OR (budget_min_paise IS NOT NULL AND budget_max_paise IS NOT NULL AND budget_min_paise > 0 AND budget_max_paise >= budget_min_paise)', name=op.f('ck_campaign_budget_range')),
    sa.CheckConstraint('cardinality(cities) BETWEEN 1 AND 10', name=op.f('ck_campaign_cities_count')),
    sa.CheckConstraint('cardinality(niches) BETWEEN 1 AND 5', name=op.f('ck_campaign_niches_count')),
    sa.CheckConstraint('char_length(btrim(deliverables)) > 0', name=op.f('ck_campaign_deliverables_not_blank')),
    sa.CheckConstraint('char_length(btrim(title)) > 0', name=op.f('ck_campaign_title_not_blank')),
    sa.CheckConstraint('char_length(deliverables) <= 2000', name=op.f('ck_campaign_deliverables_length')),
    sa.CheckConstraint('char_length(description) <= 4000', name=op.f('ck_campaign_description_length')),
    sa.ForeignKeyConstraint(['brand_id'], ['brand.id'], name=op.f('fk_campaign_brand_id_brand'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_campaign'))
    )
    op.create_index(op.f('ix_campaign_brand_id'), 'campaign', ['brand_id'], unique=False)
    op.create_index('ix_campaign_cities', 'campaign', ['cities'], unique=False, postgresql_using='gin')
    op.create_index('ix_campaign_niches', 'campaign', ['niches'], unique=False, postgresql_using='gin')
    op.create_index('ix_campaign_open_created_at', 'campaign', ['created_at'], unique=False, postgresql_where=sa.text("status = 'open'"))


def downgrade() -> None:
    op.drop_index('ix_campaign_open_created_at', table_name='campaign', postgresql_where=sa.text("status = 'open'"))
    op.drop_index('ix_campaign_niches', table_name='campaign', postgresql_using='gin')
    op.drop_index('ix_campaign_cities', table_name='campaign', postgresql_using='gin')
    op.drop_index(op.f('ix_campaign_brand_id'), table_name='campaign')
    op.drop_table('campaign')

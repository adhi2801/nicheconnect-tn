"""add creator table

Revision ID: 15e894f4fe7e
Revises: b0020a4adcd2
Create Date: 2026-09-17 20:11:54.606279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '15e894f4fe7e'
down_revision: Union[str, None] = 'b0020a4adcd2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Creator public profile. No contact details here: this table will feed
    # matching embeddings. gen_random_uuid() comes from pgcrypto (b0020a4adcd2).
    # No foreign keys yet, so no ON DELETE choices to make.
    op.create_table('creator',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('handle', sa.String(length=30), nullable=False),
    sa.Column('city', sa.String(length=60), nullable=False),
    sa.Column('niches', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('languages', postgresql.ARRAY(sa.Text()), nullable=False),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("handle ~ '^[a-z0-9._]{3,30}$'", name=op.f('ck_creator_handle_format')),
    sa.CheckConstraint("languages <@ ARRAY['en']::text[]", name=op.f('ck_creator_languages_allowed')),
    sa.CheckConstraint("niches <@ ARRAY['food', 'fashion', 'beauty', 'tech', 'travel', 'fitness', 'education', 'entertainment', 'finance', 'lifestyle']::text[]", name=op.f('ck_creator_niches_allowed')),
    sa.CheckConstraint('cardinality(languages) >= 1', name=op.f('ck_creator_languages_count')),
    sa.CheckConstraint('cardinality(niches) BETWEEN 1 AND 5', name=op.f('ck_creator_niches_count')),
    sa.CheckConstraint('char_length(bio) <= 500', name=op.f('ck_creator_bio_length')),
    sa.CheckConstraint('char_length(btrim(city)) > 0', name=op.f('ck_creator_city_not_blank')),
    sa.CheckConstraint('char_length(btrim(display_name)) > 0', name=op.f('ck_creator_display_name_not_blank')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_creator')),
    sa.UniqueConstraint('handle', name=op.f('uq_creator_handle'))
    )
    # GIN index so "creators in niche X" queries stay fast.
    op.create_index('ix_creator_niches', 'creator', ['niches'], unique=False, postgresql_using='gin')
    # Autogenerate also proposed renaming brand_email_key -> uq_brand_email
    # (new naming convention). Left out on purpose: one change per migration.
    # It belongs to the separate brand email fix migration.


def downgrade() -> None:
    op.drop_index('ix_creator_niches', table_name='creator', postgresql_using='gin')
    op.drop_table('creator')

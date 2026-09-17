"""fix brand email and name constraints

Revision ID: c78f2f83c465
Revises: 15e894f4fe7e
Create Date: 2026-09-17 20:18:26.071119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c78f2f83c465'
down_revision: Union[str, None] = '15e894f4fe7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written by hand: autogenerate detected none of these changes.

# Databases built before the naming convention (D-005) have Postgres default
# names; databases built after it already have the new names. Rename only
# where the old name still exists, so every database ends up the same.
RENAME_LEGACY_CONSTRAINTS = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'brand_pkey' AND conrelid = 'brand'::regclass) THEN
        ALTER TABLE brand RENAME CONSTRAINT brand_pkey TO pk_brand;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'brand_email_key' AND conrelid = 'brand'::regclass) THEN
        ALTER TABLE brand RENAME CONSTRAINT brand_email_key TO uq_brand_email;
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(RENAME_LEGACY_CONSTRAINTS)

    # Lowercase existing emails before the lowercase rule is added. If two
    # emails differ only in capitals, this fails on uq_brand_email and the
    # migration stops, rather than silently merging accounts.
    op.execute("UPDATE brand SET email = lower(email) WHERE email <> lower(email)")

    # Fails if any existing value is longer than the new limit (safe failure).
    op.alter_column('brand', 'name', type_=sa.String(length=150),
                    existing_type=sa.String(), existing_nullable=False)
    op.alter_column('brand', 'email', type_=sa.String(length=320),
                    existing_type=sa.String(), existing_nullable=False)

    op.create_check_constraint(op.f('ck_brand_email_lowercase'), 'brand',
                               'email = lower(email)')
    op.create_check_constraint(op.f('ck_brand_name_not_blank'), 'brand',
                               'char_length(btrim(name)) > 0')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_brand_name_not_blank'), 'brand', type_='check')
    op.drop_constraint(op.f('ck_brand_email_lowercase'), 'brand', type_='check')
    op.alter_column('brand', 'email', type_=sa.String(),
                    existing_type=sa.String(length=320), existing_nullable=False)
    op.alter_column('brand', 'name', type_=sa.String(),
                    existing_type=sa.String(length=150), existing_nullable=False)
    # Not reversed on purpose: the constraint renames (earlier migrations now
    # create pk_brand / uq_brand_email on fresh databases anyway) and the
    # lowercased emails (the original capitals are not kept).

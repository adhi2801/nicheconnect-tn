"""add account table and link brand and creator

Revision ID: 0d4be8a8813a
Revises: c78f2f83c465
Create Date: 2026-09-17 20:26:23.365577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d4be8a8813a'
down_revision: Union[str, None] = 'c78f2f83c465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# account_id is required, and existing profiles have no account to point to.
# Only test data exists (D-011), so stop with a clear message instead of guessing.
REFUSE_UNLINKED_PROFILES = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM brand) OR EXISTS (SELECT 1 FROM creator) THEN
        RAISE EXCEPTION 'brand/creator rows exist without an account. '
            'They are test data: delete them, then rerun alembic upgrade head.';
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(REFUSE_UNLINKED_PROFILES)

    # Login identity (D-011). Holds the phone number, so never embedded.
    op.create_table('account',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('phone', sa.String(length=16), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("phone ~ '^\\+91[6-9][0-9]{9}$'", name=op.f('ck_account_phone_format')),
    sa.CheckConstraint("role IN ('brand', 'creator')", name=op.f('ck_account_role_allowed')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_account')),
    sa.UniqueConstraint('phone', name=op.f('uq_account_phone'))
    )

    # One profile per account. The unique constraint's index also serves as
    # the FK index. ON DELETE RESTRICT: an account with a profile can't be
    # deleted until the DPDP deletion policy is decided.
    op.add_column('brand', sa.Column('account_id', sa.UUID(), nullable=False))
    op.create_unique_constraint(op.f('uq_brand_account_id'), 'brand', ['account_id'])
    op.create_foreign_key(op.f('fk_brand_account_id_account'), 'brand', 'account', ['account_id'], ['id'], ondelete='RESTRICT')

    op.add_column('creator', sa.Column('account_id', sa.UUID(), nullable=False))
    op.create_unique_constraint(op.f('uq_creator_account_id'), 'creator', ['account_id'])
    op.create_foreign_key(op.f('fk_creator_account_id_account'), 'creator', 'account', ['account_id'], ['id'], ondelete='RESTRICT')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_creator_account_id_account'), 'creator', type_='foreignkey')
    op.drop_constraint(op.f('uq_creator_account_id'), 'creator', type_='unique')
    op.drop_column('creator', 'account_id')
    op.drop_constraint(op.f('fk_brand_account_id_account'), 'brand', type_='foreignkey')
    op.drop_constraint(op.f('uq_brand_account_id'), 'brand', type_='unique')
    op.drop_column('brand', 'account_id')
    op.drop_table('account')

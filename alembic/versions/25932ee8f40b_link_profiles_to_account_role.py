"""link profiles to account role

Revision ID: 25932ee8f40b
Revises: 3d218c522ec6
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25932ee8f40b'
down_revision: Union[str, None] = '3d218c522ec6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# D-014. Autogenerate found the column and key changes but not the CHECK
# constraints; those are written by hand below.
#
# Existing rows: the server default fills account_role correctly, because every
# row in brand belongs to a brand and every row in creator to a creator. If a
# profile pointed at an account of the other role, creating the paired foreign
# key fails and the whole migration rolls back, which is the safe outcome.


def upgrade() -> None:
    # Lets a profile reference (id, role) together.
    op.create_unique_constraint('uq_account_id_role', 'account', ['id', 'role'])

    for table, role in (('brand', 'brand'), ('creator', 'creator')):
        op.add_column(
            table,
            sa.Column(
                'account_role',
                sa.String(length=16),
                server_default=sa.text(f"'{role}'"),
                nullable=False,
            ),
        )
        op.create_check_constraint(
            op.f(f'ck_{table}_account_role_fixed'), table, f"account_role = '{role}'"
        )
        # Replace the single-column key with the pair, so the linked account
        # must have this role, cannot own the other profile too, and cannot
        # change role while the profile exists.
        op.drop_constraint(f'fk_{table}_account_id_account', table, type_='foreignkey')
        op.create_foreign_key(
            op.f(f'fk_{table}_account_id_account'),
            table,
            'account',
            ['account_id', 'account_role'],
            ['id', 'role'],
            ondelete='RESTRICT',
        )


def downgrade() -> None:
    for table in ('creator', 'brand'):
        op.drop_constraint(op.f(f'fk_{table}_account_id_account'), table, type_='foreignkey')
        op.create_foreign_key(
            f'fk_{table}_account_id_account',
            table,
            'account',
            ['account_id'],
            ['id'],
            ondelete='RESTRICT',
        )
        op.drop_constraint(op.f(f'ck_{table}_account_role_fixed'), table, type_='check')
        op.drop_column(table, 'account_role')
    op.drop_constraint('uq_account_id_role', 'account', type_='unique')

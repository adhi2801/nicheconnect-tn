"""add creator passport opt in

Revision ID: 386c81bcb3ff
Revises: 62fca71c7083
Create Date: 2026-09-21 00:04:18.469539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '386c81bcb3ff'
down_revision: Union[str, None] = '62fca71c7083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # When a creator chose to put their profile on the open internet.
    #
    # Nullable, with no default and no backfill, so every existing row means
    # "not published". That is deliberate: publishing somebody cannot be
    # undone once search engines have seen it, while publishing them later
    # once they have said yes costs nothing. Nothing is deployed and there
    # are no real creators yet, so the safe default is free.
    #
    # A timestamp rather than a boolean because it is the consent itself:
    # it records that the creator chose, and when.
    op.add_column('creator', sa.Column('passport_published_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Dropping this un-publishes everybody, which is the safe direction.
    op.drop_column('creator', 'passport_published_at')

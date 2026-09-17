"""add auth session table

Revision ID: 3d218c522ec6
Revises: a3547503e1e9
Create Date: 2026-09-17 20:37:58.127149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d218c522ec6'
down_revision: Union[str, None] = 'a3547503e1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Refresh-token sessions (D-008, D-011). Stores only a SHA-256 of each token.
    # ON DELETE CASCADE: sessions are removed with their account.
    op.create_table('auth_session',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_auth_session_token_hash_format')),
    sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('fk_auth_session_account_id_account'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_session')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_auth_session_token_hash'))
    )
    # account_id: "log out of all devices". family_id: revoke a stolen token's family.
    op.create_index(op.f('ix_auth_session_account_id'), 'auth_session', ['account_id'], unique=False)
    op.create_index(op.f('ix_auth_session_family_id'), 'auth_session', ['family_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_auth_session_family_id'), table_name='auth_session')
    op.drop_index(op.f('ix_auth_session_account_id'), table_name='auth_session')
    op.drop_table('auth_session')

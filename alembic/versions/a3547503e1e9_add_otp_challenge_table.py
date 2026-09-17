"""add otp challenge table

Revision ID: a3547503e1e9
Revises: 0d4be8a8813a
Create Date: 2026-09-17 20:33:29.231522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3547503e1e9'
down_revision: Union[str, None] = '0d4be8a8813a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One-time login codes (D-007, D-011). Stores only an HMAC of the code.
    # Not linked to account on purpose, so registered numbers can't be probed.
    op.create_table('otp_challenge',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('phone', sa.String(length=16), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("code_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_otp_challenge_code_hash_format')),
    sa.CheckConstraint("phone ~ '^\\+91[6-9][0-9]{9}$'", name=op.f('ck_otp_challenge_phone_format')),
    sa.CheckConstraint('attempts BETWEEN 0 AND 5', name=op.f('ck_otp_challenge_attempts_range')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_challenge'))
    )
    # Latest code per phone and per-phone send-limit counts.
    op.create_index('ix_otp_challenge_phone_created_at', 'otp_challenge', ['phone', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
    op.drop_index('ix_otp_challenge_phone_created_at', table_name='otp_challenge')
    op.drop_table('otp_challenge')

"""add dispute and dispute event tables

Revision ID: 62fca71c7083
Revises: c3b81e47af20
Create Date: 2026-09-20 23:45:23.755520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62fca71c7083'
down_revision: Union[str, None] = 'c3b81e47af20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A dispute about a payment, and the dated account each side put on the
    # record (D-028). We hold no money and have no standing to judge, so what
    # is stored is who said what and when, never a finding.
    #
    # No status column on the dispute: `unresolved` is not something anybody
    # does, it is what thirty days of nothing looks like, so it is read from
    # the dates. Same reasoning as payment_status.
    #
    # RESTRICT from the payment record, CASCADE from the dispute to its
    # entries: a dispute must not vanish with something else, but an entry
    # means nothing without the dispute it belongs to.
    op.create_table('dispute',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('payment_status_id', sa.UUID(), nullable=False),
    sa.Column('opened_by', sa.String(length=8), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('response_due_on', sa.Date(), nullable=False),
    sa.Column('outcome', sa.String(length=24), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("opened_by IN ('brand', 'creator')", name=op.f('ck_dispute_opened_by_allowed')),
    sa.CheckConstraint("outcome IS NULL OR outcome IN ('resolved_paid', 'resolved_withdrawn', 'resolved_informally')", name=op.f('ck_dispute_outcome_allowed')),
    sa.CheckConstraint('(outcome IS NULL) = (closed_at IS NULL)', name=op.f('ck_dispute_outcome_matches_closed_at')),
    sa.CheckConstraint('char_length(btrim(reason)) >= 20 AND char_length(reason) <= 2000', name=op.f('ck_dispute_reason_length')),
    sa.ForeignKeyConstraint(['payment_status_id'], ['payment_status.id'], name=op.f('fk_dispute_payment_status_id_payment_status'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dispute')),
    sa.UniqueConstraint('payment_status_id', name=op.f('uq_dispute_payment_status_id'))
    )
    op.create_index('ix_dispute_open', 'dispute', ['created_at'], unique=False, postgresql_where=sa.text('outcome IS NULL'))
    op.create_table('dispute_event',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('dispute_id', sa.UUID(), nullable=False),
    sa.Column('actor_role', sa.String(length=8), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('evidence_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("actor_role IN ('brand', 'creator')", name=op.f('ck_dispute_event_actor_role_allowed')),
    sa.CheckConstraint("evidence_url IS NULL OR evidence_url LIKE 'https://%%'", name=op.f('ck_dispute_event_evidence_url_is_https')),
    sa.CheckConstraint("kind IN ('opened', 'response', 'evidence', 'closed')", name=op.f('ck_dispute_event_kind_allowed')),
    sa.CheckConstraint('note IS NOT NULL OR evidence_url IS NOT NULL', name=op.f('ck_dispute_event_says_something')),
    sa.CheckConstraint('note IS NULL OR (char_length(btrim(note)) > 0 AND char_length(note) <= 2000)', name=op.f('ck_dispute_event_note_length')),
    sa.ForeignKeyConstraint(['dispute_id'], ['dispute.id'], name=op.f('fk_dispute_event_dispute_id_dispute'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dispute_event'))
    )
    op.create_index('ix_dispute_event_dispute_created_at', 'dispute_event', ['dispute_id', 'created_at'], unique=False)


def downgrade() -> None:
    # Entries first: they point at the dispute.
    op.drop_index('ix_dispute_event_dispute_created_at', table_name='dispute_event')
    op.drop_table('dispute_event')
    op.drop_index('ix_dispute_open', table_name='dispute', postgresql_where=sa.text('outcome IS NULL'))
    op.drop_table('dispute')

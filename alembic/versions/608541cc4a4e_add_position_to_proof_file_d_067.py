"""add position to proof_file (D-067)

A proof shows its files in the order the creator chose, the order the deal
record already seals. Until now they were shown in upload order, so the
record and the screen could disagree (approved by Adhi in session,
1 October 2026).

`position` is empty while a file is pending and set, from 0, once a proof
takes it; two files on one proof never share one.

Existing attached files are given their upload order, which is what they
showed until now. database.md section 6 puts backfills in a migration of
their own, batched; this one is not, by the approved plan: proof_file has
never been deployed or merged, so it holds no real data anywhere, and at
most ten rows share a proof.

No lock on a busy table (Squawk, D-050): the checks are added NOT VALID and
validated after the transaction commits, and the unique index is built
CONCURRENTLY, then adopted as the constraint.

Alembic does not compare CHECK constraints, so those are written by hand.

Revision ID: 608541cc4a4e
Revises: f276d2c6ce1e
Create Date: 2026-10-01 14:10:27.925623

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '608541cc4a4e'
down_revision: Union[str, None] = 'f276d2c6ce1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS = {
    "ck_proof_file_position_once_attached": "(status = 'pending') = (position IS NULL)",
    "ck_proof_file_position_in_range": "position IS NULL OR position BETWEEN 0 AND 9",
}
UNIQUE = "uq_proof_file_proof_id"


def upgrade() -> None:
    op.add_column('proof_file', sa.Column('position', sa.SmallInteger(), nullable=True))
    # Upload order, from 0, within each proof: what each proof showed until now.
    op.execute(
        "UPDATE proof_file AS f SET position = ranked.place "
        "FROM ("
        "  SELECT id, row_number() OVER ("
        "    PARTITION BY proof_id ORDER BY created_at, id"
        "  ) - 1 AS place"
        "  FROM proof_file WHERE status <> 'pending'"
        ") AS ranked "
        "WHERE f.id = ranked.id"
    )
    for name, condition in CHECKS.items():
        op.execute(
            f"ALTER TABLE proof_file ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )
    with op.get_context().autocommit_block():
        for name in CHECKS:
            op.execute(f"ALTER TABLE proof_file VALIDATE CONSTRAINT {name}")
        op.execute(
            f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {UNIQUE} "
            "ON proof_file (proof_id, position)"
        )
        op.execute(
            f"ALTER TABLE proof_file ADD CONSTRAINT {UNIQUE} UNIQUE USING INDEX {UNIQUE}"
        )


def downgrade() -> None:
    # Files fall back to upload order; nothing else is lost. Raw SQL, by the
    # exact names: op.drop_constraint would put the naming convention's
    # prefix on them a second time.
    op.execute(f"ALTER TABLE proof_file DROP CONSTRAINT {UNIQUE}")
    for name in CHECKS:
        op.execute(f"ALTER TABLE proof_file DROP CONSTRAINT {name}")
    op.drop_column('proof_file', 'position')

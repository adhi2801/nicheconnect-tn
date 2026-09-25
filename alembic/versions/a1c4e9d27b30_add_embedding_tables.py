"""add creator and campaign embedding tables

Revision ID: a1c4e9d27b30
Revises: 386c81bcb3ff
Create Date: 2026-09-23 18:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'a1c4e9d27b30'
down_revision: Union[str, None] = '386c81bcb3ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIMENSIONS = 1024


def upgrade() -> None:
    # pgvector itself. The image pins 0.8.6, clear of CVE-2026-3172, which
    # affects 0.6.0 to 0.8.1 (D-049). This is the first thing in the project
    # to need the extension at all.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # One vector each, keyed by the row it describes, so there is exactly one
    # current embedding per creator and per campaign. CASCADE because an
    # embedding without its subject is meaningless — this is derived data, and
    # deleting the creator should take it with them rather than block on it.
    #
    # No UUIDv7 default here although D-049 locks it for new tables: neither
    # table generates an id. The primary key is the foreign key.
    for table, parent, column in (
        ("creator_embedding", "creator", "creator_id"),
        ("campaign_embedding", "campaign", "campaign_id"),
    ):
        op.create_table(
            table,
            sa.Column(
                column,
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{parent}.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("embedding", Vector(DIMENSIONS), nullable=False),
            # SHA-256 of the text that was embedded, so a rebuild can skip the
            # rows whose input did not change. Embedding is the slow part.
            sa.Column("source_hash", sa.String(64), nullable=False),
            sa.Column("model", sa.String(128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    # Deliberately NO vector index (HNSW or IVFFlat).
    #
    # Matching filters structurally first — city, niche, budget, status — and
    # ranks by similarity inside that result. At pilot scale that leaves tens
    # of rows, and an exact scan over tens of vectors is faster than an index
    # lookup and always exactly right, where an approximate index is not.
    #
    # Building one now would also be the mistake CLAUDE.md section 3 warns
    # about: HNSW costs build time and memory on every write for a recall
    # problem we do not have. The trigger to add it is a measured p95 over
    # the 300 ms read budget in docs/PERFORMANCE.md, not a hunch.


def downgrade() -> None:
    op.drop_table("campaign_embedding")
    op.drop_table("creator_embedding")
    # The extension is deliberately left in place. Dropping it would break
    # anything else that starts using vector columns, and an unused extension
    # costs nothing. Drop it by hand if this is truly being reversed:
    #   DROP EXTENSION vector;

"""Where a creator's and a campaign's embeddings are stored (D-052).

One table each, rather than a column on `creator` and `campaign`, because an
embedding is derived data with its own lifecycle:

- It is regenerated whenever the text it was built from changes, or the model
  changes, and it is throwaway — losing every row costs a rebuild, not data.
- A 1024-dimension vector is about 4 KB. On the row itself, every `SELECT
  creator` in the product would carry it for nothing.
- Two models can coexist while one replaces the other, because `model` is on
  the row.

`source_hash` is the hash of the text `embedding_input.py` produced. A rebuild
compares it and re-embeds only the rows whose input actually changed, which
matters because embedding is the slow part.

**Nothing private is in here.** What went into the vector is decided by
`app/modules/matching/embedding_input.py`, which refuses to list a field whose
name looks private and fails closed when a new column appears. Constraint 2 is
enforced there; this module only stores the result.

No vector index yet, deliberately. See the migration.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Qwen3-Embedding-0.6B's native width (D-052). The model supports Matryoshka
# truncation from 32 upwards, so this can be narrowed later without retraining
# — but not without a migration, so it is fixed here rather than configurable.
EMBEDDING_DIMENSIONS = 1024

# Which model produced a row. Long enough for a Hugging Face path.
MODEL_NAME_MAX_LENGTH = 128

# Hex SHA-256 of the embedded text.
SOURCE_HASH_LENGTH = 64


class CreatorEmbedding(Base):
    """One vector per creator, rebuilt when their profile text changes."""

    __tablename__ = "creator_embedding"

    # The creator's id is the primary key: exactly one current embedding each.
    # A second model in flight gets its own row only once `model` joins the
    # key, which is a migration we do when we actually need it.
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(SOURCE_HASH_LENGTH), nullable=False)
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=text("now()"),
    )


class CampaignEmbedding(Base):
    """One vector per campaign, rebuilt when its brief changes."""

    __tablename__ = "campaign_embedding"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(SOURCE_HASH_LENGTH), nullable=False)
    model: Mapped[str] = mapped_column(String(MODEL_NAME_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=text("now()"),
    )

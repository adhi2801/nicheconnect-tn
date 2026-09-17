import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Creator profiles will feed matching embeddings, so this table must never
# hold contact details (phone, email, bank, UPI). The phone lives in account (D-011).

CREATOR_NICHES: tuple[str, ...] = (
    "food",
    "fashion",
    "beauty",
    "tech",
    "travel",
    "fitness",
    "education",
    "entertainment",
    "finance",
    "lifestyle",
)
CREATOR_LANGUAGES: tuple[str, ...] = ("en",)
MAX_NICHES = 5
HANDLE_PATTERN = r"^[a-z0-9._]{3,30}$"
BIO_MAX_LENGTH = 500


def _text_array_literal(values: tuple[str, ...]) -> str:
    """Build a SQL text[] literal from fixed, code-defined values (never user input)."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"ARRAY[{quoted}]::text[]"


class Creator(Base):
    __tablename__ = "creator"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(display_name)) > 0", name="display_name_not_blank"
        ),
        CheckConstraint(f"handle ~ '{HANDLE_PATTERN}'", name="handle_format"),
        CheckConstraint("char_length(btrim(city)) > 0", name="city_not_blank"),
        CheckConstraint(
            f"cardinality(niches) BETWEEN 1 AND {MAX_NICHES}", name="niches_count"
        ),
        CheckConstraint(
            f"niches <@ {_text_array_literal(CREATOR_NICHES)}", name="niches_allowed"
        ),
        CheckConstraint("cardinality(languages) >= 1", name="languages_count"),
        CheckConstraint(
            f"languages <@ {_text_array_literal(CREATOR_LANGUAGES)}",
            name="languages_allowed",
        ),
        CheckConstraint(
            f"char_length(bio) <= {BIO_MAX_LENGTH}", name="bio_length"
        ),
        Index("ix_creator_niches", "niches", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: an account can't be deleted while its profile exists (D-011).
        ForeignKey("account.id", ondelete="RESTRICT"),
        nullable=False,
        # Unique: one profile per account. The unique index also serves as the FK index.
        unique=True,
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    handle: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    city: Mapped[str] = mapped_column(String(60), nullable=False)
    niches: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # Nullable on purpose: a bio is optional on a creator profile.
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

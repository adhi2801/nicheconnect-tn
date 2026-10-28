"""What a proof screenshot said, read by Claude and checked by us (D-070).

One row per cleaned proof file that was read. The database refuses every
state that would make a reading claim more than it holds: numbers on a
reading that read none, a failure without its reason, a negative count.

**The creator's own claims are copied in** (`stated_followers`,
`stated_average_views`) at the moment of reading. A creator who edits their
profile later cannot change what a past result was compared with, in either
direction.

**Never "verified".** Nothing here says a screenshot is true; layer 2's
checks say whether it agrees with facts we hold, and that is all.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

READING_STATUSES: tuple[str, ...] = ("read", "no_numbers", "failed")
READING_FAILURES: tuple[str, ...] = (
    "refusal",
    "max_tokens",
    "api_error",
    "invalid_answer",
    "image_too_large",
)
READING_PLATFORMS: tuple[str, ...] = ("instagram", "youtube", "other")
READING_METRICS: tuple[str, ...] = (
    "views",
    "reach",
    "impressions",
    "likes",
    "comments",
    "saves",
    "shares",
)
CREATOR_NOTE_MAX_LENGTH = 500


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_NO_NUMBERS = " AND ".join(f"{metric} IS NULL" for metric in READING_METRICS)
_SOME_NUMBER = " OR ".join(f"{metric} IS NOT NULL" for metric in READING_METRICS)


class ProofFileReading(Base):
    __tablename__ = "proof_file_reading"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_sql_list(READING_STATUSES)})", name="status_allowed"
        ),
        CheckConstraint(
            f"failure IS NULL OR failure IN ({_sql_list(READING_FAILURES)})",
            name="failure_allowed",
        ),
        # Failed exactly when there is a reason.
        CheckConstraint(
            "(status = 'failed') = (failure IS NOT NULL)", name="failed_has_reason"
        ),
        # Numbers only on a reading that read some, and then at least one.
        CheckConstraint(
            f"(status = 'read' AND ({_SOME_NUMBER})) OR (status <> 'read' AND {_NO_NUMBERS})",
            name="numbers_only_when_read",
        ),
        CheckConstraint(
            " AND ".join(f"({m} IS NULL OR {m} >= 0)" for m in READING_METRICS),
            name="numbers_not_negative",
        ),
        CheckConstraint(
            f"platform IS NULL OR platform IN ({_sql_list(READING_PLATFORMS)})",
            name="platform_allowed",
        ),
        CheckConstraint(
            f"abbreviated <@ ARRAY[{_sql_list(READING_METRICS)}]::varchar[]",
            name="abbreviated_allowed",
        ),
        CheckConstraint(
            "stated_followers IS NULL OR stated_followers >= 0",
            name="stated_followers_valid",
        ),
        CheckConstraint(
            "stated_average_views IS NULL OR stated_average_views >= 0",
            name="stated_average_views_valid",
        ),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="tokens_not_negative"
        ),
        # A creator's mark that the reading is wrong always says when.
        CheckConstraint(
            "creator_note IS NULL OR creator_marked_at IS NOT NULL",
            name="note_has_mark",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # One reading per file. RESTRICT, like the file itself: evidence stays.
    # The unique constraint's index also serves the foreign key.
    proof_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proof_file.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Which model and which instructions produced it, so a reading can always
    # be traced, and re-read if either changes.
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    handle: Mapped[str | None] = mapped_column(String(30), nullable=True)
    post_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    likes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comments: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    saves: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    shares: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Shown abbreviated on screen (12.5K), so not exact.
    abbreviated: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, server_default=text("'{}'")
    )
    # Layer 2, each null when there was nothing to check against.
    handle_matches: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    date_within_deal: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    numbers_consistent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    stated_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stated_average_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The creator says the reading is wrong. Kept next to it, never instead.
    creator_marked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creator_note: Mapped[str | None] = mapped_column(
        String(CREATOR_NOTE_MAX_LENGTH), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    # What reading it cost, for the daily spend ceiling and the bill.
    input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

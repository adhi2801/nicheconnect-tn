"""The quarterly city rate report, one row a quarter (item 84, D-200).

A snapshot, because the facts behind it do not keep their past: rate cards
are edited in place, so last quarter's asking prices cannot be worked out
again later, and a figure a journalist quoted must never change under them.
So, unlike every other figure in `insights` (worked out on read, backend.md
section 2), this one is stored once, when the quarter has closed.

- `body` holds aggregate numbers only: no id, handle or name of anyone
  (`rate_report_rules`, `rate_report_schemas.RateReportBody`).
- `body_sha256` is the SHA-256 of the body's canonical JSON (keys sorted, no
  spaces, UTF-8), shown with the report so any copy can be checked.
- It is built unpublished, read by an admin, then published. **Once
  published, the database refuses any change to what it says** (a trigger,
  the pattern of the deal record's seal, D-057), and refuses deleting it, so
  a cited figure can be withdrawn with its reason, never quietly rewritten or
  removed. Withdrawing is the one change left, made once.

Nobody's personal data is here (`NOT_EXPORTED`, `NOT_PERSONAL`); which admin
published it is recorded, as in the admin log.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

QUARTER_PATTERN = r"^[0-9]{4}-Q[1-4]$"
WITHDRAWN_REASON_MIN_LENGTH = 10
WITHDRAWN_REASON_MAX_LENGTH = 500


class CityRateReport(Base):
    __tablename__ = "city_rate_report"
    __table_args__ = (
        CheckConstraint(f"quarter ~ '{QUARTER_PATTERN}'", name="quarter_shape"),
        CheckConstraint("method_version >= 1", name="method_version_positive"),
        CheckConstraint("jsonb_typeof(body) = 'object'", name="body_is_object"),
        CheckConstraint("body_sha256 ~ '^[0-9a-f]{64}$'", name="body_sha256_shape"),
        # Published by someone, or by nobody yet: both or neither.
        CheckConstraint(
            "(published_at IS NULL) = (published_by_account_id IS NULL)",
            name="published_with_its_admin",
        ),
        # A withdrawal always says why, and only a published report has one.
        CheckConstraint(
            "(withdrawn_at IS NULL) = (withdrawn_reason IS NULL)",
            name="withdrawn_with_its_reason",
        ),
        CheckConstraint(
            "withdrawn_at IS NULL OR published_at IS NOT NULL",
            name="withdrawn_only_once_published",
        ),
        CheckConstraint(
            "withdrawn_reason IS NULL OR char_length(btrim(withdrawn_reason))"
            f" BETWEEN {WITHDRAWN_REASON_MIN_LENGTH} AND {WITHDRAWN_REASON_MAX_LENGTH}",
            name="withdrawn_reason_length",
        ),
        # Deleting an admin's account checks here without scanning it
        # (database.md section 5: every foreign key indexed).
        Index("ix_city_rate_report_published_by_account_id", "published_by_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # One report a quarter, keyed `YYYY-Qn` in the Tamil Nadu calendar. The
    # unique constraint is what makes a second build of the same quarter a
    # no-op (ON CONFLICT DO NOTHING), however many runs race.
    quarter: Mapped[str] = mapped_column(String(7), nullable=False, unique=True)
    # Which rules built it (docs/RATE_REPORT_METHOD.md); never changes.
    method_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # The moment the figures were worked out: the report's "as of".
    built_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL means not yet published: read by an admin, by nobody else.
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # RESTRICT: the admin who published a report can never be deleted out
    # from under it, as in the admin log. NULL until published.
    published_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account.id", ondelete="RESTRICT"), nullable=True
    )
    # NULL means it stands. Set once, with the reason readers are shown.
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

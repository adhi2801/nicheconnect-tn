"""How a person wants to be told things outside the app (D-079).

One row per account, written only when the person saves; no row means the
defaults in preference_service.py. It governs delivery outside the app
(push and WhatsApp, once built). The in-app list always keeps every
notification: it is the record of what happened.

Urgent types, those with a deadline running against the reader, can never
be muted; the database refuses it, not only the API.
"""

import uuid
from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.modules.notifications.models import NOTIFICATION_TYPES

# A deadline runs against the reader of each of these, so they always arrive
# at once: an answer is due (memo_sent), a review window runs
# (proof_submitted), the creator has changes to make (proof_revision_requested),
# or the creator's confirmation window runs (payment_marked_paid).
URGENT_TYPES: tuple[str, ...] = (
    "memo_sent",
    "proof_submitted",
    "proof_revision_requested",
    "payment_marked_paid",
)
MUTABLE_TYPES: tuple[str, ...] = tuple(
    kind for kind in NOTIFICATION_TYPES if kind not in URGENT_TYPES
)
DIGEST_CHOICES: tuple[str, ...] = ("off", "daily")


def _sql_array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


class NotificationPreference(Base):
    __tablename__ = "notification_preference"
    __table_args__ = (
        # A quiet window has both ends, or none.
        CheckConstraint(
            "(quiet_from IS NULL) = (quiet_until IS NULL)", name="quiet_hours_whole"
        ),
        # Equal ends would mean "always quiet" or "never": neither is a window.
        CheckConstraint(
            "quiet_from IS NULL OR quiet_from <> quiet_until",
            name="quiet_hours_not_empty",
        ),
        CheckConstraint(f"digest IN {DIGEST_CHOICES}", name="digest_allowed"),
        CheckConstraint("digest_hour BETWEEN 0 AND 23", name="digest_hour_valid"),
        CheckConstraint(
            f"muted_types <@ {_sql_array(MUTABLE_TYPES)}", name="muted_types_allowed"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    # CASCADE: a person's own settings go with their account.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # In Tamil Nadu time. Nullable: NULL in both means no quiet hours.
    quiet_from: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_until: Mapped[time | None] = mapped_column(Time, nullable=True)
    digest: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'off'")
    )
    digest_hour: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("19")
    )
    muted_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

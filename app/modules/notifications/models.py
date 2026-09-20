import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# What happened, told to one account. The text is NOT stored: only the type and
# the details needed to render it, so the app can show it in Tamil or English
# (ux.md section 6). Storing English sentences would make Tamil impossible.

NOTIFICATION_TYPES: tuple[str, ...] = (
    # To the brand
    "application_received",
    "application_withdrawn",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "proof_submitted",
    # To the creator
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_marked_paid",
    # To whichever side did not do it
    "memo_cancelled",
    "payment_confirmed",
)
MAX_DETAILS_LENGTH = 2000


class Notification(Base):
    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(
            f"notification_type IN {tuple(NOTIFICATION_TYPES)}", name="type_allowed"
        ),
        # A small object, not a document: it holds rendering values such as a
        # campaign title, never a whole record and never contact details.
        # Postgres forbids a subquery in a CHECK, so the size is measured on
        # the text form rather than by counting keys.
        CheckConstraint(
            "jsonb_typeof(details) = 'object'"
            f" AND char_length(details::text) <= {MAX_DETAILS_LENGTH}",
            name="details_small_object",
        ),
        # The list: one account's notifications, newest first.
        Index("ix_notification_account_created_at", "account_id", "created_at"),
        # The unread badge: only unread rows, so the index stays small.
        Index(
            "ix_notification_unread",
            "account_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # CASCADE: notifications mean nothing without the account they belong to.
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # What the notification is about, so the app can link straight to it.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("application.id", ondelete="CASCADE"),
        nullable=True,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Nullable on purpose: empty until the person has seen it.
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

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
    "invitation_accepted",
    "invitation_declined",
    # To the creator
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_marked_paid",
    "invitation_received",
    "invitation_withdrawn",
    # To whichever side did not do it
    "memo_cancelled",
    "payment_confirmed",
    # To whoever made a report, when an admin resolves it (item 102)
    "report_resolved",
    # To whoever made a report, the moment it is filed: the IT Rules'
    # acknowledgement, with the time it will be answered by (item 51)
    "report_received",
    # To every admin, when a report nears its deadline and when it passes it
    # unanswered (item 51)
    "report_due_soon",
    "report_overdue",
    # To the owner, when an admin withholds their profile, brand or campaign
    # for legal reasons, and when that is lifted (item 52)
    "content_withheld",
    "content_restored",
    # To every admin, about any admin's login (item 101, D-105): a sign-in
    # with both codes; a phone code right but the second factor refused (or
    # locked); a setup ticket issued or redeemed. Between two founders each
    # sees the other's, so a stolen login cannot go unnoticed.
    "admin_signed_in",
    "admin_second_factor_refused",
    "admin_second_factor_changed",
    # To the account itself, after a risky change made with a second check
    # (item 82, D-107): a new UPI ID set and waiting its 24 hours, or that
    # waiting ID cancelled; the data export downloaded; every session ended.
    # Whoever did it, the owner sees it in the app.
    "upi_change_pending",
    "upi_change_cancelled",
    "data_exported",
    "logged_out_everywhere",
    # To the account itself, about its phone number (item 80, D-108): a
    # change asked for and waiting its 72 hours, that change cancelled, the
    # change made (every session ended), or the change dropped because the
    # new number was taken while it waited.
    "phone_change_requested",
    "phone_change_cancelled",
    "phone_changed",
    "phone_change_failed",
    # To the account itself, when the data export it asked for is ready to
    # download, once, within 24 hours (D-111).
    "data_export_ready",
    # When building it failed every try (D-112): ask for a new one.
    "data_export_failed",
    # To the account itself, about its passkeys (item 79, D-113): one added,
    # one or all removed (by the owner, or by a reset), a reset asked for
    # with the number and waiting 7 days, that reset cancelled by a passkey
    # sign-in, and passkey-only sign-in turned on or off.
    "passkey_added",
    "passkey_removed",
    "passkey_reset_requested",
    "passkey_reset_cancelled",
    "passkey_only_changed",
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
        # Every foreign key indexed, so deleting a campaign or an application
        # finds its notifications without scanning them all (item 98).
        Index(
            "ix_notification_campaign_id",
            "campaign_id",
            postgresql_where=text("campaign_id IS NOT NULL"),
        ),
        Index(
            "ix_notification_application_id",
            "application_id",
            postgresql_where=text("application_id IS NOT NULL"),
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

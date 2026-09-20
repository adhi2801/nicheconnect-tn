"""Request and response shapes for notifications."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.models import NOTIFICATION_TYPES

NotificationType = Literal[
    "application_received",
    "application_withdrawn",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "memo_cancelled",
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_marked_paid",
    "payment_confirmed",
]

assert set(NOTIFICATION_TYPES) == set(NotificationType.__args__)


class NotificationRead(BaseModel):
    """One notification. The app renders the wording from `type` and `details`,
    so the same row can be shown in Tamil or English."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notification_type: NotificationType
    campaign_id: uuid.UUID | None
    application_id: uuid.UUID | None
    details: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class UnreadCount(BaseModel):
    unread: int = Field(description="How many notifications are unread", examples=[3])


class MarkedRead(BaseModel):
    marked_read: int = Field(description="How many changed from unread", examples=[5])

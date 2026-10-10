"""Request and response shapes for notifications."""

import uuid
from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.modules.notifications.models import NOTIFICATION_TYPES
from app.modules.notifications.preference_models import DIGEST_CHOICES

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
    "invitation_received",
    "invitation_accepted",
    "invitation_declined",
    "invitation_withdrawn",
]

ensure_same_values("NotificationType", NotificationType, NOTIFICATION_TYPES)


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


# --- preferences (D-079) -------------------------------------------------------------------

DigestChoice = Literal["off", "daily"]

ensure_same_values("DigestChoice", DigestChoice, DIGEST_CHOICES)

QUIET_TIME = (
    "A time of day in Tamil Nadu, to the minute (`22:00`). Both ends or neither; "
    "a window may cross midnight."
)


class NotificationPreferencesIn(BaseModel):
    """The whole set of preferences. Saving replaces them all, so a retry is safe."""

    model_config = ConfigDict(extra="forbid")

    quiet_from: time | None = Field(description=QUIET_TIME, examples=["22:00"])
    quiet_until: time | None = Field(description=QUIET_TIME, examples=["08:00"])
    digest: DigestChoice = Field(
        description="`daily` collects every non-urgent notification into one a day"
    )
    digest_hour: int = Field(
        ge=0, le=23, description="The digest's hour, Tamil Nadu time"
    )
    muted_types: list[NotificationType] = Field(
        max_length=len(NOTIFICATION_TYPES),
        description="Kept in the app only, never sent. Urgent types are refused.",
    )

    @model_validator(mode="after")
    def quiet_hours_are_a_window(self) -> NotificationPreferencesIn:
        start, end = self.quiet_from, self.quiet_until
        if (start is None) != (end is None):
            raise PydanticCustomError(
                "quiet_hours_whole", "Give both ends of the quiet hours, or neither"
            )
        for moment in (start, end):
            if moment is not None and (
                moment.second or moment.microsecond or moment.tzinfo is not None
            ):
                raise PydanticCustomError(
                    "quiet_hours_minutes",
                    "Quiet hours are a time of day to the minute, with no time zone",
                )
        if start is not None and start == end:
            raise PydanticCustomError(
                "quiet_hours_empty", "Quiet hours must start and end at different times"
            )
        return self


class NotificationPreferencesRead(BaseModel):
    """How this person is told things outside the app.

    The in-app list keeps every notification whatever is set here. The types
    in `always_sent` arrive at once whatever is set, because a deadline runs
    against the reader.
    """

    quiet_from: str | None = Field(description="HH:MM, Tamil Nadu time")
    quiet_until: str | None = Field(description="HH:MM, Tamil Nadu time")
    digest: DigestChoice
    digest_hour: int
    muted_types: list[NotificationType]
    always_sent: list[NotificationType]
    is_default: bool = Field(description="True until the person saves their own")
    saved_at: datetime | None

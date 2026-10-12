"""Request and response shapes for push devices (item 9, D-095)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.modules.notifications.device_models import (
    APP_VERSION_MAX_LENGTH,
    DEVICE_PLATFORMS,
    TOKEN_MAX_LENGTH,
    TOKEN_MIN_LENGTH,
    TOKEN_PATTERN,
)

DevicePlatform = Literal["android", "ios", "ios_live_activity"]
ensure_same_values("DevicePlatform", DevicePlatform, DEVICE_PLATFORMS)

PushToken = Annotated[
    str,
    Field(
        min_length=TOKEN_MIN_LENGTH,
        max_length=TOKEN_MAX_LENGTH,
        pattern=TOKEN_PATTERN,
        description=(
            "The token Firebase (Android) or Apple (iPhone, Live Activity) gave "
            "this install. Sent in the body, never a URL, so it reaches no log"
        ),
        examples=["fMEP0vJqS0Kp1Xz9:APA91bH-example-token-from-firebase-0123456789"],
    ),
]


class DeviceRegister(BaseModel):
    """Register this phone, or refresh it. Send on every app start."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token: PushToken
    platform: DevicePlatform = Field(
        description="`ios_live_activity` for a Live Activity's own push token"
    )
    app_version: Annotated[
        str | None,
        Field(min_length=1, max_length=APP_VERSION_MAX_LENGTH, examples=["1.4.0 (212)"]),
    ] = None


class DeviceRead(BaseModel):
    """A registered phone. Its token is never returned."""

    id: uuid.UUID = Field(description="Keep it to unregister this phone later")
    platform: DevicePlatform
    app_version: str | None
    last_seen_at: datetime
    created_at: datetime

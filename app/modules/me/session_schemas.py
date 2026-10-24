"""Response shapes for where you are logged in (item 81, D-114)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.auth.schemas import ClientPlatform, SignInMethod


class SessionRead(BaseModel):
    """One login still able to refresh, as its owner sees it."""

    id: uuid.UUID = Field(
        description="The session; end it at DELETE /api/v1/me/sessions/{id}"
    )
    platform: ClientPlatform | None = Field(
        description="What the app said it is at sign-in; null when it said nothing"
    )
    label: str | None = Field(
        description=(
            "The name the app gave itself at sign-in, never checked; null when it "
            "said nothing. Show it beside `signed_in_at` and `signed_in_with`, "
            "which no app can choose"
        ),
        examples=["Pixel 8"],
    )
    signed_in_at: datetime = Field(description="When this login was made")
    last_active_at: datetime = Field(
        description=(
            "When it last renewed its access, at most 15 minutes behind its last "
            "use while in use"
        )
    )
    expires_at: datetime = Field(
        description="When it ends unless it is used again before then"
    )
    signed_in_with: SignInMethod = Field(
        description=(
            "`phone_code`, `passkey`, or `two_factors` (an admin's phone code "
            "and authenticator)"
        )
    )
    is_current: bool = Field(description="True for the session making this request")
    sign_in_acknowledged_at: datetime | None = Field(
        default=None,
        description=(
            "When you said this sign-in was yours, from a device signed in before "
            "it; it then leaves the attention list. Null until then"
        ),
    )

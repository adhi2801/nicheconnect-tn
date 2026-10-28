"""Request and response shapes for changing the phone number (item 80, D-108)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.schemas import IndianMobile, OtpCode


class PhoneChangeIn(BaseModel):
    """The new number, and the login code sent to it."""

    model_config = ConfigDict(extra="forbid")

    new_phone: IndianMobile
    new_phone_code: OtpCode = Field(
        description=(
            "The 6-digit code sent to the new number: ask for it at "
            "`POST /api/v1/auth/otp/request` with the new number. It is used "
            "up here, so it logs nobody in."
        )
    )


class PhoneChangeWaitingRead(BaseModel):
    """A new number waiting to take over the login."""

    new_phone: str = Field(examples=["+919876501234"])
    requested_at: datetime
    takes_effect_at: datetime = Field(
        description=(
            "When the new number takes over, 72 hours after it was asked for. "
            "Until then you log in with your current number, and can cancel "
            "with `DELETE /api/v1/me/phone-change`, with no code. Then every "
            "session ends, within a minute, and you log in with the new number."
        )
    )
    without_current_number: bool = Field(
        description=(
            "Asked for without a code from your current number, which you said "
            "is lost: it waits 7 days, and any login with your current number "
            "before then cancels it."
        )
    )


class PhoneChangeRead(BaseModel):
    """The number you log in with, and a new one waiting, if any."""

    phone: str = Field(
        description="The number you log in with now", examples=["+919876543210"]
    )
    waiting: PhoneChangeWaitingRead | None

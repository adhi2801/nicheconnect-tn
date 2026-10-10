"""Request and response shapes for the UPI pay link (D-085)."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.taxonomy import CURRENCY
from app.modules.payment_status.upi_models import (
    NOTICE_VERSION_MAX_LENGTH,
    PHONE_LIKE_NAME,
    UPI_ID_MAX_LENGTH,
    UPI_ID_PATTERN,
)

UnavailableReason = Literal["no_upi_id", "above_upi_limit"]


class UpiSet(BaseModel):
    """A creator gives their UPI ID, having read the notice."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    upi_id: Annotated[
        str,
        Field(
            max_length=UPI_ID_MAX_LENGTH,
            description=(
                "name@handle, as your UPI app shows it. Not one made of your "
                "phone number: your UPI app lets you create a name instead."
            ),
            examples=["meena.cooks@okhdfcbank"],
        ),
    ]
    consent: Literal[True] = Field(
        description="Must be true: you agree to the notice you were shown"
    )
    notice_version: Annotated[
        str,
        Field(
            min_length=1,
            max_length=NOTICE_VERSION_MAX_LENGTH,
            description="The version of the notice you were shown",
        ),
    ]

    @field_validator("upi_id")
    @classmethod
    def a_real_upi_id(cls, value: str) -> str:
        value = value.lower()
        if not re.fullmatch(UPI_ID_PATTERN, value):
            raise PydanticCustomError(
                "upi_id_format", "Enter your UPI ID as it appears in your UPI app"
            )
        if re.fullmatch(PHONE_LIKE_NAME, value.split("@", 1)[0]):
            raise PydanticCustomError(
                "upi_id_reveals_phone",
                "This UPI ID is your phone number, which brands would see. "
                "Create a UPI ID with a name in your UPI app and use that.",
            )
        return value


class UpiRead(BaseModel):
    """The creator's own UPI ID, and the consent it was given under.

    All null when they have not added one.
    """

    upi_id: str | None
    consented_at: datetime | None
    notice_version: str | None
    updated_at: datetime | None


class PayDetailsRead(BaseModel):
    """What the brand needs to pay the creator directly, by UPI.

    `pay_link` opens the brand's own UPI app with everything filled in; the
    brand checks the name the app shows (the bank's, not ours) and approves
    with its PIN. NicheConnect TN never receives the money. `pay_link` is
    null when the creator has added no UPI ID, or when the amount is above
    what UPI allows between people in a day, and `unavailable_reason` says
    which: pay by bank transfer instead.
    """

    payee_name: str = Field(description="The creator's display name")
    upi_id: str | None
    amount_paise: int
    currency: Literal["INR"] = CURRENCY
    pay_link: str | None = Field(
        description="A upi://pay link; render it as a button, or as a QR code"
    )
    unavailable_reason: UnavailableReason | None
    upi_id_set_at: datetime | None = Field(
        description="When the creator last set their UPI ID"
    )
    upi_id_changed_recently: bool = Field(
        description=(
            "True when the UPI ID was set in the last 24 hours. Worth confirming "
            "with the creator before paying: a changed ID is how payment fraud "
            "usually starts."
        )
    )

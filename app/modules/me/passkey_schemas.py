"""Request and response shapes for passkeys (item 79, D-113)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.models.passkey import PASSKEY_NAME_MAX_LENGTH
from app.modules.auth.passkey_schemas import WebAuthnCredential
from app.modules.auth.schemas import IndianMobile, OtpCode

PasskeyName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=PASSKEY_NAME_MAX_LENGTH,
        description="A name you will recognise it by",
        examples=["My phone"],
    ),
]


class PasskeyRead(BaseModel):
    """One of your passkeys, as you can recognise it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    aaguid: uuid.UUID = Field(
        description="Which kind of authenticator made it (a password manager, a "
        "security key), as it says; never who you are"
    )
    backup_eligible: bool = Field(description="Whether it may sync to your other devices")
    backup_state: bool = Field(description="Whether it is synced now")
    last_used_at: datetime | None
    created_at: datetime


class PasskeyResetRead(BaseModel):
    """A reset of your passkeys, waiting."""

    model_config = ConfigDict(from_attributes=True)

    requested_at: datetime
    takes_effect_at: datetime = Field(
        description=(
            "When every passkey is removed, 7 days after it was asked for. Any "
            "sign-in with a passkey before then cancels it."
        )
    )


class PasskeysRead(BaseModel):
    """Your passkeys, whether only they sign you in, and a reset waiting."""

    items: list[PasskeyRead] = Field(
        description="Every passkey, oldest first: at most 10, a bound by rule"
    )
    passkey_only: bool = Field(
        description="When true, a phone code no longer signs you in"
    )
    reset: PasskeyResetRead | None


class PasskeyCreate(BaseModel):
    """A new passkey: the phone's answer to the sign-up challenge, and a name."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    credential: WebAuthnCredential
    name: PasskeyName


class PasskeyRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: PasskeyName


class PasskeyOnlySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        description="True: only a passkey signs you in. False: a phone code does too."
    )


class PasskeyResetIn(BaseModel):
    """Your number, and a login code sent to it."""

    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile
    code: OtpCode

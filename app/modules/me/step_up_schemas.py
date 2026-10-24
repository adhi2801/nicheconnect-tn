"""Request and response shapes for asking for a second check (item 82, D-107; passkeys D-113)."""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.literals import ensure_same_values
from app.modules.auth.models.step_up_challenge import STEP_UP_ACTIONS
from app.modules.auth.passkey_schemas import WebAuthnCredential
from app.modules.auth.schemas import IndianMobile
from app.modules.auth.step_up_service import StepUpAction, StepUpMethod
from app.modules.payment_status.upi_schemas import UPI_ID_FIELD, a_real_upi_id

ensure_same_values("StepUpAction", StepUpAction, STEP_UP_ACTIONS)


class StepUpForUpiId(BaseModel):
    """A code to set one exact UPI ID: it cannot set any other."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["set_upi_id"]
    upi_id: Annotated[str, UPI_ID_FIELD]

    @field_validator("upi_id")
    @classmethod
    def upi_id_is_real(cls, value: str) -> str:
        return a_real_upi_id(value)


class StepUpForPhone(BaseModel):
    """A code to move the account onto one exact new number (item 80)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["change_phone"]
    new_phone: IndianMobile


class StepUpForExport(BaseModel):
    """A code to download one exact data export, which must be ready (D-111, D-112)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["download_export"]
    export_id: uuid.UUID


class StepUpForAccount(BaseModel):
    """A code to log out of every device, or to add a passkey (D-113)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["log_out_everywhere", "add_passkey"]


class StepUpForPasskeyRemoval(BaseModel):
    """A code to remove one exact passkey (D-113)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["remove_passkey"]
    passkey_id: uuid.UUID


class StepUpForPasskeyOnly(BaseModel):
    """A code to turn passkey-only sign-in exactly on, or exactly off (D-113)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["passkey_only"]
    enabled: bool


class StepUpForSession(BaseModel):
    """A code to end one exact other session of yours (item 81, D-114)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["end_session"]
    session_id: uuid.UUID


StepUpIn = Annotated[
    StepUpForUpiId
    | StepUpForPhone
    | StepUpForExport
    | StepUpForAccount
    | StepUpForPasskeyRemoval
    | StepUpForPasskeyOnly
    | StepUpForSession,
    Field(discriminator="action"),
]


class StepUpAccepted(BaseModel):
    """How to prove this change, and for how long the code works."""

    action: StepUpAction
    method: StepUpMethod = Field(
        description=(
            "`phone_code`: a code was sent to your phone. `authenticator`: "
            "admins only; nothing was sent, use the code your authenticator "
            "app shows. `passkey`: you have a passkey, so nothing was sent: "
            "answer `passkey_options` with it at `POST "
            "/api/v1/me/step-up/passkey`, which gives the code."
        )
    )
    expires_in_seconds: int | None = Field(
        description=(
            "How long the code, or the passkey's challenge, works; null for an "
            "authenticator code"
        ),
        examples=[300],
    )
    passkey_options: dict[str, Any] | None = Field(
        default=None,
        description=(
            "For `passkey`: WebAuthn's request options, to pass to "
            "`navigator.credentials.get` (or the phone's credential manager)"
        ),
    )


class StepUpPasskeyIn(BaseModel):
    """A passkey's answer to the challenge for one change."""

    model_config = ConfigDict(extra="forbid")

    change: StepUpIn
    credential: WebAuthnCredential


class StepUpGranted(BaseModel):
    """The code for exactly this change, earned by the passkey (D-113)."""

    action: StepUpAction
    code: str = Field(
        description="Send it in the `Step-Up-Code` header with the change itself",
        examples=["042917"],
    )
    expires_in_seconds: int = Field(examples=[300])

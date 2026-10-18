"""Request and response shapes for asking for a second check (item 82, D-107)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.literals import ensure_same_values
from app.modules.auth.models.step_up_challenge import STEP_UP_ACTIONS
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
    """A code to log out of every device."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["log_out_everywhere"]


StepUpIn = Annotated[
    StepUpForUpiId | StepUpForPhone | StepUpForExport | StepUpForAccount,
    Field(discriminator="action"),
]


class StepUpAccepted(BaseModel):
    """How to prove this change, and for how long the code works."""

    action: StepUpAction
    method: StepUpMethod = Field(
        description=(
            "`phone_code`: a code was sent to your phone. `authenticator`: "
            "admins only; nothing was sent, use the code your authenticator "
            "app shows."
        )
    )
    expires_in_seconds: int | None = Field(
        description="How long the code works; null for an authenticator code",
        examples=[300],
    )

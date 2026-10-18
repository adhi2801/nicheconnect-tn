"""Request shapes for passkey answers (item 79, D-113), shared by every layer above auth."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

# A passkey's answer, as the browser or phone gives it (WebAuthn's JSON form
# of a PublicKeyCredential). Checked by fido2, never trusted as it comes.
WebAuthnCredential = Annotated[
    dict[str, Any],
    Field(
        description=(
            "The passkey's answer, exactly as `navigator.credentials` (or the "
            "phone's credential manager) gives it, in WebAuthn's JSON form"
        )
    ),
]


class PasskeyLoginIn(BaseModel):
    """A passkey's answer to a login challenge."""

    model_config = ConfigDict(extra="forbid")

    credential: WebAuthnCredential

"""Request and response shapes for assistants' tokens (item 11, D-138)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.modules.auth.models.agent_token import (
    AGENT_SCOPES,
    AGENT_TOKEN_MAX_LIFETIME,
    AGENT_TOKEN_NAME_MAX_LENGTH,
)
from app.modules.auth.schemas import CLIENT_LABEL_PATTERN

AgentScope = Literal[
    "deals:read",
    "campaigns:read",
    "applications:write",
    "notes:write",
    "alerts:write",
]
ensure_same_values("AgentScope", AgentScope, AGENT_SCOPES)

AgentScopes = Annotated[
    list[AgentScope],
    Field(
        min_length=1,
        max_length=len(AGENT_SCOPES),
        description=(
            "What the assistant may do. `deals:read`: your deals, their notes, "
            "proof, record and feedback, never a payment, UPI ID or address. "
            "`campaigns:read`: campaigns and applications as you see them. "
            "`applications:write`: applying and withdrawing, answering an "
            "invitation, and a brand's shortlisting or turning down; never "
            "accepting one. `notes:write`: adding a note to a deal. "
            "`alerts:write`: your campaign alerts. No scope reaches money, your "
            "phone, passkeys, sessions, exports or deletion"
        ),
        examples=[["deals:read", "campaigns:read"]],
    ),
]


class AgentTokenCreate(BaseModel):
    """A token for one assistant: what it is called, what it may do, how long it lasts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(
        min_length=1,
        max_length=AGENT_TOKEN_NAME_MAX_LENGTH,
        pattern=CLIENT_LABEL_PATTERN,
        description="The assistant it is for, as you will recognise it",
        examples=["Claude on my laptop"],
    )
    scopes: AgentScopes
    expires_in_days: int = Field(
        ge=1,
        le=AGENT_TOKEN_MAX_LIFETIME.days,
        description="How many days it works for, at most 90",
        examples=[30],
    )


class AgentTokenRead(BaseModel):
    """One of your assistants' tokens, never its value."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Revoke it at DELETE /api/v1/me/agent-tokens/{id}")
    name: str
    scopes: list[AgentScope]
    expires_at: datetime
    last_used_at: datetime | None = Field(
        description="When it was last used, to within a minute; null if never"
    )
    created_at: datetime


class AgentTokenCreated(AgentTokenRead):
    """The new token, with its value: shown this once and never again."""

    token: str = Field(
        description=(
            "Give it to the assistant as `Authorization: Bearer <token>`. It is "
            "shown only now; we keep no copy we could show you again"
        ),
        # Low in entropy on purpose, so no secret scanner mistakes it.
        examples=["nct_" + "x" * 43],
    )

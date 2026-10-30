"""Request and response shapes for team seats (item 13, D-148).

A phone number goes in, to invite someone, and never comes back out: the
team and the invites are shown by first name and role only.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.modules.auth.models.brand_team import (
    BRAND_ROLES,
    FIRST_NAME_MAX_LENGTH,
    TEAM_ROLES,
)
from app.modules.auth.schemas import IndianMobile

TeamRole = Literal["admin", "campaigns", "finance"]
ensure_same_values("TeamRole", TeamRole, TEAM_ROLES)
BrandRole = Literal["owner", "admin", "campaigns", "finance"]
ensure_same_values("BrandRole", BrandRole, BRAND_ROLES)

FIRST_NAME_PATTERN = r"^[^\x00-\x1f\x7f]+$"


class TeamInviteCreate(BaseModel):
    """Someone to invite: their number, the role they will hold, the name you know them by."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    phone: IndianMobile
    role: TeamRole = Field(
        description=(
            "`campaigns`: campaigns, applicants, memos and approving work. "
            "`finance`: marking payments and disputes. `admin`: all of that and "
            "the team, invited by the owner alone, with a step-up code"
        )
    )
    first_name: str = Field(
        min_length=1,
        max_length=FIRST_NAME_MAX_LENGTH,
        pattern=FIRST_NAME_PATTERN,
        description="Shown to creators beside the brand's name when they act",
        examples=["Ravi"],
    )


class TeamInviteAccept(BaseModel):
    """Joining: optionally, the first name you want creators to see."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=FIRST_NAME_MAX_LENGTH,
        pattern=FIRST_NAME_PATTERN,
        description="Leave it out to keep the name the inviter gave",
    )


class TeamRoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: TeamRole


class TeamMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: TeamRole
    first_name: str
    created_at: datetime


class TeamInviteRead(BaseModel):
    """An invite as the brand sees it: never the number."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: TeamRole
    first_name: str
    expires_at: datetime
    created_at: datetime


class TeamRead(BaseModel):
    brand_id: uuid.UUID
    brand_name: str
    your_role: BrandRole
    members: list[TeamMemberRead] = Field(description="At most 20, the owner not counted")
    invites: list[TeamInviteRead] = Field(description="Invites still open, oldest first")


class MyTeamInviteRead(BaseModel):
    """An invite to your own number, waiting for your answer."""

    id: uuid.UUID
    brand_id: uuid.UUID
    brand_name: str
    role: TeamRole
    first_name: str
    expires_at: datetime

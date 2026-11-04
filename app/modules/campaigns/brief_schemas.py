"""Request and response shapes for drafted campaign briefs (item 40, D-156)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.literals import ensure_same_values
from app.core.taxonomy import Niche
from app.modules.campaigns.brief_models import (
    BRIEF_STATUSES,
    IDEA_MAX_LENGTH,
    IDEA_MIN_LENGTH,
)
from app.modules.campaigns.schemas import CampaignType

BriefStatus = Literal["waiting", "ready", "failed"]
ensure_same_values("BriefStatus", BriefStatus, BRIEF_STATUSES)


class BriefDraftCreate(BaseModel):
    """What the brand wants, in its own words."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idea: str = Field(
        min_length=IDEA_MIN_LENGTH,
        max_length=IDEA_MAX_LENGTH,
        description="A few sentences: the product, who it is for, what you want made, and any budget or city",
        examples=[
            "Our new millet laddu box for Pongal. Two reels from Madurai food creators, Rs 8,000 each."
        ],
    )


class BriefFieldsRead(BaseModel):
    """The drafted fields, ready to prefill the new-campaign form. Only what the brand's words supported."""

    title: str
    description: str
    deliverables: str
    campaign_type: CampaignType | None = Field(
        description="Null when the words did not say"
    )
    niches: list[Niche]
    cities: list[str] = Field(
        description="Only cities the brand named; empty when it named none"
    )
    budget_min_paise: int | None
    budget_max_paise: int | None


class BriefDraftRead(BaseModel):
    """A draft, as the brand's team sees it."""

    id: uuid.UUID
    status: BriefStatus = Field(
        description="`waiting` while it is written (usually within a minute), `ready` with `draft`, or `failed`"
    )
    idea: str
    draft: BriefFieldsRead | None
    failure: str | None = Field(
        description="Why it could not be drafted, when `failed`: ask again in other words",
        examples=["refusal"],
    )
    created_at: datetime

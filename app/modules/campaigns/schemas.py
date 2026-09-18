"""Request and response shapes for campaigns (backend.md sections 2 and 4)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.taxonomy import CURRENCY, MAX_NICHES, NICHES
from app.modules.campaigns.models import (
    BUDGETED_TYPES,
    CAMPAIGN_TYPES,
    DELIVERABLES_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    MAX_CITIES,
    TITLE_MAX_LENGTH,
)

CampaignType = Literal["paid", "barter", "commission", "local_business"]
CampaignStatus = Literal["draft", "open", "closed", "cancelled"]
Niche = Literal[
    "food",
    "fashion",
    "beauty",
    "tech",
    "travel",
    "fitness",
    "education",
    "entertainment",
    "finance",
    "lifestyle",
]

# The literal above must stay in step with the shared list and the database.
assert set(NICHES) == set(Niche.__args__)
assert set(CAMPAIGN_TYPES) == set(CampaignType.__args__)

Title = Annotated[str, Field(min_length=1, max_length=TITLE_MAX_LENGTH, examples=["Pongal sweets launch"])]
Description = Annotated[str, Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)]
Deliverables = Annotated[
    str,
    Field(
        min_length=1,
        max_length=DELIVERABLES_MAX_LENGTH,
        examples=["3 Instagram reels, 1 story set"],
    ),
]
City = Annotated[str, Field(min_length=2, max_length=60, examples=["Madurai"])]
Cities = Annotated[list[City], Field(min_length=1, max_length=MAX_CITIES)]
Niches = Annotated[list[Niche], Field(min_length=1, max_length=MAX_NICHES)]
Paise = Annotated[
    int,
    Field(gt=0, le=10_000_000_000, description="Whole paise, e.g. 500000 is Rs 5,000"),
]


def _check_budget(campaign_type: str, minimum: int | None, maximum: int | None) -> None:
    """The same rules the database enforces, with friendlier messages."""
    if (minimum is None) != (maximum is None):
        raise PydanticCustomError(
            "budget_incomplete", "Give both a minimum and a maximum budget, or neither"
        )
    if minimum is not None and maximum is not None and maximum < minimum:
        raise PydanticCustomError(
            "budget_backwards", "The maximum budget cannot be lower than the minimum"
        )
    if campaign_type == "barter" and minimum is not None:
        raise PydanticCustomError(
            "budget_on_barter", "A barter campaign pays in goods, so it has no budget"
        )
    if campaign_type in BUDGETED_TYPES and minimum is None:
        raise PydanticCustomError(
            "budget_required", "Give a budget range for this campaign type"
        )


class CampaignCreate(BaseModel):
    """What a brand sends to create a campaign. It starts as a draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title
    description: Description
    campaign_type: CampaignType
    budget_min_paise: Paise | None = None
    budget_max_paise: Paise | None = None
    cities: Cities
    niches: Niches
    deliverables: Deliverables
    applications_close_on: date | None = None

    @model_validator(mode="after")
    def check_budget(self) -> "CampaignCreate":
        _check_budget(self.campaign_type, self.budget_min_paise, self.budget_max_paise)
        return self


class CampaignUpdate(BaseModel):
    """Fields a brand may change. Anything left out stays as it is."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title | None = None
    description: Description | None = None
    campaign_type: CampaignType | None = None
    budget_min_paise: Paise | None = None
    budget_max_paise: Paise | None = None
    cities: Cities | None = None
    niches: Niches | None = None
    deliverables: Deliverables | None = None
    applications_close_on: date | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "CampaignUpdate":
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class CampaignRead(BaseModel):
    """A campaign as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: str
    campaign_type: CampaignType
    budget_min_paise: int | None
    budget_max_paise: int | None
    currency: Literal["INR"] = CURRENCY
    cities: list[str]
    niches: list[str]
    deliverables: str
    applications_close_on: date | None
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime

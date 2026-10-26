"""What a match looks like on the wire (D-052, backlog D3)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.modules.auth.schemas import ChannelPlatform, PublicCreatorSummary
from app.modules.campaigns.schemas import CampaignRead
from app.modules.deal_memo.schemas import CreatorDeliveryRead
from app.modules.matching.creator_list_models import LIST_NAME_MAX_LENGTH
from app.modules.payment_status.schemas import BrandReliabilityRead


class MatchReasonsRead(BaseModel):
    """Why this creator was returned, in facts a brand can check.

    A score on its own is not an explanation: a brand has no way to know
    whether 0.83 is good. These are the things that actually decided the
    result, and all but one of them are facts rather than a model's opinion.
    """

    model_config = ConfigDict(from_attributes=True)

    shared_niches: list[str] = Field(
        description="Niches this creator and the campaign have in common",
        examples=[["food", "travel"]],
    )
    city: str = Field(
        description="The creator's city, which is one the campaign named",
        examples=["Madurai"],
    )
    accepted_deals: int = Field(
        description=(
            "How many deal memos this creator has accepted, with any brand. "
            "Accepted, not delivered: it says they have worked before, not "
            "that the work went well"
        ),
        examples=[3],
    )
    similarity: float | None = Field(
        description=(
            "How close the creator's profile reads to the campaign brief, "
            "from 0 to 1. **Null when the campaign has not been indexed yet**, "
            "in which case the results are ordered by the facts above and are "
            "still worth reading"
        ),
        examples=[0.83],
    )
    booked_until: date | None = Field(
        default=None,
        description=(
            "The last day the creator is not taking new work, or null if they "
            "are taking work today. Creators taking work come first"
        ),
        examples=[None],
    )


class CreatorMatchRead(BaseModel):
    """One suggested creator, and why."""

    creator: PublicCreatorSummary
    reasons: MatchReasonsRead


class CreatorMatchesRead(BaseModel):
    """The whole answer, with enough context to read the list honestly."""

    matches: list[CreatorMatchRead]
    ranked_by_similarity: bool = Field(
        description=(
            "False when the campaign has no embedding yet, so the order comes "
            "from the facts alone. Say so in the interface rather than showing "
            "an unranked list as if it were ranked"
        ),
        examples=[True],
    )


# --- the creator's side --------------------------------------------------------


class CampaignMatchReasonsRead(BaseModel):
    """Why this campaign was suggested to a creator, in facts they can check."""

    shared_niches: list[str] = Field(
        description="Niches this campaign and the creator have in common",
        examples=[["food"]],
    )
    city: str = Field(
        description="The creator's city, which is one the campaign named",
        examples=["Madurai"],
    )
    similarity: float | None = Field(
        description=(
            "How close the brief reads to the creator's profile, from 0 to 1. "
            "**Null when either side has not been indexed yet** (a creator is "
            "indexed once they publish their Passport); the list is then "
            "newest first"
        ),
        examples=[0.79],
    )
    brand_payments: BrandReliabilityRead = Field(
        description=(
            "How this brand pays, exactly as its reliability page says. The "
            "figures are null below three completed deals, meaning **not "
            "enough to say**, never zero; `currently_overdue` is always "
            "reported"
        )
    )


class CampaignMatchRead(BaseModel):
    """One suggested campaign, and why."""

    campaign: CampaignRead
    reasons: CampaignMatchReasonsRead


class CampaignMatchesRead(BaseModel):
    """Campaigns suggested to the signed-in creator, best first."""

    matches: list[CampaignMatchRead]
    ranked_by_similarity: bool = Field(
        description=(
            "False when the creator has no embedding yet, so the list is "
            "newest first. Say so rather than presenting it as a ranking"
        ),
        examples=[True],
    )


class SearchChannelRead(BaseModel):
    """A channel's size, as the creator stated it and when."""

    platform: ChannelPlatform
    followers: int
    figures_as_of: date
    self_reported: Literal[True] = Field(
        default=True,
        description="Always true. The creator's number, never verified by us",
    )


class CreatorSearchResultRead(BaseModel):
    """One creator in a brand's search: enough to decide whether to open the media kit."""

    creator_id: uuid.UUID
    handle: str
    display_name: str
    city: str
    niches: list[str]
    bio: str | None
    member_since: str = Field(examples=["2026-09"])
    channels: list[SearchChannelRead]
    from_price_paise: int | None = Field(
        description=(
            "The cheapest package that answers the search (of the format and "
            "platform asked for, if any). Null when the creator lists none"
        )
    )
    currency: str
    booked_until: date | None = Field(
        description="The last day the creator is not taking new work; null if taking work today"
    )


# --- saved creator lists (item 66, D-129) ---------------------------------------


class CreatorListIn(BaseModel):
    """A list's name, when making or renaming one."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(
        min_length=1, max_length=LIST_NAME_MAX_LENGTH, examples=["Diwali food creators"]
    )


class CreatorListRead(BaseModel):
    """One of the brand's lists. Private: the creators on it are never told."""

    id: uuid.UUID
    name: str
    creators: int = Field(
        description=(
            "How many creators on it you can find today; one who unpublished, "
            "left or was withheld, or a block, takes them out of view"
        )
    )
    created_at: datetime
    updated_at: datetime


class ListedCreatorRead(CreatorSearchResultRead):
    """A creator on a list: search's facts, how they deliver, and when you saved them."""

    saved_at: datetime
    delivery: CreatorDeliveryRead = Field(
        description="What happened on their deals, not reviews; null shares mean "
        "not enough to say, never zero"
    )


class SimilarAnchorRead(BaseModel):
    """One of the creators who delivered for you, that this one is closest to."""

    creator_id: uuid.UUID
    handle: str


class SimilarCreatorRead(CreatorSearchResultRead):
    """A creator like those who delivered for you: why, and how they deliver."""

    similarity: float = Field(
        description="1 is the same; closeness of their public profile to your anchors'"
    )
    closest_to: SimilarAnchorRead = Field(
        description="Which creator who delivered for you this one is most like"
    )
    delivery: CreatorDeliveryRead


class SimilarPageRead(BaseModel):
    """A page of creators like the ones who delivered for you."""

    based_on: int = Field(
        description=(
            "How many creators who finished a deal with you this rests on; 0 means "
            "none yet, and the list is empty"
        )
    )
    items: list[SimilarCreatorRead]
    next_cursor: str | None = Field(
        default=None, description="Pass as ?cursor= to get the next page"
    )

"""What a match looks like on the wire (D-052, backlog D3)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.schemas import PublicCreatorSummary
from app.modules.campaigns.schemas import CampaignRead
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

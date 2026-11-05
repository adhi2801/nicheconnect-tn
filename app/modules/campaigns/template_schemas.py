"""Festival campaign templates on the wire (item 14, piece 1, D-161)."""

from pydantic import BaseModel, Field

from app.core.taxonomy import Niche
from app.modules.campaigns import festival_templates
from app.modules.campaigns.schemas import CampaignType


class TemplateCampaignRead(BaseModel):
    """The campaign the template starts: pass these to `POST /api/v1/campaigns` with
    the brand's own `cities`, and a budget for a paid campaign."""

    title: str
    description: str
    campaign_type: CampaignType = Field(examples=["paid"])
    deliverables: str
    niches: list[Niche]


class CampaignTemplateRead(BaseModel):
    key: str = Field(
        description="Stable, for a link to one template", examples=["pongal"]
    )
    name: str = Field(examples=["Pongal"])
    when: str = Field(examples=["Mid-January, the first day of the Tamil month of Thai"])
    months: list[int] = Field(
        description=(
            "The months it falls in, 1 to 12. Empty for a festival that follows the moon, "
            "whose dates the brand sets"
        ),
        examples=[[1]],
    )
    lead_weeks: int = Field(description="How many weeks ahead to publish", examples=[6])
    campaign: TemplateCampaignRead


def to_template_read(t: festival_templates.FestivalTemplate) -> CampaignTemplateRead:
    return CampaignTemplateRead(
        key=t.key,
        name=t.name,
        when=t.when,
        months=list(t.months),
        lead_weeks=t.lead_weeks,
        campaign=TemplateCampaignRead(
            title=t.title,
            description=t.description,
            campaign_type="paid",
            deliverables=t.deliverables,
            niches=list(t.niches),
        ),
    )

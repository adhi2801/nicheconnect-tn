"""Festival campaign templates on the wire (item 14, piece 1, D-161, D-165)."""

from datetime import date

from pydantic import BaseModel, Field

from app.core.taxonomy import Niche
from app.modules.campaigns import festival_templates
from app.modules.campaigns.schemas import CampaignType, DeliverableIn


class TemplateCampaignRead(BaseModel):
    """The campaign the template starts: pass these to `POST /api/v1/campaigns` with
    the brand's own `cities`, and a budget for a paid campaign."""

    title: str
    description: str
    campaign_type: CampaignType = Field(examples=["paid"])
    deliverables: str
    deliverable_items: list[DeliverableIn]
    niches: list[Niche]


class CampaignTemplateRead(BaseModel):
    key: str = Field(
        description="Stable: the same festival keeps its key", examples=["pongal"]
    )
    name: str = Field(examples=["Pongal"])
    when: str = Field(
        examples=["Mid-January: Bhogi, Thai Pongal on the first day of Thai"]
    )
    starts_on: date = Field(
        description="When it next starts, or started if it is under way",
        examples=["2027-01-14"],
    )
    ends_on: date = Field(examples=["2027-01-17"])
    publish_by: date = Field(
        description="The day to have the campaign open by: `lead_weeks` before `starts_on`",
        examples=["2026-12-03"],
    )
    dates_confirmed: bool = Field(
        description=(
            "True when the dates are fixed or notified by the Tamil Nadu Government; "
            "false when they are expected, from an almanac or from the moon"
        )
    )
    depends_on_moon: bool = Field(
        description="The day is set by the moon being sighted, so it can move by a day"
    )
    lead_weeks: int = Field(description="How many weeks ahead to publish", examples=[6])
    campaign: TemplateCampaignRead


def to_template_read(
    t: festival_templates.FestivalTemplate, o: festival_templates.Occurrence
) -> CampaignTemplateRead:
    return CampaignTemplateRead(
        key=t.key,
        name=t.name,
        when=t.when,
        starts_on=o.starts_on,
        ends_on=o.ends_on,
        publish_by=festival_templates.publish_by(t, o),
        dates_confirmed=o.confirmed,
        depends_on_moon=t.moon,
        lead_weeks=t.lead_weeks,
        campaign=TemplateCampaignRead(
            title=t.title,
            description=t.description,
            campaign_type="paid",
            deliverables=t.deliverables,
            deliverable_items=[
                DeliverableIn(platform=i.platform, format=i.format, quantity=i.quantity)
                for i in t.items
            ],
            niches=list(t.niches),
        ),
    )

"""Whether a campaign fits a creator's alert (item 43, D-130). Pure.

This is the rule written down once; `alert_service` asks the same question
in SQL, so a campaign fits the same alerts whichever way it is asked, and
the tests hold the two to each other.

Each term an alert names must hold; a term left empty holds for anything:

- a city: the campaign is in it, in any case ("madurai" fits "Madurai");
- a niche: the campaign is in it;
- a campaign type: the campaign is that type;
- a least budget: the top of the campaign's budget reaches it, the rule
  discovery's `min_budget_paise` uses. A campaign with no budget (barter,
  some commission) fits no alert that names one.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AlertTerms:
    city: str | None
    niche: str | None
    campaign_type: str | None
    min_budget_paise: int | None


@dataclass(frozen=True)
class CampaignTerms:
    cities: Sequence[str]
    niches: Sequence[str]
    campaign_type: str
    budget_max_paise: int | None


def matches(alert: AlertTerms, campaign: CampaignTerms) -> bool:
    """True when every term the alert names holds for the campaign."""
    if alert.city is not None and alert.city.lower() not in {
        city.lower() for city in campaign.cities
    }:
        return False
    if alert.niche is not None and alert.niche not in campaign.niches:
        return False
    if alert.campaign_type is not None and alert.campaign_type != campaign.campaign_type:
        return False
    return alert.min_budget_paise is None or (
        campaign.budget_max_paise is not None
        and campaign.budget_max_paise >= alert.min_budget_paise
    )

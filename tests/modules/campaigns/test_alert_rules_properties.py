"""What holds for every alert and every campaign (item 43, D-130).

The rule is a conjunction of independent terms, each empty term fitting
anything. These properties pin that shape, so a later change cannot make
one term quietly depend on another, or an empty term exclude something.
"""

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from app.core.taxonomy import NICHES
from app.modules.campaigns.alert_rules import AlertTerms, CampaignTerms, matches
from app.modules.campaigns.models import CAMPAIGN_TYPES

CITIES = ["Madurai", "Coimbatore", "Chennai", "Salem", "Tiruchirappalli"]

cities = st.sampled_from(CITIES).flatmap(
    lambda city: st.sampled_from([city, city.lower(), city.upper()])
)
budgets = st.integers(min_value=1, max_value=10_000_000_000)

alerts = st.builds(
    AlertTerms,
    city=st.none() | cities,
    niche=st.none() | st.sampled_from(NICHES),
    campaign_type=st.none() | st.sampled_from(CAMPAIGN_TYPES),
    min_budget_paise=st.none() | budgets,
)
campaigns = st.builds(
    CampaignTerms,
    cities=st.lists(cities, min_size=1, max_size=10),
    niches=st.lists(st.sampled_from(NICHES), min_size=1, max_size=5, unique=True),
    campaign_type=st.sampled_from(CAMPAIGN_TYPES),
    budget_max_paise=st.none() | budgets,
)
EMPTY = AlertTerms(city=None, niche=None, campaign_type=None, min_budget_paise=None)


def single_terms(alert: AlertTerms) -> list[AlertTerms]:
    """The alert taken apart, one named term each."""
    return [
        replace(EMPTY, **{name: value})
        for name, value in vars(alert).items()
        if value is not None
    ]


@given(campaigns)
def test_an_alert_naming_nothing_fits_every_campaign(campaign):
    assert matches(EMPTY, campaign)


@given(alerts, campaigns)
def test_an_alert_fits_exactly_when_each_of_its_terms_does(alert, campaign):
    assert matches(alert, campaign) == all(
        matches(single, campaign) for single in single_terms(alert)
    )


@given(
    alerts,
    campaigns,
    st.sampled_from(["city", "niche", "campaign_type", "min_budget_paise"]),
)
def test_dropping_a_term_never_loses_a_campaign(alert, campaign, name):
    if matches(alert, campaign):
        assert matches(replace(alert, **{name: None}), campaign)


@given(alerts, campaigns)
def test_the_case_of_a_city_never_matters(alert, campaign):
    if alert.city is None:
        return
    for spelling in (alert.city.lower(), alert.city.upper(), alert.city.title()):
        assert matches(replace(alert, city=spelling), campaign) == matches(
            alert, campaign
        )


@given(alerts, campaigns, budgets)
def test_a_bigger_budget_never_loses_an_alert(alert, campaign, extra):
    if matches(alert, campaign) and campaign.budget_max_paise is not None:
        richer = replace(campaign, budget_max_paise=campaign.budget_max_paise + extra)
        assert matches(alert, richer)

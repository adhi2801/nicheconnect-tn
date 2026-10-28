"""Whether a campaign fits an alert (item 43, D-130): the pure rule, every branch."""

import pytest

from app.modules.campaigns.alert_rules import AlertTerms, CampaignTerms, matches

CAMPAIGN = CampaignTerms(
    cities=["Madurai", "Coimbatore"],
    niches=["food", "travel"],
    campaign_type="paid",
    budget_max_paise=1_500_000,
)


def alert(**terms) -> AlertTerms:
    fields = {
        "city": None,
        "niche": None,
        "campaign_type": None,
        "min_budget_paise": None,
    }
    fields.update(terms)
    return AlertTerms(**fields)


@pytest.mark.parametrize(
    ("terms", "fits"),
    [
        ({"city": "Madurai"}, True),
        ({"city": "madurai"}, True),  # a city in any case
        ({"city": "MADURAI"}, True),
        ({"city": "Salem"}, False),
        ({"niche": "travel"}, True),
        ({"niche": "tech"}, False),
        ({"campaign_type": "paid"}, True),
        ({"campaign_type": "barter"}, False),
        ({"min_budget_paise": 1_500_000}, True),  # reaching it exactly fits
        ({"min_budget_paise": 1_500_001}, False),
        ({"min_budget_paise": 100}, True),
        # Every term must hold: one wrong is enough to miss.
        ({"city": "Madurai", "niche": "food", "campaign_type": "paid"}, True),
        ({"city": "Madurai", "niche": "tech"}, False),
        ({"city": "Salem", "niche": "food"}, False),
        ({"niche": "food", "min_budget_paise": 2_000_000}, False),
    ],
)
def test_each_term_named_must_hold(terms, fits):
    assert matches(alert(**terms), CAMPAIGN) is fits


def test_a_campaign_without_a_budget_fits_no_alert_naming_one():
    barter = CampaignTerms(
        cities=["Madurai"], niches=["food"], campaign_type="barter", budget_max_paise=None
    )

    assert matches(alert(min_budget_paise=1), barter) is False
    assert matches(alert(city="Madurai"), barter) is True

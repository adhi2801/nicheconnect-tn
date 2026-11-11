"""A campaign's budget rules, without a database (audit C6).

The same rules the database's `budget_range` and `budget_matches_type`
checks hold; these prove each branch and its boundary, and that the rules
agree with the database's for every input.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.campaigns.budget import budget_problem
from app.modules.campaigns.models import BUDGETED_TYPES, CAMPAIGN_TYPES

amounts = st.one_of(st.none(), st.integers(min_value=1, max_value=10**11))


@pytest.mark.parametrize(
    ("campaign_type", "minimum", "maximum", "rule"),
    [
        ("paid", 500_000, 1_500_000, None),
        ("paid", 500_000, 500_000, None),  # one figure, not a range
        ("paid", 500_000, 499_999, "budget_backwards"),
        ("paid", 500_000, None, "budget_incomplete"),
        ("paid", None, 1_500_000, "budget_incomplete"),
        ("paid", None, None, "budget_required"),
        ("local_business", None, None, "budget_required"),
        ("barter", None, None, None),
        ("barter", 500_000, 1_500_000, "budget_on_barter"),
        ("commission", None, None, None),
        ("commission", 500_000, 1_500_000, None),
    ],
)
def test_each_rule_and_its_boundary(campaign_type, minimum, maximum, rule):
    problem = budget_problem(campaign_type, minimum, maximum)

    assert (None if problem is None else problem[0]) == rule


def test_each_rule_says_how_to_fix_it():
    assert budget_problem("paid", 2, 1) == (
        "budget_backwards",
        "The maximum budget cannot be lower than the minimum",
    )
    assert budget_problem("paid", 1, None) == (
        "budget_incomplete",
        "Give both a minimum and a maximum budget, or neither",
    )
    assert budget_problem("barter", 1, 1) == (
        "budget_on_barter",
        "A barter campaign pays in goods, so it has no budget",
    )
    assert budget_problem("paid", None, None) == (
        "budget_required",
        "Give a budget range for this campaign type",
    )


def database_allows(campaign_type: str, minimum: int | None, maximum: int | None) -> bool:
    """The two CHECKs of `campaign`, written out as Python."""
    budget_range = (minimum is None and maximum is None) or (
        minimum is not None and maximum is not None and 0 < minimum <= maximum
    )
    matches_type = (
        (campaign_type == "barter" and minimum is None)
        or (campaign_type in BUDGETED_TYPES and minimum is not None)
        or campaign_type == "commission"
    )
    return budget_range and matches_type


@given(campaign_type=st.sampled_from(CAMPAIGN_TYPES), minimum=amounts, maximum=amounts)
def test_the_rules_refuse_exactly_what_the_database_refuses(
    campaign_type, minimum, maximum
):
    """So a change passing them can never meet the database's 500."""
    assert (budget_problem(campaign_type, minimum, maximum) is None) == database_allows(
        campaign_type, minimum, maximum
    )

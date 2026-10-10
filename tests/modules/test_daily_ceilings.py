"""Every way of reaching another person has a daily ceiling per account (item 58).

trust-and-safety.md rule 2: a per-minute limit stops a script, not a person
spamming by hand for an hour. These tests read the limits slowapi actually
registered, so a new route that reaches someone, or an edit that drops a
ceiling, fails here rather than in production.
"""

import pytest

from app.core.rate_limit import limiter, per_account
from app.main import app  # noqa: F401 - registers every route's limits
from tests.deal_flow import brand_user, creator_user

# Each route that lets one account reach, judge or read about another.
REACH = (
    "app.modules.campaigns.invitation_router.invite_creator",
    "app.modules.deal_memo.repeat_router.repeat_deal",
    "app.modules.campaigns.application_router.apply_to_campaign",
    "app.modules.campaigns.router.create_campaign",
    "app.modules.auth.report_router.file_report",
    "app.modules.disputes.router.open_dispute",
    "app.modules.disputes.router.add_entry",
    "app.modules.auth.search_router.search_creators",
    "app.modules.matching.router.list_matches_for_campaign",
    "app.modules.matching.router.list_campaigns_for_me",
    "app.modules.payment_status.upi_router.read_pay_details",
)


def limits_of(route: str) -> list:
    return limiter._route_limits[route]


@pytest.mark.parametrize("route", REACH)
def test_it_has_a_daily_ceiling(route):
    granularities = {limit.limit.GRANULARITY.name for limit in limits_of(route)}

    assert "day" in granularities


@pytest.mark.parametrize("route", REACH)
def test_its_ceiling_counts_the_account_not_the_network(route):
    for limit in limits_of(route):
        key = limit.key_func
        assert key is per_account or key is limiter._key_func


def test_the_routes_listed_all_exist():
    # A renamed function would otherwise drop out of the check above.
    assert set(REACH) <= set(limiter._route_limits)


def test_two_people_on_one_network_do_not_share_a_limit(client, db, clock):
    """Until 10 October limits counted the address: an office behind one
    address shared one limit. Now each signed-in account has its own."""
    first, second = creator_user(db, clock), creator_user(db, clock)
    url = "/api/v1/creators/me/availability"

    for _ in range(30):
        assert (
            client.put(
                url, json={"booked_until": None}, headers=first.headers
            ).status_code
            == 200
        )
    assert (
        client.put(url, json={"booked_until": None}, headers=first.headers).status_code
        == 429
    )

    assert (
        client.put(url, json={"booked_until": None}, headers=second.headers).status_code
        == 200
    )


def test_a_brand_sees_the_same_ceiling_from_any_route_twice(client, db, clock):
    brand = brand_user(db, clock)
    # Search's minute limit is 30 now (security.md section 5), not 60.
    answers = [
        client.get("/api/v1/creators", headers=brand.headers).status_code
        for _ in range(31)
    ]

    assert answers[:30] == [200] * 30
    assert answers[30] == 429

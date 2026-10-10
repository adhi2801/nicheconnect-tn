"""A bigger data export costs no more queries than a small one (testing.md section 1).

The export reads every module's records for one account. Each section must
load the other side's handles and titles in one query, never one per row, or
an active brand's export would grow into thousands of statements.
"""

from tests.deal_flow import accepted_memo, brand_user, creator_user
from tests.query_counts import queries_for

URL = "/api/v1/me/export"


def test_a_brand_with_more_deals_costs_no_more_queries(client, db, clock):
    small = brand_user(db, clock)
    accepted_memo(client, small, creator_user(db, clock))
    large = brand_user(db, clock)
    for _ in range(4):
        accepted_memo(client, large, creator_user(db, clock))

    one_deal = queries_for(client, URL, small.headers)
    four_deals = queries_for(client, URL, large.headers)

    assert four_deals == one_deal


def test_a_creator_with_more_deals_costs_no_more_queries(client, db, clock):
    small = creator_user(db, clock)
    accepted_memo(client, brand_user(db, clock), small)
    large = creator_user(db, clock)
    for _ in range(4):
        accepted_memo(client, brand_user(db, clock), large)

    one_deal = queries_for(client, URL, small.headers)
    four_deals = queries_for(client, URL, large.headers)

    assert four_deals == one_deal

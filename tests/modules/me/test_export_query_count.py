"""A bigger data export costs no more queries than a small one (testing.md section 1).

The export reads every module's records for one account, now in the
background job (D-111). Each section must load the other side's handles and
titles in one query, never one per row, or an active brand's export would
grow into thousands of statements.
"""

from app.modules.auth.models.account import Account
from app.modules.me import export_service
from tests.deal_flow import accepted_memo, brand_user, creator_user
from tests.factories import FIXED_NOW
from tests.query_counts import count_queries


def queries_to_build(db, account_id) -> int:
    """How many statements building one account's file runs, as the job does."""
    account = db.get_one(Account, account_id)
    with count_queries() as statements:
        export_service.build_export(db, account, FIXED_NOW)
    return len(statements)


def test_a_brand_with_more_deals_costs_no_more_queries(client, db, clock):
    small = brand_user(db, clock)
    accepted_memo(client, small, creator_user(db, clock))
    large = brand_user(db, clock)
    for _ in range(4):
        accepted_memo(client, large, creator_user(db, clock))

    one_deal = queries_to_build(db, small.account_id)
    four_deals = queries_to_build(db, large.account_id)

    assert four_deals == one_deal


def test_a_creator_with_more_deals_costs_no_more_queries(client, db, clock):
    small = creator_user(db, clock)
    accepted_memo(client, brand_user(db, clock), small)
    large = creator_user(db, clock)
    for _ in range(4):
        accepted_memo(client, brand_user(db, clock), large)

    one_deal = queries_to_build(db, small.account_id)
    four_deals = queries_to_build(db, large.account_id)

    assert four_deals == one_deal

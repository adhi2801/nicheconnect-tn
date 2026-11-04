"""Which deal a row is (R1 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

A row in "My deals" says the campaign and the other side, as the reader
knows them: a brand reads the creator's handle, a creator the brand's name.
On the list and on one deal; a team member reads as the brand.
"""

from sqlalchemy import select

from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from tests.deal_flow import MEMOS_URL, accepted_memo, brand_user, creator_user
from tests.modules.me.test_team_api import join


def test_each_side_reads_the_campaign_and_the_other_side(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    brand_name = db.scalar(select(Brand.name).where(Brand.account_id == brand.account_id))
    handle = db.scalar(
        select(Creator.handle).where(Creator.account_id == creator.account_id)
    )
    member = join(client, db, clock, brand, "finance")

    def row(user) -> dict:
        listed = client.get(f"{MEMOS_URL}/mine", headers=user.headers)
        assert listed.status_code == 200, listed.text
        [found] = [m for m in listed.json()["items"] if m["id"] == memo_id]
        one = client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers).json()
        assert (one["campaign_title"], one["counterparty_name"]) == (
            found["campaign_title"],
            found["counterparty_name"],
        )
        return found

    assert row(creator)["counterparty_name"] == brand_name
    assert row(brand)["counterparty_name"] == handle
    assert row(member)["counterparty_name"] == handle
    assert row(creator)["campaign_title"] == "Pongal sweets launch"

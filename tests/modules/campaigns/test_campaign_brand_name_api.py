"""Who a campaign is from (R1 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

The first question a creator asks of a campaign is "who?": every campaign
read carries its brand's name, in discovery, on the brand's own list and on
one campaign, from one query for the page.
"""

import pytest
from sqlalchemy import select, update

from app.modules.auth.models.brand import Brand
from app.modules.campaigns.models import Campaign
from tests.deal_flow import CAMPAIGNS_URL, brand_user, creator_user
from tests.modules.campaigns.test_invitation_api import open_campaign


@pytest.fixture(autouse=True)
def only_this_tests_campaigns(db) -> None:
    """Discovery reads every open campaign, so a laptop's seeded sample data
    would push these off the first page. Closed inside the test's
    transaction, which is rolled back afterwards."""
    db.execute(update(Campaign).where(Campaign.status == "open").values(status="closed"))


def test_a_creator_sees_whose_campaign_it_is(client, db, clock):
    brand = brand_user(db, clock)
    name = db.scalar(select(Brand.name).where(Brand.account_id == brand.account_id))
    campaign_id = open_campaign(client, brand)
    creator = creator_user(db, clock)

    one = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=creator.headers)
    found = client.get(f"{CAMPAIGNS_URL}/discover", headers=creator.headers)
    mine = client.get(CAMPAIGNS_URL, headers=brand.headers)

    assert one.status_code == 200, one.text
    assert one.json()["brand_name"] == name
    assert {c["id"]: c["brand_name"] for c in found.json()["items"]}[campaign_id] == name
    assert {c["id"]: c["brand_name"] for c in mine.json()["items"]}[campaign_id] == name


def test_each_campaign_names_its_own_brand(client, db, clock):
    first, second = brand_user(db, clock), brand_user(db, clock)
    db.execute(
        Brand.__table__.update()
        .where(Brand.account_id == second.account_id)
        .values(name="Kovai Crafts")
    )
    ids = {
        open_campaign(client, first): "Acme",
        open_campaign(client, second): "Kovai Crafts",
    }

    found = client.get(
        f"{CAMPAIGNS_URL}/discover", headers=creator_user(db, clock).headers
    ).json()["items"]

    names = {c["id"]: c["brand_name"] for c in found if c["id"] in ids}
    assert names == ids

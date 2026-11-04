"""Who applied, in one call (R2 of docs/PROPOSAL_FRONTEND_API_REQUESTS.md).

The rules worth proving: the brand's applicant list names each creator,
with their city, niches and delivery record, never a phone number; the
brand's campaign list counts those who came forward, never an invitation
still waiting, one declined or one withdrawn; nobody else sees a count.
"""

from sqlalchemy import select

from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from tests.deal_flow import CAMPAIGNS_URL, PITCH, brand_user, creator_user
from tests.modules.campaigns.test_invitation_api import invite, open_campaign


def creator_id(db, user) -> str:
    return str(db.scalar(select(Creator.id).where(Creator.account_id == user.account_id)))


def apply(client, campaign_id: str, creator) -> str:
    sent = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert sent.status_code == 201, sent.text
    return sent.json()["id"]


def test_the_brand_sees_who_applied(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    first, second = creator_user(db, clock), creator_user(db, clock)
    apply(client, campaign_id, first)
    apply(client, campaign_id, second)

    listed = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", headers=brand.headers
    )

    assert listed.status_code == 200, listed.text
    rows = {row["creator_id"]: row["creator"] for row in listed.json()["items"]}
    for user in (first, second):
        creator = db.scalars(
            select(Creator).where(Creator.account_id == user.account_id)
        ).one()
        shown = rows[str(creator.id)]
        assert (shown["handle"], shown["display_name"], shown["city"]) == (
            creator.handle,
            creator.display_name,
            creator.city,
        )
        assert shown["niches"] == list(creator.niches)
        assert shown["delivery"]["status"] == "new_creator_no_history_yet"
        phone = db.get_one(Account, user.account_id).phone
        assert phone not in listed.text


def test_the_count_is_those_who_came_forward(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    for _ in range(2):
        apply(client, campaign_id, creator_user(db, clock))
    withdrew = creator_user(db, clock)
    gone = apply(client, campaign_id, withdrew)
    assert (
        client.post(f"/api/v1/applications/{gone}/withdraw", headers=withdrew.headers)
    ).status_code == 200
    waiting = creator_user(db, clock)
    assert invite(client, brand, campaign_id, creator_id(db, waiting)).status_code == 201
    empty = open_campaign(client, brand, title="Diwali boxes")

    mine = client.get(CAMPAIGNS_URL, headers=brand.headers).json()["items"]

    counts = {c["id"]: c["applicant_count"] for c in mine}
    assert counts[campaign_id] == 2
    assert counts[empty] == 0


def test_nobody_but_the_brand_sees_a_count(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, campaign_id, creator_user(db, clock))
    reader = creator_user(db, clock)

    one = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=reader.headers).json()
    found = client.get(f"{CAMPAIGNS_URL}/discover", headers=reader.headers).json()

    assert one["applicant_count"] is None
    assert all(c["applicant_count"] is None for c in found["items"])


def test_another_brand_never_lists_the_applicants(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, campaign_id, creator_user(db, clock))

    other = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        headers=brand_user(db, clock).headers,
    )

    assert other.status_code == 404


def test_the_counted_statuses_are_ones_an_application_can_have():
    from app.modules.campaigns.applicant_service import APPLICANT_STATUSES
    from app.modules.campaigns.models import APPLICATION_STATUSES

    assert set(APPLICANT_STATUSES) <= set(APPLICATION_STATUSES)


def test_nothing_to_list_costs_nothing(db, clock):
    from app.modules.campaigns import applicant_service

    assert applicant_service.read_for_brand(db, [], clock.now) == []
    assert applicant_service.applicant_counts(db, []) == {}


def test_a_campaign_nobody_applied_to_lists_no_one(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)

    listed = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", headers=brand.headers
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []

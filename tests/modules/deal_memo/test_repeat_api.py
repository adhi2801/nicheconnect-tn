"""Work together again: a deal repeated in one tap (D-084).

The journey: an agreed deal, the brand repeats it on another open campaign,
the creator accepts, and the memo is waiting drafted with the earlier terms,
for the brand to date and send. Plus every way it is refused.
"""

import uuid

import pytest
from sqlalchemy import inspect, select

from app.modules.deal_memo import service as deal_memos
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.repeat_router import WRITE_LIMIT
from tests.deal_flow import (
    AGREED_DUE_ON,
    MEMOS_URL,
    NOTIFICATIONS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.modules.campaigns.test_invitation_api import (
    APPLICATIONS_URL,
    answer,
    assert_problem,
    creator_id_of,
    invite,
    open_campaign,
)

TERMS = {
    "usage_rights_days": 90,
    "approval_window_days": 5,
    "payment_due_days": 10,
    "cancellation_fee_paise": 100_000,
    "disclosure_required": True,
    "extra_terms": "Raw footage shared on request.",
}


def repeat(client, brand: User, memo_id: str, campaign_id: str, **body: object):
    return client.post(
        f"{MEMOS_URL}/{memo_id}/repeat",
        json={"campaign_id": campaign_id, **body},
        headers=brand.headers,
    )


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def deal(client, brand, creator) -> str:
    """An agreed deal with every term set, to see each one carried over."""
    return accepted_memo(client, brand, creator, **TERMS)


@pytest.fixture
def next_campaign(client, brand) -> str:
    return open_campaign(client, brand, title="Diwali sweets launch")


def memo_of(client, user: User, application_id: str) -> dict | None:
    memos = client.get(f"{MEMOS_URL}/mine", headers=user.headers).json()["items"]
    return next((m for m in memos if m["application_id"] == application_id), None)


# --- the journey -----------------------------------------------------------------------


def test_a_repeat_is_an_invitation_naming_the_earlier_deal(
    client, db, brand, creator, deal, next_campaign
):
    earlier = client.get(f"{MEMOS_URL}/{deal}", headers=brand.headers).json()

    response = repeat(client, brand, deal, next_campaign, note="Same again for Diwali?")

    assert response.status_code == 201, response.text
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/applications/{body['id']}"
    assert body["origin"] == "invited"
    assert body["status"] == "invited"
    assert body["campaign_id"] == next_campaign
    assert body["creator_id"] == creator_id_of(db, creator)
    assert body["repeat_of_application_id"] == earlier["application_id"]
    assert body["invitation_note"] == "Same again for Diwali?"


def test_the_creator_is_told_it_is_a_repeat(client, brand, creator, deal, next_campaign):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]

    told = client.get(NOTIFICATIONS_URL, headers=creator.headers).json()["items"]
    [received] = [n for n in told if n["application_id"] == invitation]

    assert received["notification_type"] == "invitation_received"
    assert received["details"]["repeat"] is True


def test_accepting_drafts_the_memo_with_the_earlier_terms(
    client, brand, creator, deal, next_campaign
):
    earlier = client.get(f"{MEMOS_URL}/{deal}", headers=brand.headers).json()
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]

    accepted = answer(client, creator, invitation, "accept-invitation")
    drafted = memo_of(client, brand, invitation)

    assert accepted.status_code == 200, accepted.text
    assert drafted is not None
    assert drafted["status"] == "draft"
    for term in deal_memos.REPEATED_TERMS:
        assert drafted[term] == earlier[term], term
    # A new deal has a new date; the brand sets it before sending.
    assert drafted["content_due_on"] is None


def test_the_creator_does_not_see_the_draft_until_it_is_sent(
    client, brand, creator, deal, next_campaign
):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]
    answer(client, creator, invitation, "accept-invitation")

    assert memo_of(client, creator, invitation) is None


def test_the_brand_is_asked_to_send_it_then_the_deal_goes_on(
    client, brand, creator, deal, next_campaign
):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]
    answer(client, creator, invitation, "accept-invitation")
    memo_id = memo_of(client, brand, invitation)["id"]

    [item] = [
        i
        for i in client.get("/api/v1/me/attention", headers=brand.headers).json()["items"]
        if i["kind"] == "draft_memo"
    ]
    dated = client.patch(
        f"{MEMOS_URL}/{memo_id}",
        json={"content_due_on": AGREED_DUE_ON},
        headers=brand.headers,
    )
    sent = client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    agreed = client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)

    assert (item["application_id"], item["memo_id"]) == (invitation, memo_id)
    assert dated.status_code == 200, dated.text
    assert sent.status_code == 200, sent.text
    assert agreed.status_code == 200, agreed.text


def test_without_a_date_the_drafted_memo_cannot_be_sent(
    client, brand, creator, deal, next_campaign
):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]
    answer(client, creator, invitation, "accept-invitation")
    memo_id = memo_of(client, brand, invitation)["id"]

    response = client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)

    assert_problem(response, 409, "memo_needs_due_date")


def test_a_declined_repeat_leaves_no_memo(client, brand, creator, deal, next_campaign):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]

    answer(client, creator, invitation, "decline-invitation", reason="timing")

    assert memo_of(client, brand, invitation) is None


def test_a_plain_invitation_drafts_no_memo(client, db, brand, creator, next_campaign):
    invitation = invite(client, brand, next_campaign, creator_id_of(db, creator)).json()[
        "id"
    ]

    answer(client, creator, invitation, "accept-invitation")

    assert memo_of(client, brand, invitation) is None


def test_a_deal_can_be_repeated_again_and_again(client, brand, creator, deal):
    for title in ("Diwali", "Christmas"):
        campaign = open_campaign(client, brand, title=title)
        invitation = repeat(client, brand, deal, campaign).json()["id"]
        assert answer(client, creator, invitation, "accept-invitation").status_code == 200

    assert memo_of(client, brand, invitation)["status"] == "draft"


# --- refused ---------------------------------------------------------------------------


def test_only_an_agreed_deal_can_be_repeated(client, db, clock, brand, next_campaign):
    other = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, other)
    cancelled = client.post(
        f"{MEMOS_URL}/{memo_id}/cancel",
        json={"reason": "Plans changed."},
        headers=brand.headers,
    )
    assert cancelled.status_code == 200, cancelled.text

    response = repeat(client, brand, memo_id, next_campaign)

    assert_problem(response, 409, "memo_status_conflict")


def test_not_onto_a_campaign_that_is_not_open(client, brand, deal, next_campaign):
    client.post(f"/api/v1/campaigns/{next_campaign}/close", headers=brand.headers)

    response = repeat(client, brand, deal, next_campaign)

    assert_problem(response, 409, "campaign_not_open")


def test_not_onto_another_brands_campaign(client, db, clock, brand, deal):
    stranger = brand_user(db, clock)
    theirs = open_campaign(client, stranger)

    response = repeat(client, brand, deal, theirs)

    assert_problem(response, 404, "campaign_not_found")


def test_not_onto_a_campaign_that_does_not_exist(client, brand, deal):
    response = repeat(client, brand, deal, str(uuid.uuid4()))

    assert_problem(response, 404, "campaign_not_found")


def test_a_paid_deal_cannot_be_repeated_as_barter(client, brand, deal):
    barter = open_campaign(
        client,
        brand,
        campaign_type="barter",
        budget_min_paise=None,
        budget_max_paise=None,
    )

    response = repeat(client, brand, deal, barter)

    assert_problem(response, 409, "barter_memo_has_no_fee")


def test_a_barter_deal_cannot_be_repeated_as_paid(
    client, db, clock, brand, next_campaign
):
    other = creator_user(db, clock)
    barter = open_campaign(
        client,
        brand,
        campaign_type="barter",
        budget_min_paise=None,
        budget_max_paise=None,
    )
    application_id = client.post(
        f"/api/v1/campaigns/{barter}/applications",
        json={"pitch": "I run a Madurai street-food page with 12,000 local followers."},
        headers=other.headers,
    ).json()["id"]
    client.post(f"{APPLICATIONS_URL}/{application_id}/shortlist", headers=brand.headers)
    client.post(f"{APPLICATIONS_URL}/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "1 reel for a sweet box."},
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert (
        client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=other.headers).status_code
        == 200
    )

    response = repeat(client, brand, memo_id, next_campaign)

    assert_problem(response, 409, "paid_memo_needs_fee")


def test_not_when_the_creator_is_already_on_the_campaign(
    client, brand, deal, next_campaign
):
    assert repeat(client, brand, deal, next_campaign).status_code == 201

    response = repeat(client, brand, deal, next_campaign)

    assert_problem(response, 409, "creator_already_on_campaign")


def test_another_brand_cannot_repeat_the_deal(client, db, clock, deal):
    stranger = brand_user(db, clock)
    theirs = open_campaign(client, stranger)

    response = repeat(client, stranger, deal, theirs)

    assert_problem(response, 404, "memo_not_found")


def test_a_creator_cannot_repeat_a_deal(client, creator, deal, next_campaign):
    response = repeat(client, creator, deal, next_campaign)

    assert response.status_code == 403


def test_without_a_token_it_is_refused(client, deal, next_campaign):
    response = client.post(
        f"{MEMOS_URL}/{deal}/repeat", json={"campaign_id": next_campaign}
    )

    assert response.status_code == 401


def test_unknown_fields_are_refused(client, brand, deal, next_campaign):
    response = repeat(client, brand, deal, next_campaign, fee_amount_paise=1)

    assert response.status_code == 422


def test_it_is_rate_limited(client, brand, deal):
    allowed = int(WRITE_LIMIT.split()[0])
    nowhere = str(uuid.uuid4())

    answers = [
        repeat(client, brand, deal, nowhere).status_code for _ in range(allowed + 1)
    ]

    assert answers[:allowed] == [404] * allowed
    assert answers[allowed] == 429


# --- what carries over -------------------------------------------------------------------


def test_every_memo_column_is_carried_over_or_deliberately_not():
    columns = {column.key for column in inspect(DealMemo).columns}

    assert set(deal_memos.REPEATED_TERMS) | set(deal_memos.NOT_REPEATED) == columns
    assert not set(deal_memos.REPEATED_TERMS) & set(deal_memos.NOT_REPEATED)


def test_the_drafted_memo_is_its_own_row(client, db, brand, creator, deal, next_campaign):
    invitation = repeat(client, brand, deal, next_campaign).json()["id"]
    answer(client, creator, invitation, "accept-invitation")

    rows = db.scalars(select(DealMemo).where(DealMemo.id != uuid.UUID(deal))).all()
    drafted = [row for row in rows if str(row.application_id) == invitation]

    assert len(drafted) == 1
    assert drafted[0].sent_at is None and drafted[0].revision_count == 0

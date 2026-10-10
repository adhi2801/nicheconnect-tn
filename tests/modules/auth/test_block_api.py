"""Blocking (item 59): once either side blocks, nothing new starts between them.

Every effect is tested in both directions, because a block works both ways
whoever placed it, and every refusal must read as "not found" so the block
is never revealed to the person blocked.
"""

import uuid

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.modules.auth.block_router import WRITE_LIMIT
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from tests.deal_flow import (
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import FIXED_NOW
from tests.modules.campaigns.test_invitation_api import invite, open_campaign
from tests.query_counts import queries_for

URL = "/api/v1/me/blocks"


def ids(db, brand: User, creator: User) -> tuple[str, str]:
    brand_id = db.scalar(select(Brand.id).where(Brand.account_id == brand.account_id))
    creator_id = db.scalar(
        select(Creator.id).where(Creator.account_id == creator.account_id)
    )
    return str(brand_id), str(creator_id)


def published(db, creator: User) -> None:
    db.execute(
        update(Creator)
        .where(Creator.account_id == creator.account_id)
        .values(passport_published_at=FIXED_NOW)
    )
    db.flush()


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture(params=["creator blocks brand", "brand blocks creator"])
def blocked(request, client, db, brand, creator):
    """A block in place, placed by either side."""
    brand_id, creator_id = ids(db, brand, creator)
    if request.param == "creator blocks brand":
        response = client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)
    else:
        response = client.post(
            URL, json={"creator_id": creator_id}, headers=brand.headers
        )
    assert response.status_code == 201, response.text
    return {"brand_id": brand_id, "creator_id": creator_id}


# --- placing one -----------------------------------------------------------------------


def test_a_creator_blocks_a_brand(client, db, brand, creator):
    brand_id, _ = ids(db, brand, creator)

    response = client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"{URL}/{body['id']}"
    assert (body["brand_id"], body["creator_id"], body["name"]) == (
        brand_id,
        None,
        "Acme",
    )


def test_a_brand_blocks_a_creator(client, db, brand, creator):
    _, creator_id = ids(db, brand, creator)

    body = client.post(URL, json={"creator_id": creator_id}, headers=brand.headers).json()

    assert body["creator_id"] == creator_id
    assert body["name"].startswith("proof")  # the creator's handle


def test_blocking_twice_is_one_block(client, db, brand, creator):
    brand_id, _ = ids(db, brand, creator)

    first = client.post(URL, json={"brand_id": brand_id}, headers=creator.headers).json()
    second = client.post(URL, json={"brand_id": brand_id}, headers=creator.headers).json()

    assert first["id"] == second["id"]
    assert len(client.get(URL, headers=creator.headers).json()["items"]) == 1


@pytest.mark.parametrize(
    "body", [{}, {"brand_id": str(uuid.uuid4()), "creator_id": str(uuid.uuid4())}]
)
def test_name_exactly_one(client, creator, body):
    assert client.post(URL, json=body, headers=creator.headers).status_code == 422


def test_only_the_other_side_can_be_blocked(client, db, brand, creator, clock):
    other_creator = creator_user(db, clock)
    _, other_id = ids(db, brand, other_creator)

    response = client.post(URL, json={"creator_id": other_id}, headers=creator.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "block_target_not_found"


def test_an_unknown_id_is_not_found(client, creator):
    response = client.post(
        URL, json={"brand_id": str(uuid.uuid4())}, headers=creator.headers
    )

    assert response.json()["code"] == "block_target_not_found"


def test_blocking_needs_a_login(client):
    assert client.post(URL, json={"brand_id": str(uuid.uuid4())}).status_code == 401
    assert client.get(URL).status_code == 401


# --- what it stops, in both directions ----------------------------------------------------


def test_no_invitation(client, db, brand, creator, blocked):
    campaign_id = open_campaign(client, brand)

    response = invite(client, brand, campaign_id, blocked["creator_id"])

    assert response.status_code == 404
    assert response.json()["code"] == "creator_not_found"  # never "blocked"


def test_no_repeat_of_an_earlier_deal(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    brand_id, _ = ids(db, brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)
    campaign_id = open_campaign(client, brand, title="Diwali")

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/repeat",
        json={"campaign_id": campaign_id},
        headers=brand.headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "creator_not_found"


def test_no_application(client, brand, creator, blocked):
    campaign_id = open_campaign(client, brand)

    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "campaign_not_found"


def test_out_of_the_brands_search(client, db, brand, creator, blocked):
    published(db, creator)

    found = client.get("/api/v1/creators", headers=brand.headers).json()["items"]

    assert blocked["creator_id"] not in [row["creator_id"] for row in found]


def test_out_of_the_creators_discovery(client, brand, creator, blocked):
    campaign_id = open_campaign(client, brand)

    found = client.get(f"{CAMPAIGNS_URL}/discover", headers=creator.headers).json()[
        "items"
    ]

    assert campaign_id not in [row["id"] for row in found]


def test_others_are_untouched(client, db, clock, brand, creator, blocked):
    other = creator_user(db, clock)
    published(db, other)
    campaign_id = open_campaign(client, brand)
    _, other_id = ids(db, brand, other)

    found = client.get("/api/v1/creators", headers=brand.headers).json()["items"]

    assert other_id in [row["creator_id"] for row in found]
    assert invite(client, brand, campaign_id, other_id).status_code == 201


def test_a_deal_already_agreed_carries_on(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    brand_id, _ = ids(db, brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )

    assert proof.status_code == 201, proof.text


# --- private, and undoable ----------------------------------------------------------------


def test_the_blocked_side_cannot_see_it(client, db, brand, creator):
    brand_id, _ = ids(db, brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    assert client.get(URL, headers=brand.headers).json()["items"] == []
    exported = client.get("/api/v1/me/export", headers=brand.headers).json()["data"]
    assert exported.get("blocks", []) == []


def test_the_blocker_exports_it(client, db, brand, creator):
    brand_id, _ = ids(db, brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    [row] = client.get("/api/v1/me/export", headers=creator.headers).json()["data"][
        "blocks"
    ]

    assert row["blocked_account_id"] == str(brand.account_id)


def test_unblocking_lets_them_reach_each_other_again(client, db, brand, creator):
    _, creator_id = ids(db, brand, creator)
    block_id = client.post(
        URL, json={"creator_id": creator_id}, headers=brand.headers
    ).json()["id"]
    campaign_id = open_campaign(client, brand)

    assert client.delete(f"{URL}/{block_id}", headers=brand.headers).status_code == 204
    assert invite(client, brand, campaign_id, creator_id).status_code == 201


def test_only_the_blocker_can_unblock(client, db, brand, creator):
    brand_id, _ = ids(db, brand, creator)
    block_id = client.post(
        URL, json={"brand_id": brand_id}, headers=creator.headers
    ).json()["id"]

    response = client.delete(f"{URL}/{block_id}", headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "block_not_found"


def test_blocking_is_rate_limited(client, db, clock, creator):
    allowed = int(WRITE_LIMIT.split()[0])
    brands = [ids(db, brand_user(db, clock), creator)[0] for _ in range(allowed + 1)]

    answers = [
        client.post(URL, json={"brand_id": b}, headers=creator.headers).status_code
        for b in brands
    ]

    assert answers[:allowed] == [201] * allowed
    assert answers[allowed] == 429


def test_a_longer_list_costs_no_more_queries(client, db, clock, creator):
    first = ids(db, brand_user(db, clock), creator)[0]
    client.post(URL, json={"brand_id": first}, headers=creator.headers)
    one = queries_for(client, URL, creator.headers)

    for _ in range(4):
        brand_id = ids(db, brand_user(db, clock), creator)[0]
        client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)
    five = queries_for(client, URL, creator.headers)

    assert five == one


# --- the database's own rules -------------------------------------------------------------


def test_nobody_blocks_themselves(db, creator):
    with pytest.raises(IntegrityError, match="ck_account_block_not_oneself"):
        db.execute(
            text(
                "INSERT INTO account_block (blocker_account_id, blocked_account_id) "
                "VALUES (:me, :me)"
            ),
            {"me": creator.account_id},
        )


def test_one_block_per_pair(db, brand, creator):
    insert = text(
        "INSERT INTO account_block (blocker_account_id, blocked_account_id) VALUES (:a, :b)"
    )
    db.execute(insert, {"a": creator.account_id, "b": brand.account_id})

    with pytest.raises(IntegrityError, match="uq_account_block_pair"):
        db.execute(insert, {"a": creator.account_id, "b": brand.account_id})


def test_out_of_the_campaigns_suggested_creators(client, db, brand, creator, blocked):
    published(db, creator)
    campaign_id = open_campaign(client, brand, cities=["Coimbatore"])

    matches = client.get(f"{CAMPAIGNS_URL}/{campaign_id}/matches", headers=brand.headers)

    assert matches.status_code == 200, matches.text
    assert blocked["creator_id"] not in [
        m["creator_id"] for m in matches.json()["matches"]
    ]


def test_out_of_the_creators_suggested_campaigns(client, db, brand, creator, blocked):
    campaign_id = open_campaign(client, brand, cities=["Coimbatore"])

    found = client.get(f"{CAMPAIGNS_URL}/discover/for-me", headers=creator.headers)

    assert found.status_code == 200, found.text
    assert campaign_id not in [m["campaign"]["id"] for m in found.json()["matches"]]


def test_unblocked_they_are_suggested(client, db, brand, creator):
    """The two tests above mean something only if the pair is found unblocked."""
    published(db, creator)
    campaign_id = open_campaign(client, brand, cities=["Coimbatore"])
    handle = db.scalar(
        select(Creator.handle).where(Creator.account_id == creator.account_id)
    )

    matches = client.get(f"{CAMPAIGNS_URL}/{campaign_id}/matches", headers=brand.headers)
    for_me = client.get(f"{CAMPAIGNS_URL}/discover/for-me", headers=creator.headers)

    assert handle in [m["creator"]["handle"] for m in matches.json()["matches"]]
    assert campaign_id in [m["campaign"]["id"] for m in for_me.json()["matches"]]


# --- many brands at once (the bug CI caught on 10 October 2026) ---------------------------
#
# The first version looked up a campaign's brand in a subquery that did not
# correlate to the campaign row, so it read every campaign's brand. With one
# campaign in the database it happened to work; with several, Postgres
# refused it as "more than one row" or the wrong campaigns were hidden. These
# tests have several brands and campaigns, so that shape can never pass.


def test_only_the_blocked_brands_campaigns_leave_discovery(client, db, clock, creator):
    blocked_brand, other_brand = brand_user(db, clock), brand_user(db, clock)
    hidden = [open_campaign(client, blocked_brand, title=f"Hidden {n}") for n in range(2)]
    shown = [open_campaign(client, other_brand, title=f"Shown {n}") for n in range(2)]
    brand_id, _ = ids(db, blocked_brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    response = client.get(f"{CAMPAIGNS_URL}/discover", headers=creator.headers)

    assert response.status_code == 200, response.text
    found = {row["id"] for row in response.json()["items"]}
    assert set(shown) <= found
    assert not set(hidden) & found


def test_only_the_blocked_brands_campaigns_leave_suggestions(client, db, clock, creator):
    blocked_brand, other_brand = brand_user(db, clock), brand_user(db, clock)
    hidden = open_campaign(client, blocked_brand, cities=["Coimbatore"])
    shown = open_campaign(client, other_brand, cities=["Coimbatore"])
    brand_id, _ = ids(db, blocked_brand, creator)
    client.post(URL, json={"brand_id": brand_id}, headers=creator.headers)

    response = client.get(f"{CAMPAIGNS_URL}/discover/for-me", headers=creator.headers)

    assert response.status_code == 200, response.text
    found = {m["campaign"]["id"] for m in response.json()["matches"]}
    assert shown in found and hidden not in found


def test_the_brand_lookup_is_tied_to_each_campaign():
    """The SQL itself: the brand inside the check is the campaign's own."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    from app.modules.auth.blocks import not_blocked_with_brand
    from app.modules.campaigns.models import Campaign

    sql = str(
        select(Campaign.id)
        .where(not_blocked_with_brand(uuid.uuid4(), Campaign.brand_id))
        .compile(dialect=postgresql.dialect())
    )

    assert "brand.id = campaign.brand_id" in sql
    assert "FROM brand, campaign" not in sql

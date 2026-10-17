"""What a withheld item looks like to everyone else, and to its owner (item 52, D-104).

While an item is withheld, everyone but its owner stops seeing it: it leaves
search, matches and discovery, and opening it answers 451. Nothing new can
start from it or reach it. Its owner keeps their account and sees it, and
deals already agreed carry on. Lifting it undoes all of that.

Every test that filters a list has two or more of each thing involved
(testing.md section 2), so a condition tied to the wrong row cannot pass by
luck; and each list's withheld item is proven visible before it is withheld,
so "not in the list" means something.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

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
from tests.factories import FIXED_NOW, create_account
from tests.modules.admin.test_takedowns_api import (
    MINE,
    brand_id_of,
    creator_id_of,
    lift,
    withhold,
)
from tests.modules.campaigns.test_invitation_api import answer, invite, open_campaign
from tests.query_counts import queries_for
from tests.step_up import download_export

DISCOVER = f"{CAMPAIGNS_URL}/discover"
FOR_ME = f"{CAMPAIGNS_URL}/discover/for-me"
SEARCH = "/api/v1/creators"


@pytest.fixture
def admin(db, clock) -> User:
    return User(create_account(db, "admin").id, "admin", clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def published(db, *creators: User) -> None:
    for user in creators:
        db.execute(
            update(Creator)
            .where(Creator.account_id == user.account_id)
            .values(passport_published_at=FIXED_NOW)
        )
    db.flush()


def handle_of(db, user: User) -> str:
    return db.scalar(select(Creator.handle).where(Creator.account_id == user.account_id))


def city_of_its_own() -> str:
    """A city no other test uses, so their rows cannot fill the first page."""
    return f"Testpur {uuid.uuid4().hex[:8]}"


def discovered(client, user: User, city: str) -> set[str]:
    response = client.get(DISCOVER, params={"city": city}, headers=user.headers)
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()["items"]}


def assert_withheld(response) -> None:
    assert response.status_code == 451, response.text
    assert response.json()["code"] == "content_withheld"


def assert_own(response) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "own_content_withheld"


# --- a withheld campaign ----------------------------------------------------------------


def test_a_withheld_campaign_leaves_discovery_and_no_other(
    client, db, clock, admin, creator
):
    one_brand, other_brand = brand_user(db, clock), brand_user(db, clock)
    city = city_of_its_own()
    hidden = open_campaign(client, one_brand, title="Hidden", cities=[city])
    kept = [
        open_campaign(client, one_brand, title="Kept", cities=[city]),
        open_campaign(client, other_brand, title="Other brand", cities=[city]),
    ]
    assert hidden in discovered(client, creator, city)

    withhold(client, admin, "campaign", hidden)

    found = discovered(client, creator, city)
    assert hidden not in found
    assert set(kept) <= found


def test_a_withheld_campaign_answers_451_to_all_but_its_brand(
    client, db, clock, admin, brand, creator
):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)
    other_brand = brand_user(db, clock)

    for stranger in (creator, other_brand):
        assert_withheld(
            client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=stranger.headers)
        )
    own = client.get(f"{CAMPAIGNS_URL}/{campaign_id}", headers=brand.headers)
    assert own.status_code == 200, own.text


def test_a_withheld_draft_is_still_not_found(client, db, admin, brand, creator):
    """451 only for what was public: a draft's existence stays private."""
    draft = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Not yet",
            "description": "A draft nobody has seen.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_000_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "1 reel",
        },
        headers=brand.headers,
    ).json()["id"]
    withhold(client, admin, "campaign", draft)

    response = client.get(f"{CAMPAIGNS_URL}/{draft}", headers=creator.headers)

    assert response.status_code == 404


def test_nobody_applies_to_a_withheld_campaign(client, admin, brand, creator):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)

    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert_withheld(response)


def test_an_invitation_to_it_cannot_be_accepted_and_leaves_attention(
    client, db, admin, brand, creator
):
    campaign_id = open_campaign(client, brand)
    invitation = invite(client, brand, campaign_id, creator_id_of(db, creator)).json()
    waiting = client.get("/api/v1/me/attention", headers=creator.headers).json()
    assert waiting["counts"].get("answer_invitation") == 1

    withhold(client, admin, "campaign", campaign_id)

    assert_withheld(answer(client, creator, invitation["id"], "accept-invitation"))
    after = client.get("/api/v1/me/attention", headers=creator.headers).json()
    assert after["counts"].get("answer_invitation", 0) == 0


def test_its_brand_cannot_invite_to_it(client, db, admin, brand, creator):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)

    assert_own(invite(client, brand, campaign_id, creator_id_of(db, creator)))


def test_a_withheld_campaign_leaves_a_creators_suggestions(
    client, db, clock, admin, creator
):
    one_brand, other_brand = brand_user(db, clock), brand_user(db, clock)
    hidden = open_campaign(client, one_brand, cities=["Coimbatore"])
    kept = open_campaign(client, other_brand, cities=["Coimbatore"])

    def suggested() -> set[str]:
        response = client.get(FOR_ME, headers=creator.headers)
        assert response.status_code == 200, response.text
        return {m["campaign"]["id"] for m in response.json()["matches"]}

    assert hidden in suggested()
    withhold(client, admin, "campaign", hidden)

    assert hidden not in suggested() and kept in suggested()


# --- a withheld brand -------------------------------------------------------------------


def test_a_withheld_brand_takes_every_campaign_with_it_even_later_ones(
    client, db, clock, admin, creator
):
    withheld_brand, other_brand = brand_user(db, clock), brand_user(db, clock)
    city = city_of_its_own()
    before = open_campaign(client, withheld_brand, title="Before", cities=[city])
    kept = open_campaign(client, other_brand, title="Kept", cities=[city])

    withhold(client, admin, "brand", brand_id_of(db, withheld_brand))
    after = open_campaign(client, withheld_brand, title="After", cities=[city])

    found = discovered(client, creator, city)
    assert kept in found
    assert before not in found and after not in found
    assert_withheld(client.get(f"{CAMPAIGNS_URL}/{after}", headers=creator.headers))


def test_a_withheld_brand_cannot_invite(client, db, admin, brand, creator):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "brand", brand_id_of(db, brand))

    assert_own(invite(client, brand, campaign_id, creator_id_of(db, creator)))


# --- a withheld creator -----------------------------------------------------------------


def test_a_withheld_creator_leaves_search_and_no_other(client, db, clock, admin, brand):
    hidden, kept = creator_user(db, clock), creator_user(db, clock)
    published(db, hidden, kept)

    def searched() -> set[str]:
        response = client.get(SEARCH, params={"limit": 100}, headers=brand.headers)
        assert response.status_code == 200, response.text
        return {row["creator_id"] for row in response.json()["items"]}

    assert creator_id_of(db, hidden) in searched()
    withhold(client, admin, "creator", creator_id_of(db, hidden))

    assert creator_id_of(db, hidden) not in searched()
    assert creator_id_of(db, kept) in searched()


def test_a_withheld_creator_leaves_a_campaigns_matches(client, db, clock, admin, brand):
    hidden, kept = creator_user(db, clock), creator_user(db, clock)
    published(db, hidden, kept)
    campaign_id = open_campaign(client, brand, cities=["Coimbatore"])

    def matched() -> set[str]:
        response = client.get(
            f"{CAMPAIGNS_URL}/{campaign_id}/matches", headers=brand.headers
        )
        assert response.status_code == 200, response.text
        return {m["creator"]["handle"] for m in response.json()["matches"]}

    assert handle_of(db, hidden) in matched()
    withhold(client, admin, "creator", creator_id_of(db, hidden))

    assert handle_of(db, hidden) not in matched()
    assert handle_of(db, kept) in matched()


def test_a_withheld_passport_answers_451_and_is_never_cached(client, db, admin, creator):
    published(db, creator)
    url = f"/api/v1/creators/by-handle/{handle_of(db, creator)}"
    assert client.get(url).status_code == 200

    withhold(client, admin, "creator", creator_id_of(db, creator))
    response = client.get(url)

    assert_withheld(response)
    assert "public" not in response.headers.get("Cache-Control", "")
    assert "ETag" not in response.headers


def test_an_unpublished_withheld_passport_is_still_not_found(client, db, admin, creator):
    """The Passport's own rule comes first: unpublished reads as no such handle."""
    withhold(client, admin, "creator", creator_id_of(db, creator))

    response = client.get(f"/api/v1/creators/by-handle/{handle_of(db, creator)}")

    assert response.status_code == 404


def test_the_media_kit_answers_451_to_brands_but_not_to_its_creator(
    client, db, admin, brand, creator
):
    url = f"/api/v1/creators/{creator_id_of(db, creator)}/media-kit"
    withhold(client, admin, "creator", creator_id_of(db, creator))

    assert_withheld(client.get(url, headers=brand.headers))
    assert client.get(url, headers=creator.headers).status_code == 200


def test_nobody_invites_a_withheld_creator(client, db, admin, brand, creator):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "creator", creator_id_of(db, creator))

    assert_withheld(invite(client, brand, campaign_id, creator_id_of(db, creator)))


def test_a_withheld_creator_cannot_apply(client, db, admin, brand, creator):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "creator", creator_id_of(db, creator))

    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )

    assert_own(response)


def test_a_withheld_creator_cannot_accept_an_invitation(
    client, db, admin, brand, creator
):
    campaign_id = open_campaign(client, brand)
    invitation = invite(client, brand, campaign_id, creator_id_of(db, creator)).json()
    withhold(client, admin, "creator", creator_id_of(db, creator))

    assert_own(answer(client, creator, invitation["id"], "accept-invitation"))


def test_nobody_repeats_a_deal_with_a_withheld_creator(client, db, clock, admin):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    campaign_id = open_campaign(client, brand, title="Diwali")
    withhold(client, admin, "creator", creator_id_of(db, creator))

    response = client.post(
        f"{MEMOS_URL}/{memo_id}/repeat",
        json={"campaign_id": campaign_id},
        headers=brand.headers,
    )

    assert_withheld(response)


# --- what carries on --------------------------------------------------------------------


def test_a_deal_already_agreed_carries_on(client, db, clock, admin):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    withhold(client, admin, "creator", creator_id_of(db, creator))
    withhold(client, admin, "brand", brand_id_of(db, brand))

    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    memo = client.get(f"{MEMOS_URL}/{memo_id}", headers=brand.headers)

    assert proof.status_code == 201, proof.text
    assert memo.status_code == 200, memo.text


def test_the_owner_keeps_their_account(client, db, admin, brand):
    withhold(client, admin, "brand", brand_id_of(db, brand))

    response = client.get(CAMPAIGNS_URL, headers=brand.headers)

    assert response.status_code == 200, response.text


# --- lifting ----------------------------------------------------------------------------


def test_lifting_brings_everything_back(client, db, clock, admin, brand, creator):
    city = city_of_its_own()
    campaign_id = open_campaign(client, brand, cities=[city])
    published(db, creator)
    passport = f"/api/v1/creators/by-handle/{handle_of(db, creator)}"
    on_campaign = withhold(client, admin, "campaign", campaign_id).json()
    on_creator = withhold(client, admin, "creator", creator_id_of(db, creator)).json()

    lift(client, admin, on_campaign["id"])
    lift(client, admin, on_creator["id"])

    assert campaign_id in discovered(client, creator, city)
    assert client.get(passport).status_code == 200
    assert (
        invite(client, brand, campaign_id, creator_id_of(db, creator)).status_code == 201
    )


# --- the owner's own list, and their export ---------------------------------------------


def test_the_owner_sees_what_is_withheld_and_why(client, db, admin, brand, clock):
    campaign_id = open_campaign(client, brand)
    takedown = withhold(client, admin, "campaign", campaign_id).json()

    [row] = client.get(MINE, headers=brand.headers).json()["items"]

    assert row == {
        "id": takedown["id"],
        "subject_kind": "campaign",
        "subject_id": campaign_id,
        "basis": "court_order",
        "issued_by": "High Court of Madras",
        "order_reference": "WP 1012 of 2026",
        "legal_provision": "IT Act 2000, section 79(3)(b)",
        "reference_sealed": False,
        "withheld_at": takedown["withheld_at"],
        "lifted_at": None,
    }


def test_a_sealed_order_shows_only_that_it_exists(client, db, admin, brand):
    withhold(
        client, admin, "campaign", open_campaign(client, brand), reference_sealed=True
    )

    [row] = client.get(MINE, headers=brand.headers).json()["items"]
    [exported] = download_export(client, brand.headers).json()["data"]["takedowns"]

    assert row["reference_sealed"] is True
    for shown in (row, exported):
        assert (
            shown["issued_by"],
            shown["order_reference"],
            shown["legal_provision"],
        ) == (
            None,
            None,
            None,
        )
    assert "WP 1012" not in str(exported) and "High Court" not in str(exported)


def test_the_export_holds_the_preserved_text(client, db, admin, brand):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)

    [exported] = download_export(client, brand.headers).json()["data"]["takedowns"]

    assert exported["subject_id"] == campaign_id
    assert exported["preserved"]["title"] == "Pongal sweets launch"
    assert exported["issued_by"] == "High Court of Madras"
    assert "withheld_by_account_id" not in exported


def test_nobody_else_sees_someone_s_takedowns(client, db, clock, admin, brand, creator):
    withhold(client, admin, "campaign", open_campaign(client, brand))

    assert client.get(MINE, headers=creator.headers).json()["items"] == []
    assert client.get(MINE).status_code == 401


def test_the_owner_s_list_pages_without_gaps_or_repeats(client, admin, brand, clock):
    made = []
    for _ in range(5):
        made.append(
            withhold(client, admin, "campaign", open_campaign(client, brand)).json()["id"]
        )
        clock.advance(timedelta(seconds=1))

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get(MINE, params=params, headers=brand.headers).json()
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(made))


def test_the_owner_s_longer_list_costs_no_more_queries(client, admin, brand):
    withhold(client, admin, "campaign", open_campaign(client, brand))
    one = queries_for(client, MINE, brand.headers)

    for _ in range(4):
        withhold(client, admin, "campaign", open_campaign(client, brand))
    five = queries_for(client, MINE, brand.headers)

    assert five == one


def test_discovery_costs_no_more_queries_with_items_withheld(
    client, db, clock, admin, creator
):
    """The withheld check is a condition in the one query, never a query per row."""
    brand = brand_user(db, clock)
    city = city_of_its_own()
    for n in range(3):
        open_campaign(client, brand, title=f"Kept {n}", cities=[city])
    url = f"{DISCOVER}?city={city.replace(' ', '%20')}"
    before = queries_for(client, url, creator.headers)

    for n in range(3):
        withhold(
            client,
            admin,
            "campaign",
            open_campaign(client, brand, title=f"Gone {n}", cities=[city]),
        )
    after = queries_for(client, url, creator.headers)

    assert after == before


def applied(client, brand: User, creator: User) -> str:
    campaign_id = open_campaign(client, brand)
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize("action", ["shortlist", "accept"])
def test_a_brand_cannot_move_towards_a_deal_with_a_withheld_creator(
    client, db, admin, brand, creator, action
):
    application_id = applied(client, brand, creator)
    if action == "accept":
        client.post(
            f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers
        )
    withhold(client, admin, "creator", creator_id_of(db, creator))

    response = client.post(
        f"/api/v1/applications/{application_id}/{action}", headers=brand.headers
    )

    assert_withheld(response)


def test_a_withheld_brand_cannot_move_towards_a_deal(client, db, admin, brand, creator):
    application_id = applied(client, brand, creator)
    withhold(client, admin, "brand", brand_id_of(db, brand))

    response = client.post(
        f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers
    )

    assert_own(response)


def test_saying_no_stays_open_to_both(client, db, admin, brand, creator):
    """A takedown never traps anyone in a pending application."""
    application_id = applied(client, brand, creator)
    withhold(client, admin, "creator", creator_id_of(db, creator))

    response = client.post(
        f"/api/v1/applications/{application_id}/reject",
        json={"reason": "timing"},
        headers=brand.headers,
    )

    assert response.status_code == 200, response.text

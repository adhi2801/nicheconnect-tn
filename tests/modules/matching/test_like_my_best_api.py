"""More like the creators who delivered for you (item 65, D-133).

The rules worth proving: anchors are only creators who finished a deal with
this brand; the ranking is closeness to them, and each result names its
nearest; nobody the brand could not find in search, nor already dealt
with, nor its own other side, is shown. Vectors here are hand-made, so
"closest" is known exactly.
"""

import hashlib
import math
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.matching.models import EMBEDDING_DIMENSIONS, CreatorEmbedding
from app.modules.matching.similar_router import SIMILAR_LIMIT
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
    finish_deal,
)
from tests.factories import build_creator, create_account
from tests.modules.admin.test_takedowns_api import creator_id_of
from tests.modules.matching.test_creator_lists_api import HIDINGS, findable
from tests.query_counts import queries_for

URL = "/api/v1/creators/like-my-best"


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    """A laptop's seeded creators would land in these rankings. Hidden inside
    the test's transaction, which is rolled back afterwards."""
    db.execute(update(Creator).values(passport_published_at=None))


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def vector(angle_degrees: float) -> list[float]:
    """A unit vector in the plane of the first two axes, at this angle from the first."""
    v = [0.0] * EMBEDDING_DIMENSIONS
    v[0] = math.cos(math.radians(angle_degrees))
    v[1] = math.sin(math.radians(angle_degrees))
    return v


def embed(db, user: User, angle: float) -> None:
    db.add(
        CreatorEmbedding(
            creator_id=uuid.UUID(creator_id_of(db, user)),
            embedding=vector(angle),
            source_hash=hashlib.sha256(str(angle).encode()).hexdigest(),
            model="test",
        )
    )
    db.flush()


def candidate(db, clock, angle: float) -> tuple[User, str]:
    user, creator_id = findable(db, clock)
    embed(db, user, angle)
    return user, creator_id


def anchor(client, db, clock, brand: User, angle: float) -> User:
    """A creator who finished a paid deal with the brand: paid and confirmed."""
    user = creator_user(db, clock)
    embed(db, user, angle)
    finish_deal(client, brand, user, accepted_memo(client, brand, user))
    return user


def ranked(client, brand: User, **params) -> dict:
    response = client.get(URL, params=params, headers=brand.headers)
    assert response.status_code == 200, response.text
    return response.json()


def ids(body: dict) -> list[str]:
    return [item["creator_id"] for item in body["items"]]


def test_with_no_finished_deal_there_is_nothing_to_go_on(client, db, clock, brand):
    candidate(db, clock, 0)

    assert ranked(client, brand) == {"based_on": 0, "items": [], "next_cursor": None}


def test_creators_come_closest_first_each_naming_its_nearest(client, db, clock, brand):
    best = anchor(client, db, clock, brand, 0)
    far = candidate(db, clock, 80)[1]
    near = candidate(db, clock, 5)[1]
    middle = candidate(db, clock, 40)[1]

    body = ranked(client, brand)

    assert body["based_on"] == 1
    assert ids(body) == [near, middle, far]
    similarities = [item["similarity"] for item in body["items"]]
    assert similarities == sorted(similarities, reverse=True)
    assert body["items"][0]["similarity"] == pytest.approx(
        math.cos(math.radians(5)), abs=1e-3
    )
    assert {item["closest_to"]["creator_id"] for item in body["items"]} == {
        creator_id_of(db, best)
    }


def test_each_result_names_the_anchor_it_is_closest_to(client, db, clock, brand):
    first = anchor(client, db, clock, brand, 0)
    second = anchor(client, db, clock, brand, 90)
    by_first = candidate(db, clock, 10)[1]
    by_second = candidate(db, clock, 85)[1]

    body = ranked(client, brand)

    nearest = {i["creator_id"]: i["closest_to"]["creator_id"] for i in body["items"]}
    assert nearest == {
        by_first: creator_id_of(db, first),
        by_second: creator_id_of(db, second),
    }
    assert body["based_on"] == 2


def test_only_a_finished_deal_makes_an_anchor(client, db, clock, brand):
    # Agreed but not yet paid: not an anchor, and already dealt with.
    unpaid = creator_user(db, clock)
    embed(db, unpaid, 0)
    accepted_memo(client, brand, unpaid)

    assert ranked(client, brand)["based_on"] == 0


def test_a_barter_deal_with_its_work_approved_is_an_anchor(client, db, clock, brand):
    from tests.modules.deal_memo.test_barter_shipment_api import barter_memo

    user = creator_user(db, clock)
    embed(db, user, 0)
    memo_id = barter_memo(client, brand, user)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=user.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=brand.headers)
    shown = candidate(db, clock, 10)[1]

    body = ranked(client, brand)

    assert body["based_on"] == 1
    assert ids(body) == [shown]


def test_another_brands_deals_make_no_anchor_here(client, db, clock, brand):
    other = brand_user(db, clock)
    anchor(client, db, clock, other, 0)
    candidate(db, clock, 5)

    assert ranked(client, brand)["based_on"] == 0
    assert ranked(client, other)["based_on"] == 1


def test_no_creator_already_dealt_with_is_shown(client, db, clock, brand):
    best = anchor(client, db, clock, brand, 0)
    ongoing_user, ongoing = candidate(db, clock, 3)
    accepted_memo(client, brand, ongoing_user)
    fresh = candidate(db, clock, 6)[1]

    shown = ids(ranked(client, brand))

    assert shown == [fresh]
    assert creator_id_of(db, best) not in shown and ongoing not in shown


@pytest.mark.parametrize("how", HIDINGS)
def test_a_creator_search_would_not_show_is_not_shown(client, db, clock, brand, how):
    anchor(client, db, clock, brand, 0)
    hidden_user, hidden = candidate(db, clock, 5)
    kept = candidate(db, clock, 10)[1]
    assert ids(ranked(client, brand)) == [hidden, kept]

    HIDINGS[how](client, db, hidden_user, brand)

    assert ids(ranked(client, brand)) == [kept]


def test_the_brands_own_other_side_is_never_shown(client, db, clock, brand):
    anchor(client, db, clock, brand, 0)
    phone = db.get_one(Account, brand.account_id).phone
    account = create_account(db, "creator", phone=phone)
    db.add(build_creator(db, handle=f"own{uuid.uuid4().hex[:10]}", account_id=account.id))
    db.flush()
    own = User(account.id, "creator", clock)
    db.execute(
        update(Creator)
        .where(Creator.account_id == own.account_id)
        .values(passport_published_at=brand.clock.now)
    )
    embed(db, own, 1)
    kept = candidate(db, clock, 10)[1]

    assert ids(ranked(client, brand)) == [kept]


def test_a_creator_with_no_embedding_yet_is_not_shown(client, db, clock, brand):
    anchor(client, db, clock, brand, 0)
    findable(db, clock)  # published, but no vector yet
    kept = candidate(db, clock, 10)[1]

    assert ids(ranked(client, brand)) == [kept]


def test_each_result_carries_its_own_delivery_record(client, db, clock, brand):
    """Two results, one with a deal overdue elsewhere, so a record tied to the
    wrong creator cannot pass by luck."""
    anchor(client, db, clock, brand, 0)
    late_user, late = candidate(db, clock, 5)
    _, fresh = candidate(db, clock, 10)
    due = (clock.now + timedelta(days=3)).date().isoformat()
    accepted_memo(client, brand_user(db, clock), late_user, content_due_on=due)
    clock.advance(timedelta(days=5))

    body = ranked(client, brand)

    by_id = {item["creator_id"]: item["delivery"] for item in body["items"]}
    assert (by_id[late]["currently_overdue"], by_id[fresh]["currently_overdue"]) == (1, 0)
    for creator_id in (late, fresh):
        record = client.get(
            f"/api/v1/creators/{creator_id}/delivery-record", headers=brand.headers
        )
        assert by_id[creator_id] == record.json()


def test_pages_have_no_gaps_or_repeats(client, db, clock, brand):
    anchor(client, db, clock, brand, 0)
    expected = [candidate(db, clock, angle)[1] for angle in (5, 10, 15, 20, 25)]

    seen, cursor = [], None
    while True:
        body = ranked(client, brand, limit=2, **({"cursor": cursor} if cursor else {}))
        seen += ids(body)
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == expected


def test_equal_closeness_pages_by_id_without_repeats(client, db, clock, brand):
    anchor(client, db, clock, brand, 0)
    twins = sorted(candidate(db, clock, 10)[1] for _ in range(3))

    seen, cursor = [], None
    while True:
        body = ranked(client, brand, limit=1, **({"cursor": cursor} if cursor else {}))
        seen += ids(body)
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert seen == twins


def test_a_long_page_costs_the_same_queries_as_a_short_one(client, db, clock):
    short, long = brand_user(db, clock), brand_user(db, clock)
    anchor(client, db, clock, short, 0)
    anchor(client, db, clock, long, 0)
    anchor(client, db, clock, long, 30)
    candidate(db, clock, 5)
    for angle in (6, 7, 8, 9, 10):
        candidate(db, clock, angle)
    ranked(client, short)  # the first read after a commit opens the test's savepoint

    assert queries_for(client, URL, long.headers, {"limit": 6}) == queries_for(
        client, URL, short.headers, {"limit": 1}
    )


def test_creators_are_not_shown_creators(client, db, clock):
    assert client.get(URL, headers=creator_user(db, clock).headers).status_code == 403


def test_it_needs_a_login(client):
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"cursor": "nope"}])
def test_bad_parameters_are_refused(client, db, clock, brand, params):
    anchor(client, db, clock, brand, 0)

    assert client.get(URL, params=params, headers=brand.headers).status_code == 422


def test_it_is_rate_limited_as_search_is(client, brand):
    for _ in range(int(SIMILAR_LIMIT.split()[0])):
        assert client.get(URL, headers=brand.headers).status_code == 200

    assert client.get(URL, headers=brand.headers).status_code == 429

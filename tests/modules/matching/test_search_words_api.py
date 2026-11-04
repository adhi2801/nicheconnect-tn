"""A creator search written in plain words (item 64, D-158).

The rules worth proving over HTTP: the filters it answers are ones search
takes, and finds what the words meant; places are spelled as the creators a
brand could find wrote them, so a blocked creator's city shapes nothing; a
team member reads as the brand; brands only; one query, however many
creators. The reading rules themselves are `test_words_reader.py`'s.
"""

from datetime import timedelta

import pytest
from sqlalchemy import update

from app.core.clock import india_date
from app.modules.auth.models.creator import Creator
from app.modules.matching import search_router, words_reader
from app.modules.matching.search_router import SEARCH_LIMIT
from app.modules.safety.models import AccountBlock
from tests.deal_flow import brand_user, creator_user
from tests.modules.matching.test_creator_search_api import creator, search
from tests.modules.me.test_team_api import join
from tests.query_counts import queries_for

URL = "/api/v1/creators/search-reading"
SENTENCE = "Café creators in Coimbatore, 5k to 20k followers on Instagram"


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    """Places come from every findable creator, so a laptop's seeded sample
    data would add its own. Hidden inside the test's rolled-back transaction."""
    db.execute(update(Creator).values(passport_published_at=None))


def reading(client, user, words: str) -> dict:
    response = client.get(URL, params={"words": words}, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_words_become_filters_and_say_where_each_came_from(client, db, clock):
    brand = brand_user(db, clock)

    body = reading(client, brand, SENTENCE)

    assert body["filters"] == {
        "q": None,
        "niche": "food",
        "city": "Coimbatore",
        "platform": "instagram",
        "min_followers": 5000,
        "max_followers": 20000,
        "max_price_paise": None,
        "format": None,
        "available_on": None,
    }
    assert [(p["words"], p["filter"]) for p in body["read_as"]] == [
        ("Café", "niche"),
        ("in Coimbatore", "city"),
        ("5k to 20k followers", "min_followers"),
        ("5k to 20k followers", "max_followers"),
        ("on Instagram", "platform"),
    ]
    assert body["unread"] == [] and body["notes"] == []


def test_what_it_reads_finds_what_was_meant(client, db, clock):
    brand = brand_user(db, clock)
    wanted = creator(db, city="Coimbatore", channels={"instagram": 12_000})
    creator(db, city="Coimbatore", channels={"instagram": 90_000})
    creator(db, city="Madurai", channels={"instagram": 12_000})
    creator(db, city="Coimbatore", niches=("fashion",), channels={"instagram": 12_000})

    filters = reading(client, brand, SENTENCE)["filters"]
    found = search(client, brand, **{k: v for k, v in filters.items() if v is not None})

    assert [c["creator_id"] for c in found["items"]] == [str(wanted.id)]


def test_a_place_is_spelled_as_most_creators_there_wrote_it(client, db, clock):
    brand = brand_user(db, clock)
    for _ in range(2):
        creator(db, city="Trichy")
    creator(db, city="Tiruchirappalli")

    body = reading(client, brand, "food creators in Tiruchirappalli")

    assert body["filters"]["city"] == "Trichy"
    assert body["read_as"][1] == {
        "words": "in Tiruchirappalli",
        "filter": "city",
        "value": "Trichy",
    }


def test_a_district_nobody_has_typed_yet_is_still_a_place(client, db, clock):
    body = reading(client, brand_user(db, clock), "travel creators in Kovai")

    assert body["filters"]["city"] == "Coimbatore"


def test_a_city_only_a_creator_wrote_is_a_place_too(client, db, clock):
    creator(db, city="Sathyamangalam")

    body = reading(client, brand_user(db, clock), "creators in sathyamangalam")

    assert body["filters"]["city"] == "Sathyamangalam"


def test_a_blocked_creator_s_city_shapes_nothing(client, db, clock):
    """Two Trichy to one Tiruchirappalli, but both Trichy creators blocked the brand."""
    brand = brand_user(db, clock)
    for _ in range(2):
        hidden = creator(db, city="Trichy")
        db.add(
            AccountBlock(
                blocker_account_id=hidden.account_id,
                blocked_account_id=brand.account_id,
            )
        )
    creator(db, city="Tiruchirappalli")
    db.flush()

    body = reading(client, brand, "creators in Trichy")

    assert body["filters"]["city"] == "Tiruchirappalli"


def test_a_team_member_reads_places_as_the_brand(client, db, clock):
    owner = brand_user(db, clock)
    member = join(client, db, clock, owner, "finance")
    hidden = creator(db, city="Sathyamangalam")
    db.add(
        AccountBlock(
            blocker_account_id=hidden.account_id, blocked_account_id=owner.account_id
        )
    )
    db.flush()

    body = reading(client, member, "creators in Sathyamangalam")

    assert body["filters"]["city"] is None
    assert body["unread"] == ["Sathyamangalam"]


def test_a_date_without_a_year_is_the_next_one(client, db, clock):
    today = india_date(clock.now)
    yesterday = today - timedelta(days=1)

    body = reading(
        client, brand_user(db, clock), f"free on {yesterday.day} {yesterday:%B}"
    )

    assert (
        body["filters"]["available_on"]
        == yesterday.replace(year=today.year + 1).isoformat()
    )


def test_what_it_cannot_read_comes_back_with_the_reason(client, db, clock):
    body = reading(client, brand_user(db, clock), "micro influencers free in December")

    assert body["filters"] == dict.fromkeys(body["filters"])
    assert body["unread"] == ["micro influencers", "free in December"]
    assert body["notes"] == [
        {"code": "tier_needs_numbers", "words": "micro influencers"},
        {"code": "a_month_is_not_a_day", "words": "free in December"},
    ]


@pytest.mark.parametrize("words", ["", "x", "x" * 201])
def test_the_words_have_limits(client, db, clock, words):
    response = client.get(
        URL, params={"words": words}, headers=brand_user(db, clock).headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_words_are_required(client, db, clock):
    assert client.get(URL, headers=brand_user(db, clock).headers).status_code == 422


def test_it_needs_a_login(client):
    assert client.get(URL, params={"words": SENTENCE}).status_code == 401


def test_creators_do_not_search_for_creators(client, db, clock):
    response = client.get(
        URL, params={"words": SENTENCE}, headers=creator_user(db, clock).headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_it_is_rate_limited_as_search_is(client, db, clock):
    brand = brand_user(db, clock)
    for _ in range(int(SEARCH_LIMIT.split()[0])):
        assert (
            client.get(URL, params={"words": "food"}, headers=brand.headers).status_code
            == 200
        )

    assert (
        client.get(URL, params={"words": "food"}, headers=brand.headers).status_code
        == 429
    )


def test_one_query_however_many_creators_and_places(client, db, clock):
    brand = brand_user(db, clock)
    creator(db, city="Madurai")
    creator(db, city="Salem")
    few = queries_for(client, URL, brand.headers, {"words": SENTENCE})
    for city in ("Erode", "Karur", "Theni", "Vellore", "Hosur", "Ooty", "Salem"):
        creator(db, city=city)
        creator(db, city=city)

    assert queries_for(client, URL, brand.headers, {"words": SENTENCE}) == few


def test_the_reader_keeps_to_the_search_route_s_limits():
    """The reader repeats them so it needs nothing from HTTP; these tie the copies."""
    assert words_reader.MAX_FOLLOWERS == search_router.MAX_FOLLOWERS
    assert words_reader.MAX_PRICE_PAISE == search_router.MAX_PRICE_PAISE

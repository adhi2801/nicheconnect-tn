"""Brands searching for creators.

The rules worth proving are the ones that keep answers true: only creators
who chose to be found appear, and combined filters hold on one channel or one
package, never stitched together from several.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import event, update

from app.core.taxonomy import CURRENCY
from app.db.session import engine
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.search_router import READ_LIMIT
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import FIXED_NOW, build_creator

URL = "/api/v1/creators"
FIELDS = {
    "creator_id",
    "handle",
    "display_name",
    "city",
    "niches",
    "bio",
    "member_since",
    "channels",
    "from_price_paise",
    "currency",
    "booked_until",
}


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    """Search reads every published creator, so a laptop's seeded sample
    data would land in these results. Hidden inside the test's transaction,
    which is rolled back afterwards."""
    db.execute(update(Creator).values(passport_published_at=None))


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def creator(
    db,
    *,
    handle: str | None = None,
    city: str = "Madurai",
    niches: tuple[str, ...] = ("food",),
    bio: str | None = "Street food across Tamil Nadu.",
    published: bool = True,
    age_minutes: int = 0,
    channels: dict[str, int] | None = None,
    packages: list[tuple[str, str, int]] | None = None,
) -> Creator:
    """A creator with channels {platform: followers} and packages [(platform, format, paise)]."""
    row = build_creator(
        db,
        handle=handle or f"s{uuid.uuid4().hex[:12]}",
        display_name=f"Creator {handle or 'x'}",
        city=city,
        niches=list(niches),
        bio=bio,
        passport_published_at=FIXED_NOW if published else None,
        created_at=FIXED_NOW - timedelta(minutes=age_minutes),
        updated_at=FIXED_NOW,
    )
    db.add(row)
    db.flush()
    for platform, followers in (channels or {}).items():
        db.add(
            CreatorChannel(
                creator_id=row.id,
                platform=platform,
                profile_url=f"https://{platform}.com/{row.handle}",
                followers=followers,
                figures_as_of=FIXED_NOW.date(),
            )
        )
    for position, (platform, package_format, price) in enumerate(packages or []):
        db.add(
            CreatorPackage(
                creator_id=row.id,
                platform=platform,
                format=package_format,
                title=f"{package_format} {position}",
                price_paise=price,
                currency=CURRENCY,
                delivery_days=5,
                position=position,
            )
        )
    db.flush()
    return row


def search(client, user: User, **params) -> dict:
    response = client.get(URL, params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def handles(body: dict) -> list[str]:
    return [item["handle"] for item in body["items"]]


@contextmanager
def count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


# --- who can be found ---------------------------------------------------------------


def test_only_creators_who_published_their_passport_appear(client, db, brand):
    creator(db, handle="published.one")
    creator(db, handle="hidden.one", published=False)

    assert handles(search(client, brand)) == ["published.one"]


def test_a_result_carries_exactly_the_agreed_fields(client, db, brand):
    creator(
        db,
        handle="priya.eats",
        channels={"instagram": 24_000},
        packages=[("instagram", "reel", 800_000)],
    )

    [item] = search(client, brand)["items"]

    assert set(item) == FIELDS
    assert item["channels"] == [
        {
            "platform": "instagram",
            "followers": 24_000,
            "figures_as_of": FIXED_NOW.date().isoformat(),
            "self_reported": True,
        }
    ]
    assert item["from_price_paise"] == 800_000
    assert item["currency"] == CURRENCY


def test_nothing_private_is_in_a_result(client, db, brand):
    row = creator(db, handle="priya.eats")

    text = client.get(URL, headers=brand.headers).text

    assert str(row.account_id) not in text
    for forbidden in ("phone", "account_id", "passport_published_at", "email"):
        assert forbidden not in text


# --- the filters ---------------------------------------------------------------------


def test_words_match_handle_name_or_bio_in_any_case(client, db, brand):
    creator(db, handle="priya.eats", bio="Street food.")
    creator(db, handle="arun.fit", bio="Gym routines and KUZHAMBU recipes.")
    creator(db, handle="meena.style", bio="Silk sarees.")

    assert sorted(handles(search(client, brand, q="kuzhambu"))) == ["arun.fit"]
    assert sorted(handles(search(client, brand, q="PRIYA"))) == ["priya.eats"]


def test_wildcards_in_the_words_are_taken_literally(client, db, brand):
    creator(db, handle="priya.eats", bio="100% vegetarian.")
    creator(db, handle="arun.fit", bio="100 percent effort.")

    assert handles(search(client, brand, q="100%")) == ["priya.eats"]


def test_niche_and_city(client, db, brand):
    creator(db, handle="food.madurai", niches=("food",), city="Madurai")
    creator(db, handle="food.chennai", niches=("food",), city="Chennai")
    creator(db, handle="fitness.madurai", niches=("fitness",), city="Madurai")

    assert handles(search(client, brand, niche="food", city="madurai")) == [
        "food.madurai"
    ]


def test_an_audience_filter_holds_on_one_channel(client, db, brand):
    """5,000 on Instagram and 50,000 on YouTube is not 10,000 on Instagram."""
    creator(db, handle="small.insta", channels={"instagram": 5_000, "youtube": 50_000})
    creator(db, handle="big.insta", channels={"instagram": 20_000})

    found = search(client, brand, platform="instagram", min_followers=10_000)

    assert handles(found) == ["big.insta"]


def test_an_audience_range_without_a_platform_matches_any_channel(client, db, brand):
    creator(db, handle="youtube.mid", channels={"youtube": 30_000})
    creator(db, handle="tiny", channels={"instagram": 900})

    found = search(client, brand, min_followers=10_000, max_followers=50_000)

    assert handles(found) == ["youtube.mid"]


def test_a_price_filter_holds_on_one_package(client, db, brand):
    """A cheap Story does not make an expensive Reel affordable."""
    creator(
        db,
        handle="dear.reels",
        packages=[("instagram", "story", 200_000), ("instagram", "reel", 1_500_000)],
    )
    creator(db, handle="cheap.reels", packages=[("instagram", "reel", 400_000)])

    found = search(client, brand, format="reel", max_price_paise=500_000)

    assert handles(found) == ["cheap.reels"]
    assert found["items"][0]["from_price_paise"] == 400_000


def test_from_price_is_the_cheapest_answer_to_the_question_asked(client, db, brand):
    creator(
        db,
        handle="mixed",
        packages=[("instagram", "story", 200_000), ("instagram", "reel", 900_000)],
    )

    anything = search(client, brand)["items"][0]
    reels = search(client, brand, format="reel")["items"][0]

    assert anything["from_price_paise"] == 200_000
    assert reels["from_price_paise"] == 900_000


def test_a_creator_with_no_prices_says_so_rather_than_zero(client, db, brand):
    creator(db, handle="no.prices")

    assert search(client, brand)["items"][0]["from_price_paise"] is None


# --- paging and cost -----------------------------------------------------------------


def test_pages_run_newest_first_with_no_repeats(client, db, brand):
    for minutes in range(5):
        creator(db, handle=f"page.{minutes}", age_minutes=minutes)

    first = search(client, brand, limit=2)
    second = search(client, brand, limit=2, cursor=first["next_cursor"])
    third = search(client, brand, limit=2, cursor=second["next_cursor"])

    assert handles(first) + handles(second) + handles(third) == [
        "page.0",
        "page.1",
        "page.2",
        "page.3",
        "page.4",
    ]
    assert third["next_cursor"] is None


def test_the_number_of_queries_does_not_grow_with_the_page(client, db, brand):
    for i in range(12):
        creator(
            db,
            channels={"instagram": 10_000 + i},
            packages=[("instagram", "reel", 500_000 + i)],
        )
    with count_queries() as two:
        search(client, brand, limit=2)
    with count_queries() as twelve:
        search(client, brand, limit=12)

    assert len(twelve) == len(two)


# --- who may search ------------------------------------------------------------------


def test_creators_cannot_search_other_creators(client, db, clock):
    response = client.get(URL, headers=creator_user(db, clock).headers)

    assert response.status_code == 403


def test_it_is_not_public(client):
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "bad",
    [
        {"niche": "astrology"},
        {"platform": "tiktok"},
        {"format": "billboard"},
        {"min_followers": -1},
        {"max_price_paise": 0},
        {"q": "x"},
        {"limit": 0},
        {"cursor": "not-a-cursor"},
    ],
)
def test_bad_filters_are_refused(client, brand, bad):
    assert client.get(URL, params=bad, headers=brand.headers).status_code == 422


def test_contradictory_filters_are_refused_not_answered_with_nothing(client, brand):
    response = client.get(
        URL,
        params={"min_followers": 50_000, "max_followers": 10_000},
        headers=brand.headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_search"


def test_it_is_rate_limited(client, brand):
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(URL, headers=brand.headers).status_code == 200

    assert client.get(URL, headers=brand.headers).status_code == 429


# --- availability (D-083) -------------------------------------------------------------


def booked(db, row: Creator, until) -> Creator:
    row.booked_until = until
    db.flush()
    return row


def test_each_result_says_until_when_the_creator_is_booked(client, db, brand):
    free = creator(db, handle="free.one")
    busy = booked(
        db, creator(db, handle="busy.one"), FIXED_NOW.date() + timedelta(days=30)
    )
    was_busy = booked(
        db, creator(db, handle="was.busy"), FIXED_NOW.date() - timedelta(days=1)
    )

    items = client.get(URL, headers=brand.headers).json()["items"]

    shown = {item["handle"]: item["booked_until"] for item in items}
    assert shown == {
        free.handle: None,
        busy.handle: (FIXED_NOW.date() + timedelta(days=30)).isoformat(),
        was_busy.handle: None,  # the date has passed: taking work again
    }


def test_available_on_keeps_only_creators_free_that_day(client, db, brand):
    free = creator(db, handle="free.two")
    until_oct = booked(
        db, creator(db, handle="until.oct"), FIXED_NOW.date().replace(month=10, day=5)
    )

    def handles(day: str) -> set[str]:
        response = client.get(URL, params={"available_on": day}, headers=brand.headers)
        assert response.status_code == 200, response.text
        return {item["handle"] for item in response.json()["items"]}

    assert handles("2026-10-05") == {free.handle}  # booked through the 5th
    assert handles("2026-10-06") == {free.handle, until_oct.handle}


def test_available_on_must_be_a_date(client, brand):
    response = client.get(
        URL, params={"available_on": "next week"}, headers=brand.headers
    )

    assert response.status_code == 422

"""The public Creator Passport: readable by anyone, and carrying nothing private."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.rate_limit import limiter
from app.core.taxonomy import CURRENCY
from app.db.session import engine, get_db
from app.main import app
from app.modules.auth import public_router
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from tests.factories import FIXED_NOW, build_creator

URL = "/api/v1/creators/by-handle"
# The whole agreed contract. If this list changes, the change was deliberate.
PUBLIC_FIELDS = {
    "id",
    "handle",
    "display_name",
    "city",
    "niches",
    "languages",
    "bio",
    "member_since",
    "channels",
    "packages",
}
# A channel on the open internet is its link and nothing else (D-042).
PUBLIC_CHANNEL_FIELDS = {"platform", "profile_url"}
PUBLIC_PACKAGE_FIELDS = {
    "platform",
    "format",
    "title",
    "description",
    "price_paise",
    "currency",
    "delivery_days",
    "usage_rights_days",
}


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: FIXED_NOW
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def make_creator(db, **overrides) -> Creator:
    """A creator who has published their Passport.

    Published on purpose: these tests are about the public page, and nobody
    appears on it until they have chosen to (D-036). The tests that cover
    *not* having chosen pass `passport_published_at=None` explicitly.
    """
    overrides.setdefault("passport_published_at", FIXED_NOW)
    creator = build_creator(db, **overrides)
    db.add(creator)
    db.flush()
    return creator


def add_channel(db, creator: Creator, platform: str = "instagram", **overrides):
    fields = {
        "profile_url": f"https://{platform}.com/{creator.handle}",
        "followers": 48_213,
        "average_views": 9_731,
        "figures_as_of": FIXED_NOW.date(),
    }
    fields.update(overrides)
    channel = CreatorChannel(creator_id=creator.id, platform=platform, **fields)
    db.add(channel)
    db.flush()
    return channel


def add_package(db, creator: Creator, position: int = 0, **overrides):
    fields = {
        "platform": "instagram",
        "format": "reel",
        "title": f"Reel {position}",
        "description": None,
        "price_paise": 800_000,
        "currency": CURRENCY,
        "delivery_days": 5,
        "usage_rights_days": 30,
    }
    fields.update(overrides)
    package = CreatorPackage(creator_id=creator.id, position=position, **fields)
    db.add(package)
    db.flush()
    return package


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


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- reading it -----------------------------------------------------------


def test_anyone_can_read_a_profile_without_logging_in(client, db):
    creator = make_creator(db, handle="priya.eats", city="Coimbatore")

    response = client.get(f"{URL}/priya.eats")

    assert response.status_code == 200
    body = response.json()
    assert body["handle"] == "priya.eats"
    assert body["display_name"] == creator.display_name
    assert body["city"] == "Coimbatore"
    assert body["niches"] == creator.niches
    assert body["member_since"] == "2026-09"


def test_the_response_carries_exactly_the_agreed_fields(client, db):
    """A new column must never appear here by accident."""
    make_creator(db, handle="priya.eats")

    body = client.get(f"{URL}/priya.eats").json()

    assert set(body) == PUBLIC_FIELDS


def test_nothing_private_is_ever_in_the_response(client, db):
    creator = make_creator(db, handle="priya.eats")
    from app.modules.auth.models.account import Account

    account = db.get(Account, creator.account_id)

    text = client.get(f"{URL}/priya.eats").text

    assert account.phone not in text
    assert str(creator.account_id) not in text
    for forbidden in ("phone", "email", "account_id", "updated_at"):
        assert forbidden not in text


@pytest.mark.parametrize(
    "typed", ["Priya.Eats", "@priya.eats", "PRIYA.EATS", " priya.eats "]
)
def test_handles_are_matched_however_they_are_typed(client, db, typed):
    make_creator(db, handle="priya.eats")

    assert client.get(f"{URL}/{typed}").status_code == 200


def test_an_unknown_handle_is_not_found(client, db):
    make_creator(db, handle="priya.eats")

    assert_problem(client.get(f"{URL}/someone.else"), 404, "profile_not_found")


@pytest.mark.parametrize("handle", ["ab", "has space", "x" * 40, "!!"])
def test_an_impossible_handle_is_simply_not_found(client, db, handle):
    """No hint about what a valid handle looks like, and no stack trace."""
    assert_problem(client.get(f"{URL}/{handle}"), 404, "profile_not_found")


def test_two_creators_do_not_leak_into_each_other(client, db):
    make_creator(db, handle="priya.eats", city="Coimbatore")
    make_creator(db, handle="ravi.tech", city="Madurai", display_name="Ravi Tech")

    first = client.get(f"{URL}/priya.eats").json()
    second = client.get(f"{URL}/ravi.tech").json()

    assert first["city"] == "Coimbatore"
    assert second["city"] == "Madurai"
    assert first["id"] != second["id"]


# --- caching --------------------------------------------------------------


def test_a_profile_is_cacheable_for_five_minutes(client, db):
    make_creator(db, handle="priya.eats")

    response = client.get(f"{URL}/priya.eats")

    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"].startswith('"')


def test_an_unchanged_profile_costs_nothing_to_re_read(client, db):
    make_creator(db, handle="priya.eats")
    etag = client.get(f"{URL}/priya.eats").headers["etag"]

    again = client.get(f"{URL}/priya.eats", headers={"If-None-Match": etag})

    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag


def test_editing_the_profile_changes_the_etag(client, db):
    creator = make_creator(db, handle="priya.eats")
    first = client.get(f"{URL}/priya.eats").headers["etag"]

    creator.bio = "Now covering Madurai too."
    creator.updated_at = FIXED_NOW + timedelta(hours=1)
    db.flush()
    second = client.get(f"{URL}/priya.eats")

    assert second.headers["etag"] != first
    assert second.status_code == 200
    assert second.json()["bio"] == "Now covering Madurai too."


def test_an_old_etag_gets_the_new_profile(client, db):
    creator = make_creator(db, handle="priya.eats")
    stale = client.get(f"{URL}/priya.eats").headers["etag"]
    creator.city = "Madurai"
    creator.updated_at = FIXED_NOW + timedelta(hours=1)
    db.flush()

    response = client.get(f"{URL}/priya.eats", headers={"If-None-Match": stale})

    assert response.status_code == 200
    assert response.json()["city"] == "Madurai"


# --- channels and prices (D-042, D-055) ----------------------------------


def test_channels_appear_as_links_only(client, db):
    creator = make_creator(db, handle="priya.eats")
    add_channel(db, creator, "instagram")
    add_channel(db, creator, "youtube")

    body = client.get(f"{URL}/priya.eats").json()

    assert body["channels"] == [
        {"platform": "instagram", "profile_url": "https://instagram.com/priya.eats"},
        {"platform": "youtube", "profile_url": "https://youtube.com/priya.eats"},
    ]
    for channel in body["channels"]:
        assert set(channel) == PUBLIC_CHANNEL_FIELDS


def test_our_copy_of_a_follower_count_never_appears(client, db):
    """D-042: anyone can read the real number at the source; we do not
    republish the creator's claim under our name."""
    creator = make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)
    add_channel(db, creator, followers=48_213, average_views=9_731)
    add_package(db, creator)

    text = client.get(f"{URL}/priya.eats").text

    for forbidden in ("48213", "9731", "followers", "average_views", "figures_as_of"):
        assert forbidden not in text


def test_prices_stay_off_the_page_until_the_creator_publishes_them(client, db):
    creator = make_creator(db, handle="priya.eats")
    add_package(db, creator, price_paise=1_234_500)

    response = client.get(f"{URL}/priya.eats")

    assert response.json()["packages"] == []
    assert "1234500" not in response.text


def test_published_prices_appear_in_the_creators_order(client, db):
    creator = make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)
    add_package(db, creator, position=2, title="Story set", format="story")
    add_package(db, creator, position=0, title="1 Instagram Reel", price_paise=800_000)

    packages = client.get(f"{URL}/priya.eats").json()["packages"]

    assert [p["title"] for p in packages] == ["1 Instagram Reel", "Story set"]
    assert packages[0] == {
        "platform": "instagram",
        "format": "reel",
        "title": "1 Instagram Reel",
        "description": None,
        "price_paise": 800_000,
        "currency": CURRENCY,
        "delivery_days": 5,
        "usage_rights_days": 30,
    }
    for package in packages:
        assert set(package) == PUBLIC_PACKAGE_FIELDS


def test_a_profile_with_nothing_added_has_empty_lists(client, db):
    make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)

    body = client.get(f"{URL}/priya.eats").json()

    assert body["channels"] == []
    assert body["packages"] == []


def test_publishing_prices_does_not_publish_the_passport(client, db):
    """Two separate consents: prices on, Passport off, is still a 404."""
    creator = make_creator(
        db,
        handle="priya.eats",
        passport_published_at=None,
        rate_card_public_at=FIXED_NOW,
    )
    add_package(db, creator)

    assert_problem(client.get(f"{URL}/priya.eats"), 404, "profile_not_found")


def test_another_creators_channels_and_prices_never_appear(client, db):
    priya = make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)
    arun = make_creator(db, handle="arun.fit", rate_card_public_at=FIXED_NOW)
    add_channel(db, arun)
    add_package(db, arun, title="Arun reel")
    add_package(db, priya, title="Priya reel")

    body = client.get(f"{URL}/priya.eats").json()

    assert body["channels"] == []
    assert [p["title"] for p in body["packages"]] == ["Priya reel"]


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda db, c, p: setattr(p, "price_paise", 900_000), id="price"),
        pytest.param(lambda db, c, p: add_channel(db, c, "youtube"), id="channel-added"),
        pytest.param(
            lambda db, c, p: setattr(c, "rate_card_public_at", None),
            id="prices-unpublished",
        ),
    ],
)
def test_editing_a_channel_or_price_changes_the_etag(client, db, edit):
    """They live in other tables, so the profile's own timestamp would not
    notice; a cached page must not keep showing an old price."""
    creator = make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)
    package = add_package(db, creator)
    stale = client.get(f"{URL}/priya.eats").headers["etag"]

    edit(db, creator, package)
    db.flush()
    response = client.get(f"{URL}/priya.eats", headers={"If-None-Match": stale})

    assert response.status_code == 200
    assert response.headers["etag"] != stale


def test_the_number_of_queries_does_not_grow_with_packages(client, db):
    creator = make_creator(db, handle="priya.eats", rate_card_public_at=FIXED_NOW)
    add_channel(db, creator)
    add_package(db, creator, position=0)
    with count_queries() as one:
        assert client.get(f"{URL}/priya.eats").status_code == 200

    add_channel(db, creator, "youtube")
    for position in range(1, 10):
        add_package(db, creator, position=position)
    with count_queries() as ten:
        assert len(client.get(f"{URL}/priya.eats").json()["packages"]) == 10

    assert len(ten) == len(one)


# --- the publication switch ----------------------------------------------


def test_a_creator_who_has_not_published_is_not_found(client, db):
    """Not "private", not "hidden" — simply not there, and indistinguishable
    from a handle that was never taken."""
    make_creator(db, handle="priya.eats", passport_published_at=None)

    assert_problem(client.get(f"{URL}/priya.eats"), 404, "profile_not_found")


def test_nobody_is_published_until_they_choose(db):
    """The default, and the whole point of D-036.

    Somebody who signed up to browse campaigns is not findable by strangers.
    """
    creator = build_creator(db, handle=f"seam{uuid.uuid4().hex[:8]}")

    assert creator.passport_published_at is None
    assert public_router.passport_is_public(creator) is False


def test_choosing_to_publish_makes_the_page_answer(db):
    creator = build_creator(
        db, handle=f"seam{uuid.uuid4().hex[:8]}", passport_published_at=FIXED_NOW
    )

    assert public_router.passport_is_public(creator) is True


def test_an_unpublished_profile_cannot_be_told_apart_from_a_missing_one(client, db):
    """A 404 either way, so nobody can use this page to work out whether a
    handle belongs to somebody who chose not to be listed."""
    make_creator(db, handle="priya.eats", passport_published_at=None)

    hidden = client.get(f"{URL}/priya.eats")
    absent = client.get(f"{URL}/nobody.here")

    assert hidden.status_code == absent.status_code == 404
    assert hidden.json()["code"] == absent.json()["code"]


# --- limits ---------------------------------------------------------------


def test_the_public_page_is_rate_limited(client, db):
    make_creator(db, handle="priya.eats")
    for _ in range(60):
        client.get(f"{URL}/priya.eats")

    response = client.get(f"{URL}/priya.eats")

    assert_problem(response, 429, "rate_limited")
    assert response.headers["retry-after"] == "60"

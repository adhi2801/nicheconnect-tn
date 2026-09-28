"""The media kit: one signed-in screen for a brand weighing a creator (D-055).

What is worth proving is what separates it from the public Passport: brands
see the dated, self-reported numbers and every price, published or not; and
who may read it follows the delivery record it contains (D-038 point 7).
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import event, select

from app.core.taxonomy import CURRENCY
from app.db.session import engine
from app.modules.auth.media_kit_router import READ_LIMIT
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from tests.deal_flow import User, accepted_memo, brand_user, creator_user

# The whole agreed contract. If this list changes, the change was deliberate.
MEDIA_KIT_FIELDS = {
    "creator_id",
    "handle",
    "display_name",
    "city",
    "niches",
    "languages",
    "bio",
    "member_since",
    "channels",
    "packages",
    "delivery_record",
}


def kit_url(creator_id) -> str:
    return f"/api/v1/creators/{creator_id}/media-kit"


def profile_of(db, user: User) -> Creator:
    creator = db.scalar(select(Creator).where(Creator.account_id == user.account_id))
    assert creator is not None
    return creator


def add_channel(db, creator: Creator, platform: str = "instagram", **overrides):
    fields = {
        "profile_url": f"https://{platform}.com/{creator.handle}",
        "followers": 48_213,
        "average_views": 9_731,
        "figures_as_of": creator.created_at.date(),
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


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


# --- what it says ----------------------------------------------------------


def test_a_brand_sees_the_whole_kit(client, db, brand, creator):
    profile = profile_of(db, creator)
    add_channel(db, profile)
    add_package(db, profile, title="1 Instagram Reel")

    response = client.get(kit_url(profile.id), headers=brand.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == MEDIA_KIT_FIELDS
    assert body["creator_id"] == str(profile.id)
    assert body["handle"] == profile.handle
    assert body["display_name"] == profile.display_name
    assert body["member_since"] == profile.created_at.strftime("%Y-%m")
    assert [p["title"] for p in body["packages"]] == ["1 Instagram Reel"]


def test_brands_see_the_numbers_dated_and_labelled_as_the_creators_own(
    client, db, brand, creator
):
    """The public page shows only the link (D-042); a brand deciding whom to
    pay needs a figure, so here it gets one, never passed off as ours."""
    profile = profile_of(db, creator)
    channel = add_channel(db, profile, followers=48_213, average_views=9_731)

    [shown] = client.get(kit_url(profile.id), headers=brand.headers).json()["channels"]

    assert shown["followers"] == 48_213
    assert shown["average_views"] == 9_731
    assert shown["figures_as_of"] == channel.figures_as_of.isoformat()
    assert shown["self_reported"] is True


def test_brands_see_prices_the_creator_has_not_published(client, db, brand, creator):
    """The price switch decides what strangers see, not signed-in brands."""
    profile = profile_of(db, creator)
    assert profile.rate_card_public_at is None
    add_package(db, profile, price_paise=1_234_500)

    [package] = client.get(kit_url(profile.id), headers=brand.headers).json()["packages"]

    assert package["price_paise"] == 1_234_500
    assert package["currency"] == CURRENCY


def test_packages_come_in_the_creators_order(client, db, brand, creator):
    profile = profile_of(db, creator)
    add_package(db, profile, position=2, title="Story set", format="story")
    add_package(db, profile, position=0, title="1 Instagram Reel")

    packages = client.get(kit_url(profile.id), headers=brand.headers).json()["packages"]

    assert [p["title"] for p in packages] == ["1 Instagram Reel", "Story set"]


def test_an_unpublished_passport_does_not_hide_the_kit_from_brands(
    client, db, brand, creator
):
    """The Passport switch is about the open internet. A brand on the
    platform can already find this creator through matching."""
    profile = profile_of(db, creator)
    assert profile.passport_published_at is None

    assert client.get(kit_url(profile.id), headers=brand.headers).status_code == 200


def test_the_delivery_record_is_the_same_one_its_own_endpoint_gives(
    client, db, brand, creator
):
    """One source of truth: the kit nests the record, it does not recount it."""
    accepted_memo(client, brand, creator)
    creator_id = profile_of(db, creator).id

    kit = client.get(kit_url(creator_id), headers=brand.headers).json()
    record = client.get(
        f"/api/v1/creators/{creator_id}/delivery-record", headers=brand.headers
    ).json()

    assert kit["delivery_record"] == record


def test_nothing_private_is_ever_in_the_response(client, db, brand, creator):
    profile = profile_of(db, creator)
    account = db.get(Account, creator.account_id)

    text = client.get(kit_url(profile.id), headers=brand.headers).text

    assert account.phone not in text
    assert str(creator.account_id) not in text
    for forbidden in ("phone", "email", "account_id", "passport_published_at"):
        assert forbidden not in text


def test_another_creators_channels_and_prices_never_appear(
    client, db, clock, brand, creator
):
    other = profile_of(db, creator_user(db, clock))
    add_channel(db, other)
    add_package(db, other, title="Not theirs")
    profile = profile_of(db, creator)

    body = client.get(kit_url(profile.id), headers=brand.headers).json()

    assert body["channels"] == []
    assert body["packages"] == []


# --- who may read it -------------------------------------------------------


def test_a_creator_can_read_their_own_kit(client, db, creator):
    profile = profile_of(db, creator)

    response = client.get(kit_url(profile.id), headers=creator.headers)

    assert response.status_code == 200
    assert response.json()["creator_id"] == str(profile.id)


def test_another_creator_cannot_read_it(client, db, clock, creator):
    stranger = creator_user(db, clock)

    response = client.get(kit_url(profile_of(db, creator).id), headers=stranger.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_another_creator_cannot_even_learn_whether_an_id_exists(client, db, creator):
    real = client.get(kit_url(profile_of(db, creator).id), headers=creator.headers)
    assert real.status_code == 200
    missing = client.get(kit_url(uuid.uuid4()), headers=creator.headers)

    assert missing.status_code == 403
    assert missing.json()["code"] == "role_not_allowed"


def test_it_is_not_public(client, db, creator):
    response = client.get(kit_url(profile_of(db, creator).id))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_an_unknown_creator_is_not_found(client, brand):
    response = client.get(kit_url(uuid.uuid4()), headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_an_invalid_id_is_rejected(client, brand):
    assert client.get(kit_url("not-an-id"), headers=brand.headers).status_code == 422


# --- cost ------------------------------------------------------------------


def test_the_number_of_queries_does_not_grow_with_the_kit(client, db, brand, creator):
    profile = profile_of(db, creator)
    add_channel(db, profile)
    add_package(db, profile, position=0)
    accepted_memo(client, brand, creator)
    with count_queries() as small:
        assert client.get(kit_url(profile.id), headers=brand.headers).status_code == 200

    add_channel(db, profile, "youtube")
    for position in range(1, 10):
        add_package(db, profile, position=position)
    accepted_memo(client, brand, creator)
    with count_queries() as large:
        body = client.get(kit_url(profile.id), headers=brand.headers).json()
        assert len(body["packages"]) == 10

    assert len(large) == len(small)


def test_it_is_rate_limited(client, db, brand, creator):
    url = kit_url(profile_of(db, creator).id)
    limit = int(READ_LIMIT.split()[0])
    for _ in range(limit):
        assert client.get(url, headers=brand.headers).status_code == 200

    response = client.get(url, headers=brand.headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"

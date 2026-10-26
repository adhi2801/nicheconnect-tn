"""Where a connected account shows (item 29 piece 2, D-134, D-135).

Signed-in brands see the platform's count beside the creator's own, in
search and the media kit; the public Passport shows only that the creator
controls the account, never a count (D-135, keeping D-042). An expired
connection shows nowhere.
"""

import pytest
from sqlalchemy import update

from app.modules.auth.models.creator import Creator
from app.modules.profiles.models import CreatorChannel
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import FIXED_NOW
from tests.modules.admin.test_takedowns_api import creator_id_of
from tests.modules.profiles.test_connections_api import connected
from tests.modules.safety.test_takedown_visibility_api import handle_of


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.execute(
        update(Creator)
        .where(Creator.account_id == user.account_id)
        .values(passport_published_at=FIXED_NOW, city="Testpur Connected")
    )
    db.add(
        CreatorChannel(
            creator_id=creator_id_of(db, user),
            platform="instagram",
            profile_url="https://www.instagram.com/priya.eats",
            followers=30_000,
            figures_as_of=FIXED_NOW.date(),
        )
    )
    db.flush()
    return user


def search_channel(client, brand: User, creator: User, db) -> dict:
    body = client.get(
        "/api/v1/creators", params={"city": "Testpur Connected"}, headers=brand.headers
    ).json()
    (item,) = [i for i in body["items"] if i["creator_id"] == creator_id_of(db, creator)]
    (channel,) = item["channels"]
    return channel


def test_search_shows_the_platform_count_beside_the_stated_one(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms, followers=24_000)
    brand = brand_user(db, clock)

    channel = search_channel(client, brand, creator, db)

    assert (channel["followers"], channel["self_reported"]) == (30_000, True)
    assert channel["verified_followers"] == 24_000
    assert channel["verified_as_of"] is not None


def test_an_expired_connection_shows_no_platform_count(
    client, db, clock, creator, platforms
):
    from app.modules.profiles.connection_models import ConnectedAccount

    connected(client, creator, platforms)
    db.execute(update(ConnectedAccount).values(status="expired"))
    brand = brand_user(db, clock)

    channel = search_channel(client, brand, creator, db)

    assert (channel["verified_followers"], channel["verified_as_of"]) == (None, None)
    media = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/media-kit", headers=brand.headers
    ).json()
    assert media["connected_accounts"] == []


def test_the_media_kit_carries_the_platform_count(client, db, clock, creator, platforms):
    connected(client, creator, platforms, handle="priya.eats", followers=24_000)
    brand = brand_user(db, clock)

    body = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/media-kit", headers=brand.headers
    ).json()

    (account,) = body["connected_accounts"]
    assert {k: account[k] for k in ("platform", "handle", "verified_followers")} == {
        "platform": "instagram",
        "handle": "priya.eats",
        "verified_followers": 24_000,
    }


def test_the_public_passport_shows_control_never_a_count(
    client, db, clock, creator, platforms
):
    connected(client, creator, platforms, handle="priya.eats", followers=24_000)

    body = client.get(f"/api/v1/creators/by-handle/{handle_of(db, creator)}").json()

    (account,) = body["connected_accounts"]
    assert set(account) == {"platform", "handle", "connected_since"}
    assert (
        "24000"
        not in client.get(f"/api/v1/creators/by-handle/{handle_of(db, creator)}").text
    )

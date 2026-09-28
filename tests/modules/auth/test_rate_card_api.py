"""Channels, packages and the switch that publishes prices (D-055).

The rules worth a test are the ones a database cannot hold: a link must
belong to the platform it claims, ten packages is the limit, another
creator's package is 404 rather than 403, and publishing twice keeps the
first date because the date is the consent.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import app.db.models
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, build_creator, create_account

CHANNELS = "/api/v1/creators/me/channels"
PACKAGES = "/api/v1/creators/me/packages"
PUBLISH = "/api/v1/creators/me/rate-card/publish"
UNPUBLISH = "/api/v1/creators/me/rate-card/unpublish"


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


def creator_login(db) -> tuple[Creator, dict[str, str]]:
    creator = build_creator(db, handle=f"rc{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    token, _ = create_access_token(creator.account_id, "creator", FIXED_NOW)
    return creator, {"Authorization": f"Bearer {token}"}


def brand_login(db) -> dict[str, str]:
    account = create_account(db, "brand")
    token, _ = create_access_token(account.id, "brand", FIXED_NOW)
    return {"Authorization": f"Bearer {token}"}


def channel_body(**overrides) -> dict:
    body = {
        "profile_url": "https://instagram.com/priya.eats",
        "followers": 12_000,
        "average_views": 4_500,
    }
    body.update(overrides)
    return body


def package_body(**overrides) -> dict:
    body = {
        "platform": "instagram",
        "format": "reel",
        "title": "1 Instagram Reel",
        "description": "One reel, shot and edited by me.",
        "price_paise": 800_000,
        "delivery_days": 5,
        "usage_rights_days": 30,
        "position": 0,
    }
    body.update(overrides)
    return body


# --- channels --------------------------------------------------------------


def test_a_channel_is_added_and_read_back(client, db):
    _, headers = creator_login(db)

    created = client.put(f"{CHANNELS}/instagram", json=channel_body(), headers=headers)

    assert created.status_code == 200
    assert created.json()["followers"] == 12_000
    assert client.get(CHANNELS, headers=headers).json()[0]["platform"] == "instagram"


def test_the_date_comes_from_the_server_not_the_client(client, db):
    """It records when we were told, which is what makes the figure readable."""
    _, headers = creator_login(db)

    body = client.put(
        f"{CHANNELS}/instagram",
        json=channel_body(figures_as_of="2020-01-01"),
        headers=headers,
    )

    # The client cannot even send it: the schema forbids unknown fields.
    assert body.status_code == 422


def test_the_figures_are_labelled_as_the_creators_own(client, db):
    _, headers = creator_login(db)
    client.put(f"{CHANNELS}/instagram", json=channel_body(), headers=headers)

    row = client.get(CHANNELS, headers=headers).json()[0]

    assert row["self_reported"] is True
    assert row["figures_as_of"] == FIXED_NOW.date().isoformat()


def test_saving_the_same_platform_twice_replaces_rather_than_duplicates(client, db):
    """A retry on patchy 4G must not leave two Instagrams."""
    _, headers = creator_login(db)
    client.put(f"{CHANNELS}/instagram", json=channel_body(), headers=headers)

    client.put(
        f"{CHANNELS}/instagram", json=channel_body(followers=15_000), headers=headers
    )

    rows = client.get(CHANNELS, headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["followers"] == 15_000


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("instagram", "https://youtube.com/@someone"),
        ("instagram", "https://example.com/priya"),
        ("youtube", "https://instagram.com/priya.eats"),
    ],
)
def test_a_link_must_belong_to_the_platform_it_claims(client, db, platform, url):
    """Without this the public page would carry a link of anyone's choosing."""
    _, headers = creator_login(db)

    response = client.put(
        f"{CHANNELS}/{platform}", json=channel_body(profile_url=url), headers=headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "profile_url_platform_mismatch"


def test_youtube_short_links_are_accepted(client, db):
    _, headers = creator_login(db)

    response = client.put(
        f"{CHANNELS}/youtube",
        json=channel_body(profile_url="https://youtu.be/abc123"),
        headers=headers,
    )

    assert response.status_code == 200


def test_an_unknown_platform_is_refused(client, db):
    _, headers = creator_login(db)

    response = client.put(f"{CHANNELS}/tiktok", json=channel_body(), headers=headers)

    assert response.status_code == 422


def test_a_channel_can_be_removed(client, db):
    _, headers = creator_login(db)
    client.put(f"{CHANNELS}/instagram", json=channel_body(), headers=headers)

    assert client.delete(f"{CHANNELS}/instagram", headers=headers).status_code == 204
    assert client.get(CHANNELS, headers=headers).json() == []


def test_removing_a_channel_that_is_not_there_is_404(client, db):
    _, headers = creator_login(db)

    assert client.delete(f"{CHANNELS}/youtube", headers=headers).status_code == 404


# --- packages --------------------------------------------------------------


def test_a_package_is_created_and_listed(client, db):
    _, headers = creator_login(db)

    created = client.post(PACKAGES, json=package_body(), headers=headers)

    assert created.status_code == 201
    assert created.headers["Location"].endswith(created.json()["id"])
    assert created.json()["price_paise"] == 800_000
    assert created.json()["currency"] == "INR"
    assert len(client.get(PACKAGES, headers=headers).json()) == 1


def test_a_free_package_is_refused(client, db):
    _, headers = creator_login(db)

    response = client.post(PACKAGES, json=package_body(price_paise=0), headers=headers)

    assert response.status_code == 422


def test_ten_packages_is_the_limit(client, db):
    _, headers = creator_login(db)
    for i in range(10):
        created = client.post(
            PACKAGES, json=package_body(position=i, title=f"Package {i}"), headers=headers
        )
        assert created.status_code == 201

    eleventh = client.post(PACKAGES, json=package_body(position=11), headers=headers)

    assert eleventh.status_code == 409
    assert eleventh.json()["code"] == "package_limit_reached"


def test_a_package_can_be_changed_field_by_field(client, db):
    _, headers = creator_login(db)
    package_id = client.post(PACKAGES, json=package_body(), headers=headers).json()["id"]

    changed = client.patch(
        f"{PACKAGES}/{package_id}", json={"price_paise": 950_000}, headers=headers
    )

    assert changed.status_code == 200
    assert changed.json()["price_paise"] == 950_000
    assert changed.json()["title"] == "1 Instagram Reel"  # untouched


def test_an_empty_change_is_refused(client, db):
    _, headers = creator_login(db)
    package_id = client.post(PACKAGES, json=package_body(), headers=headers).json()["id"]

    assert (
        client.patch(f"{PACKAGES}/{package_id}", json={}, headers=headers).status_code
        == 422
    )


def test_a_package_can_be_deleted(client, db):
    _, headers = creator_login(db)
    package_id = client.post(PACKAGES, json=package_body(), headers=headers).json()["id"]

    assert client.delete(f"{PACKAGES}/{package_id}", headers=headers).status_code == 204
    assert client.get(PACKAGES, headers=headers).json() == []


def test_another_creators_package_is_404_not_403(client, db):
    """403 would confirm the id exists, which would let anyone walk the table."""
    _, owner_headers = creator_login(db)
    package_id = client.post(PACKAGES, json=package_body(), headers=owner_headers).json()[
        "id"
    ]
    _, stranger_headers = creator_login(db)

    assert (
        client.patch(
            f"{PACKAGES}/{package_id}", json={"price_paise": 1}, headers=stranger_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{PACKAGES}/{package_id}", headers=stranger_headers).status_code
        == 404
    )


def test_a_package_that_does_not_exist_is_404(client, db):
    _, headers = creator_login(db)

    assert client.delete(f"{PACKAGES}/{uuid.uuid4()}", headers=headers).status_code == 404


# --- the consent switch ----------------------------------------------------


def test_prices_are_private_until_published(client, db):
    creator, _ = creator_login(db)

    assert creator.rate_card_public_at is None


def test_publishing_records_when_the_creator_chose(client, db):
    _, headers = creator_login(db)

    body = client.post(PUBLISH, headers=headers).json()

    assert body["rate_card_public_at"] is not None


def test_publishing_twice_keeps_the_first_date(client, db):
    """A second tap on a slow connection is not a second decision."""
    _, headers = creator_login(db)
    first = client.post(PUBLISH, headers=headers).json()["rate_card_public_at"]

    second = client.post(PUBLISH, headers=headers).json()["rate_card_public_at"]

    assert second == first


def test_unpublishing_is_never_refused(client, db):
    """Somebody who wants to stop showing what they charge should not have to
    argue with us — including when it was never published."""
    _, headers = creator_login(db)

    assert client.post(UNPUBLISH, headers=headers).status_code == 200
    client.post(PUBLISH, headers=headers)
    assert client.post(UNPUBLISH, headers=headers).json()["rate_card_public_at"] is None


def test_unpublishing_does_not_delete_the_packages(client, db):
    _, headers = creator_login(db)
    client.post(PACKAGES, json=package_body(), headers=headers)
    client.post(PUBLISH, headers=headers)

    client.post(UNPUBLISH, headers=headers)

    assert len(client.get(PACKAGES, headers=headers).json()) == 1


# --- who may call ----------------------------------------------------------


@pytest.mark.parametrize("url", [CHANNELS, PACKAGES])
def test_without_a_token_it_is_refused(client, db, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", [CHANNELS, PACKAGES])
def test_a_brand_may_not_use_these(client, db, url):
    assert client.get(url, headers=brand_login(db)).status_code == 403


def test_a_creator_without_a_profile_is_404(client, db):
    account = create_account(db, "creator")
    token, _ = create_access_token(account.id, "creator", FIXED_NOW)

    response = client.get(CHANNELS, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404

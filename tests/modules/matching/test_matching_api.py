"""Suggesting creators for a campaign, and saying why (D-052, backlog D2/D3).

A fake encoder stands in for the model: what matters here is who comes back,
in what order, and who is kept out — not whether Qwen3 produces good vectors.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

import app.db.models
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from app.modules.matching import embedder, service
from tests.factories import (
    FIXED_NOW,
    build_brand,
    build_campaign,
    build_creator,
    create_account,
)

PUBLISHED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=FIXED_NOW.tzinfo)


class FixedEncoder:
    """Every text gets the same vector, so ranking is decided by the query."""

    def encode(self, sentences, **kwargs):
        return [[0.5] * embedder.EXPECTED_DIMENSIONS for _ in sentences]


@pytest.fixture(autouse=True)
def only_this_tests_creators(db) -> None:
    """Matching considers every published creator, so a laptop's seeded
    sample data (about half of it published) would land in these results.
    Hidden inside the test's transaction, which is rolled back afterwards, so
    the sample data survives."""
    db.execute(update(Creator).values(passport_published_at=None))


@pytest.fixture
def encoder() -> Iterator[FixedEncoder]:
    fake = FixedEncoder()
    embedder.set_model(fake)
    try:
        yield fake
    finally:
        embedder.set_model(None)


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


def brand_login(db) -> tuple[Brand, dict[str, str]]:
    brand = build_brand(db, email=f"m-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    token, _ = create_access_token(brand.account_id, "brand", FIXED_NOW)
    return brand, {"Authorization": f"Bearer {token}"}


def creator_login(db) -> dict[str, str]:
    account = create_account(db, "creator")
    token, _ = create_access_token(account.id, "creator", FIXED_NOW)
    return {"Authorization": f"Bearer {token}"}


def a_campaign(db, brand, **overrides):
    campaign = build_campaign(
        db,
        brand_id=brand.id,
        status="open",
        cities=["Madurai"],
        niches=["food"],
        **overrides,
    )
    db.add(campaign)
    db.flush()
    return campaign


def a_creator(db, *, published: bool, city="Madurai", niches=("food",)):
    creator = build_creator(
        db,
        handle=f"m{uuid.uuid4().hex[:12]}",
        city=city,
        niches=list(niches),
        passport_published_at=PUBLISHED_AT if published else None,
    )
    db.add(creator)
    db.flush()
    return creator


def url(campaign) -> str:
    return f"/api/v1/campaigns/{campaign.id}/matches"


# --- the happy path --------------------------------------------------------


def test_a_matching_creator_comes_back_with_reasons(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    creator = a_creator(db, published=True)

    body = client.get(url(campaign), headers=headers).json()

    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["creator"]["handle"] == creator.handle
    assert match["reasons"]["shared_niches"] == ["food"]
    assert match["reasons"]["city"] == "Madurai"
    assert match["reasons"]["accepted_deals"] == 0


def test_the_answer_says_when_it_is_not_ranked_by_similarity(client, db, encoder):
    """Nothing is indexed yet, so the order is the facts alone — and the
    interface must be able to say so rather than imply a ranking."""
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    a_creator(db, published=True)

    body = client.get(url(campaign), headers=headers).json()

    assert body["ranked_by_similarity"] is False
    assert body["matches"][0]["reasons"]["similarity"] is None


def test_once_indexed_it_is_ranked_and_scored(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    a_creator(db, published=True)
    service.refresh_campaigns(db, campaign_ids=[campaign.id])
    service.refresh_creators(db)
    db.flush()

    body = client.get(url(campaign), headers=headers).json()

    assert body["ranked_by_similarity"] is True
    assert body["matches"][0]["reasons"]["similarity"] == pytest.approx(1.0, abs=1e-3)


def test_no_candidates_is_an_empty_list_not_an_error(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)

    response = client.get(url(campaign), headers=headers)

    assert response.status_code == 200
    assert response.json() == {"matches": [], "ranked_by_similarity": False}


# --- who is kept out -------------------------------------------------------


def test_a_creator_who_never_published_is_not_discoverable(client, db, encoder):
    """D-036: a creator who signed up to browse has not asked to be findable
    by strangers, and a brand searching for someone who never applied is
    exactly that. This is the test that keeps that promise."""
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    a_creator(db, published=False)

    body = client.get(url(campaign), headers=headers).json()

    assert body["matches"] == []


def test_a_creator_in_another_city_is_left_out(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    a_creator(db, published=True, city="Chennai")

    assert client.get(url(campaign), headers=headers).json()["matches"] == []


def test_a_creator_sharing_no_niche_is_left_out(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    a_creator(db, published=True, niches=("fitness",))

    assert client.get(url(campaign), headers=headers).json()["matches"] == []


def test_no_private_field_is_ever_returned(client, db, encoder):
    """The response reuses the public Passport shape, so a brand searching
    sees exactly what the open internet would, and no more."""
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    creator = a_creator(db, published=True)

    match = client.get(url(campaign), headers=headers).json()["matches"][0]

    assert set(match["creator"]) == {
        "id",
        "handle",
        "display_name",
        "city",
        "niches",
        "languages",
        "bio",
        "member_since",
    }
    assert str(creator.account_id) not in str(match)


# --- who may ask -----------------------------------------------------------


def test_without_a_token_it_is_refused(client, db, encoder):
    brand, _ = brand_login(db)
    campaign = a_campaign(db, brand)

    assert client.get(url(campaign)).status_code == 401


def test_a_creator_may_not_ask(client, db, encoder):
    brand, _ = brand_login(db)
    campaign = a_campaign(db, brand)

    response = client.get(url(campaign), headers=creator_login(db))

    assert response.status_code == 403


def test_another_brands_campaign_is_404_not_403(client, db, encoder):
    """404, so a brand cannot discover which campaign ids exist."""
    other_brand, _ = brand_login(db)
    campaign = a_campaign(db, other_brand)
    _, headers = brand_login(db)

    assert client.get(url(campaign), headers=headers).status_code == 404


def test_a_campaign_that_does_not_exist_is_404(client, db, encoder):
    _, headers = brand_login(db)

    response = client.get(f"/api/v1/campaigns/{uuid.uuid4()}/matches", headers=headers)

    assert response.status_code == 404


@pytest.mark.parametrize("limit", [0, -1, 51, "many"])
def test_a_bad_limit_is_refused(client, db, encoder, limit):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)

    response = client.get(f"{url(campaign)}?limit={limit}", headers=headers)

    assert response.status_code == 422


def test_the_limit_is_honoured(client, db, encoder):
    brand, headers = brand_login(db)
    campaign = a_campaign(db, brand)
    for _ in range(3):
        a_creator(db, published=True)

    body = client.get(f"{url(campaign)}?limit=2", headers=headers).json()

    assert len(body["matches"]) == 2

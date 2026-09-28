"""Fair-rate guidance: a range from published rate cards, or nothing (D-056).

The tests that matter are the ones that keep it honest: five creators or no
figures, each creator counted once, never a minimum or maximum, unpublished
prices never counted, and narrowing that is reported rather than silent.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.clock import india_date
from app.core.taxonomy import CURRENCY
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.rate_guidance_router import READ_LIMIT
from app.modules.auth.rate_guidance_service import audience_band
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import FIXED_NOW, build_creator

URL = "/api/v1/rate-guidance"
REEL_12K = {"platform": "instagram", "format": "reel", "followers": 12_000}
# The whole agreed contract. If this list changes, the change was deliberate.
FIELDS = {
    "platform",
    "format",
    "audience_band",
    "narrowed_to",
    "source",
    "creators_counted",
    "lower_quarter_paise",
    "median_paise",
    "upper_quarter_paise",
    "currency",
    "audience_self_reported",
    "audience_figures_from",
    "as_of",
}


def pricer(
    db,
    *prices: int,
    followers: int = 20_000,
    niche: str = "food",
    city: str = "Madurai",
    published: bool = True,
    platform: str = "instagram",
    package_format: str = "reel",
    youtube_followers: int | None = None,
):
    """A creator with an Instagram channel and one package per price."""
    creator = build_creator(
        db,
        handle=f"rg{uuid.uuid4().hex[:12]}",
        niches=[niche],
        city=city,
        rate_card_public_at=FIXED_NOW if published else None,
    )
    db.add(creator)
    db.flush()
    db.add(
        CreatorChannel(
            creator_id=creator.id,
            platform="instagram",
            profile_url=f"https://instagram.com/{creator.handle}",
            followers=followers,
            average_views=None,
            figures_as_of=india_date(FIXED_NOW),
        )
    )
    if youtube_followers is not None:
        db.add(
            CreatorChannel(
                creator_id=creator.id,
                platform="youtube",
                profile_url=f"https://youtube.com/{creator.handle}",
                followers=youtube_followers,
                average_views=None,
                figures_as_of=india_date(FIXED_NOW),
            )
        )
    for position, price in enumerate(prices):
        db.add(
            CreatorPackage(
                creator_id=creator.id,
                platform=platform,
                format=package_format,
                title=f"Package {position}",
                price_paise=price,
                currency=CURRENCY,
                delivery_days=5,
                position=position,
            )
        )
    db.flush()
    return creator


def five_food_creators_in_madurai(db) -> None:
    for price in (100_000, 200_000, 300_000, 400_000, 500_000):
        pricer(db, price)


def guidance(client, user: User, **params) -> dict:
    response = client.get(URL, params={**REEL_12K, **params}, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(autouse=True)
def only_this_tests_prices(db) -> None:
    """Guidance aggregates every published price, so a laptop's seeded sample
    data would land in these figures. Removed inside the test's transaction,
    which is rolled back afterwards, so the sample data survives."""
    db.execute(delete(CreatorPackage))


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


# --- the figures -----------------------------------------------------------


def test_five_creators_give_a_range(client, db, brand):
    five_food_creators_in_madurai(db)

    body = guidance(client, brand)

    assert set(body) == FIELDS
    assert body["creators_counted"] == 5
    assert body["lower_quarter_paise"] == 200_000
    assert body["median_paise"] == 300_000
    assert body["upper_quarter_paise"] == 400_000
    assert body["currency"] == CURRENCY
    assert body["source"] == "published_asking_prices"
    assert body["audience_band"] == "10k_50k"
    assert body["audience_self_reported"] is True
    assert body["audience_figures_from"] == india_date(FIXED_NOW).isoformat()
    assert body["as_of"] == india_date(FIXED_NOW).isoformat()


def test_four_creators_are_not_enough_to_say(client, db, brand):
    for price in (100_000, 200_000, 300_000, 400_000):
        pricer(db, price)

    body = guidance(client, brand)

    assert body["creators_counted"] == 4
    assert body["lower_quarter_paise"] is None
    assert body["median_paise"] is None
    assert body["upper_quarter_paise"] is None
    assert body["audience_figures_from"] is None


def test_no_minimum_or_maximum_ever_appears(client, db, brand):
    """Each of those would be one person's price."""
    five_food_creators_in_madurai(db)

    text = client.get(URL, params=REEL_12K, headers=brand.headers).text

    assert "100000" not in text
    assert "500000" not in text
    for forbidden in ("min", "max", "creator_id", "handle"):
        assert forbidden not in text


def test_each_creator_counts_once(client, db, brand):
    """Five packages from one creator do not outweigh four other creators."""
    for price in (100_000, 200_000, 300_000, 400_000):
        pricer(db, price)
    pricer(db, 500_000, 900_000, 900_000, 900_000, 900_000)

    body = guidance(client, brand)

    assert body["creators_counted"] == 5
    # That creator's own median is 900,000, so the upper quarter is 400,000,
    # exactly as if they had one package.
    assert body["upper_quarter_paise"] == 400_000
    assert body["median_paise"] == 300_000


def test_unpublished_prices_are_never_counted(client, db, brand):
    """D-056 decision 1: only creators who chose to show their prices."""
    for price in (100_000, 200_000, 300_000, 400_000):
        pricer(db, price)
    pricer(db, 5_000_000, published=False)

    body = guidance(client, brand)

    assert body["creators_counted"] == 4
    assert body["median_paise"] is None
    assert "5000000" not in str(body)


def test_another_audience_band_is_not_counted(client, db, brand):
    five_food_creators_in_madurai(db)
    pricer(db, 9_000_000, followers=300_000)

    body = guidance(client, brand)

    assert body["creators_counted"] == 5
    assert body["upper_quarter_paise"] == 400_000


def test_the_band_comes_from_the_same_platforms_followers(client, db, brand):
    """A YouTube audience says nothing about an Instagram Reel's price."""
    for price in (100_000, 200_000, 300_000, 400_000, 500_000):
        pricer(db, price, followers=2_000, youtube_followers=20_000)

    body = guidance(client, brand)

    assert body["creators_counted"] == 0


def test_another_format_or_platform_is_not_counted(client, db, brand):
    five_food_creators_in_madurai(db)
    for _ in range(5):
        pricer(db, 50_000, package_format="story")

    reels = guidance(client, brand)
    stories = guidance(client, brand, format="story")
    youtube = guidance(client, brand, platform="youtube", format="reel")

    assert reels["median_paise"] == 300_000
    assert stories["median_paise"] == 50_000
    assert youtube["creators_counted"] == 0


# --- narrowing -------------------------------------------------------------


def test_niche_and_city_narrow_the_answer_when_there_is_enough(client, db, brand):
    five_food_creators_in_madurai(db)
    for _ in range(5):
        pricer(db, 9_000_000, niche="fitness", city="Chennai")

    body = guidance(client, brand, niche="food", city="Madurai")

    assert body["narrowed_to"] == {"niche": "food", "city": "Madurai"}
    assert body["creators_counted"] == 5
    assert body["median_paise"] == 300_000


def test_too_few_in_the_city_widens_to_the_niche_and_says_so(client, db, brand):
    for price in (100_000, 200_000):
        pricer(db, price, city="Madurai")
    for price in (300_000, 400_000, 500_000):
        pricer(db, price, city="Salem")

    body = guidance(client, brand, niche="food", city="Madurai")

    assert body["narrowed_to"] == {"niche": "food", "city": None}
    assert body["creators_counted"] == 5


def test_too_few_in_the_niche_widens_to_everyone_and_says_so(client, db, brand):
    for price in (100_000, 200_000):
        pricer(db, price, niche="food")
    for price in (300_000, 400_000, 500_000):
        pricer(db, price, niche="fitness")

    body = guidance(client, brand, niche="food")

    assert body["narrowed_to"] == {"niche": None, "city": None}
    assert body["creators_counted"] == 5


def test_a_city_matches_however_it_is_typed(client, db, brand):
    five_food_creators_in_madurai(db)

    body = guidance(client, brand, city=" madurai ")

    assert body["narrowed_to"]["city"] == "madurai"
    assert body["creators_counted"] == 5


@pytest.mark.parametrize(
    ("followers", "band"),
    [
        (0, "under_10k"),
        (9_999, "under_10k"),
        (10_000, "10k_50k"),
        (49_999, "10k_50k"),
        (50_000, "50k_100k"),
        (100_000, "100k_500k"),
        (500_000, "500k_plus"),
        (1_000_000_000, "500k_plus"),
    ],
)
def test_audience_bands_have_exact_edges(followers, band):
    assert audience_band(followers)[0] == band


# --- who may read it -------------------------------------------------------


def test_a_creator_can_read_it_too(client, db, clock):
    five_food_creators_in_madurai(db)

    assert guidance(client, creator_user(db, clock))["median_paise"] == 300_000


def test_it_is_not_public(client):
    response = client.get(URL, params=REEL_12K)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


@pytest.mark.parametrize(
    "bad",
    [
        {"platform": "tiktok"},
        {"format": "billboard"},
        {"niche": "astrology"},
        {"followers": -1},
        {"followers": "many"},
        {"city": "x"},
    ],
)
def test_bad_questions_are_refused(client, brand, bad):
    response = client.get(URL, params={**REEL_12K, **bad}, headers=brand.headers)

    assert response.status_code == 422


def test_followers_are_required(client, brand):
    params = {"platform": "instagram", "format": "reel"}

    assert client.get(URL, params=params, headers=brand.headers).status_code == 422


def test_it_is_rate_limited(client, brand):
    limit = int(READ_LIMIT.split()[0])
    for _ in range(limit):
        assert client.get(URL, params=REEL_12K, headers=brand.headers).status_code == 200

    response = client.get(URL, params=REEL_12K, headers=brand.headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"

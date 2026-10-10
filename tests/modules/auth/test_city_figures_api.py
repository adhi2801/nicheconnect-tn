"""City figures for public pages: counts and medians, five or nothing (D-078).

Each test uses a city name of its own, so rows other tests leave in the
database can never change its counts.
"""

import random
import string
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.rate_card import CreatorPackage
from tests.factories import build_campaign, build_creator

PUBLISHED = datetime(2026, 9, 1, tzinfo=UTC)
URL = "/api/v1/cities"


def city_name() -> str:
    return "Testur " + "".join(random.choices(string.ascii_lowercase, k=10))


def creator(
    db: Session,
    city: str,
    *,
    niches: tuple[str, ...] = ("food",),
    published: bool = True,
    reel_price: int | None = None,
    suspended: bool = False,
):
    row = build_creator(
        db,
        handle=f"c{uuid.uuid4().hex[:12]}",
        city=city,
        niches=list(niches),
        passport_published_at=PUBLISHED if published else None,
        rate_card_public_at=PUBLISHED if reel_price is not None else None,
    )
    db.add(row)
    db.flush()
    if reel_price is not None:
        db.add(
            CreatorPackage(
                creator_id=row.id,
                platform="instagram",
                format="reel",
                title="One reel",
                price_paise=reel_price,
                delivery_days=5,
                position=0,
            )
        )
    if suspended:
        account = db.get(Account, row.account_id)
        account.suspended_at = PUBLISHED
        account.suspension_reason = "fake_profile"
    db.flush()
    return row


def figures(client: TestClient, city: str) -> dict:
    response = client.get(f"{URL}/{city}/figures")
    assert response.status_code == 200, response.text
    return response.json()


def niche_count(body: dict, niche: str) -> int | None:
    return next(
        row["creators"] for row in body["creators_by_niche"] if row["niche"] == niche
    )


# --- five or nothing ---------------------------------------------------------------------


def test_four_creators_are_not_enough_to_say(client, db):
    city = city_name()
    for _ in range(4):
        creator(db, city)

    body = figures(client, city)

    assert body["published_creators"] is None
    assert niche_count(body, "food") is None
    assert body["min_count"] == 5


def test_five_creators_are_counted(client, db):
    city = city_name()
    for _ in range(5):
        creator(db, city, niches=("food", "fashion"))

    body = figures(client, city)

    assert body["published_creators"] == 5
    assert niche_count(body, "food") == 5
    assert niche_count(body, "fashion") == 5
    assert niche_count(body, "travel") is None


def test_only_published_and_active_creators_count(client, db):
    city = city_name()
    for _ in range(4):
        creator(db, city)
    creator(db, city, published=False)
    creator(db, city, suspended=True)

    assert figures(client, city)["published_creators"] is None


def test_cities_match_whatever_the_case_or_spaces(client, db):
    city = city_name()
    for spelling in (city, city.upper(), f"  {city}  ", city, city.lower()):
        creator(db, spelling)

    body = figures(client, city.title())

    assert body["published_creators"] == 5
    assert body["city"] == city  # the spelling most creators used


def test_a_city_nobody_has_joined_answers_with_nothing_to_say(client):
    body = figures(client, city_name())

    assert body["published_creators"] is None
    assert body["open_campaigns"] is None
    assert body["asking_prices"] == []


# --- asking prices -------------------------------------------------------------------------


def test_the_median_asking_price_needs_five_published_rate_cards(client, db):
    city = city_name()
    for price in (400_000, 500_000, 600_000, 700_000):
        creator(db, city, reel_price=price)
    creator(db, city)  # published Passport, prices kept private

    assert figures(client, city)["asking_prices"] == []

    creator(db, city, reel_price=2_000_000)
    assert figures(client, city)["asking_prices"] == [
        {
            "platform": "instagram",
            "format": "reel",
            "creators": 5,
            "median_paise": 600_000,
            "currency": "INR",
        }
    ]


# --- open campaigns ------------------------------------------------------------------------


def test_open_campaigns_in_the_city_are_counted_from_five(client, db):
    city = city_name()
    for _ in range(4):
        db.add(build_campaign(db, cities=[city.upper()]))
    db.add(build_campaign(db, cities=[city], status="closed"))
    db.flush()
    assert figures(client, city)["open_campaigns"] is None

    db.add(build_campaign(db, cities=["Madurai", city]))
    db.flush()
    assert figures(client, city)["open_campaigns"] == 5


# --- the list of cities --------------------------------------------------------------------


def test_the_list_holds_only_cities_with_five_creators(client, db):
    big, small = city_name(), city_name()
    for _ in range(5):
        creator(db, big)
    for _ in range(4):
        creator(db, small)

    response = client.get(URL)

    assert response.status_code == 200
    listed = {row["city"]: row["published_creators"] for row in response.json()}
    assert listed.get(big) == 5
    assert small not in listed


# --- caching and refusals ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", "/Coimbatore/figures"])
def test_an_unchanged_answer_costs_nothing_to_read_again(client, path):
    first = client.get(URL + path)
    assert first.headers["Cache-Control"] == "public, max-age=3600"

    again = client.get(URL + path, headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
    assert again.content == b""


def test_no_login_is_needed(client):
    assert client.get(f"{URL}/Coimbatore/figures").status_code == 200


@pytest.mark.parametrize("city", ["C", "Chennai1", "<script>", "a" * 61])
def test_something_that_is_not_a_city_name_is_refused(client, city):
    assert client.get(f"{URL}/{city}/figures").status_code == 422

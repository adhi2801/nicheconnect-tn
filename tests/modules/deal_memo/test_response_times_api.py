"""Typical response times through the API, from real deals (D-077)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)

RRN = "412345678901"


def brand_url(user_id: str) -> str:
    return f"/api/v1/brands/{user_id}/response-times"


def creator_url(user_id: str) -> str:
    return f"/api/v1/creators/{user_id}/response-times"


def profile_id(client: TestClient, user: User) -> str:
    path = "/api/v1/brands/me" if user.role == "brand" else "/api/v1/creators/me"
    return client.get(path, headers=user.headers).json()["id"]


def reviewed_after(
    client: TestClient, clock, brand: User, creator: User, hours: int
) -> str:
    """A deal whose work the brand decided on `hours` after it arrived."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    clock.advance(timedelta(hours=hours))
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    return memo_id


def read(client: TestClient, url: str, user: User) -> dict:
    response = client.get(url, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- a brand -------------------------------------------------------------------------------


def test_a_brands_review_time_is_the_median_of_five_real_decisions(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    for hours in (2, 4, 6, 30, 50):
        reviewed_after(client, clock, brand, creator, hours)

    body = read(client, brand_url(profile_id(client, brand)), creator)

    assert body["work_reviewed"] == {
        "examples": 5,
        "median_hours": 6.0,
        "min_examples": 5,
    }


def test_four_decisions_are_not_enough_to_say(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    for hours in (2, 4, 6, 8):
        reviewed_after(client, clock, brand, creator, hours)

    body = read(client, brand_url(profile_id(client, brand)), brand)

    assert body["work_reviewed"]["examples"] == 4
    assert body["work_reviewed"]["median_hours"] is None


def test_a_new_brand_has_no_examples(client, db, clock):
    brand = brand_user(db, clock)

    body = read(client, brand_url(profile_id(client, brand)), brand)

    assert body["work_reviewed"] == {
        "examples": 0,
        "median_hours": None,
        "min_examples": 5,
    }


def test_an_unknown_brand_is_not_found(client, db, clock):
    response = client.get(
        brand_url("00000000-0000-4000-8000-000000000000"),
        headers=brand_user(db, clock).headers,
    )

    assert response.status_code == 404


# --- a creator -----------------------------------------------------------------------------


@pytest.fixture
def busy_creator(client, db, clock):
    """Five memos answered and five payments confirmed, each after a pause."""
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    for _ in range(5):
        memo_id = reviewed_after(client, clock, brand, creator, 1)
        client.post(
            f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
            json={"method": "upi", "reference": RRN},
            headers=brand.headers,
        )
        clock.advance(timedelta(hours=3))
        confirmed = client.post(
            f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
        )
        assert confirmed.status_code == 200, confirmed.text
    return brand, creator


def test_a_creators_answers_and_confirmations_are_timed(client, busy_creator):
    brand, creator = busy_creator

    body = read(client, creator_url(profile_id(client, creator)), brand)

    # The helper accepts each memo the moment it is sent.
    assert body["memo_answered"]["examples"] == 5
    assert body["memo_answered"]["median_hours"] == 0.0
    assert body["payment_confirmed"] == {
        "examples": 5,
        "median_hours": 3.0,
        "min_examples": 5,
    }


def test_a_creator_can_read_their_own(client, busy_creator):
    _, creator = busy_creator

    read(client, creator_url(profile_id(client, creator)), creator)


def test_another_creator_cannot_read_them(client, db, clock, busy_creator):
    _, creator = busy_creator
    other = creator_user(db, clock)

    response = client.get(creator_url(profile_id(client, creator)), headers=other.headers)

    assert response.status_code == 403


def test_an_unknown_creator_is_not_found_for_a_brand(client, db, clock):
    response = client.get(
        creator_url("00000000-0000-4000-8000-000000000000"),
        headers=brand_user(db, clock).headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize("url", [brand_url, creator_url])
def test_it_needs_a_login(client, url):
    assert client.get(url("00000000-0000-4000-8000-000000000000")).status_code == 401


@pytest.mark.parametrize("url", [brand_url, creator_url])
def test_a_malformed_id_is_refused(client, db, clock, url):
    response = client.get(url("not-an-id"), headers=brand_user(db, clock).headers)

    assert response.status_code == 422

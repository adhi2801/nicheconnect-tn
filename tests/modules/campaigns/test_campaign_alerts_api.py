"""A creator's campaign alerts, through the API (item 43, D-130)."""

from datetime import timedelta

import pytest

from app.modules.auth.models.account import Account
from app.modules.campaigns.alert_models import MAX_ALERTS_PER_CREATOR
from app.modules.campaigns.alert_router import URL, WRITE_LIMIT
from app.modules.me import export_service
from tests.deal_flow import User, brand_user, creator_user


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def save(client, creator: User, **terms) -> dict:
    response = client.post(URL, json=terms, headers=creator.headers)
    assert response.status_code == 201, response.text
    return response.json()


def mine(client, creator: User) -> list[dict]:
    response = client.get(URL, headers=creator.headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def test_a_creator_saves_an_alert_and_sees_it(client, creator):
    response = client.post(
        URL,
        json={"city": "  Madurai ", "niche": "food", "min_budget_paise": 500_000},
        headers=creator.headers,
    )

    assert response.status_code == 201, response.text
    saved = response.json()
    assert {
        k: saved[k] for k in ("city", "niche", "campaign_type", "min_budget_paise")
    } == {
        "city": "Madurai",
        "niche": "food",
        "campaign_type": None,
        "min_budget_paise": 500_000,
    }
    assert saved["currency"] == "INR"
    assert response.headers["Location"] == URL
    assert mine(client, creator) == [saved]


def test_alerts_come_newest_first(client, clock, creator):
    first = save(client, creator, city="Madurai")
    clock.advance(timedelta(minutes=1))
    second = save(client, creator, niche="tech")

    assert [a["id"] for a in mine(client, creator)] == [second["id"], first["id"]]


def test_the_same_terms_twice_are_refused_a_city_in_any_case(client, creator):
    save(client, creator, city="Madurai", niche="food")

    assert_problem(
        client.post(
            URL, json={"city": "MADURAI", "niche": "food"}, headers=creator.headers
        ),
        409,
        "campaign_alert_exists",
    )
    save(client, creator, city="Madurai")  # fewer terms are other terms


def test_another_creator_may_save_the_same_terms(client, db, clock, creator):
    save(client, creator, niche="food")

    save(client, creator_user(db, clock), niche="food")


def test_the_sixth_alert_is_refused(client, creator):
    niches = ["food", "fashion", "beauty", "tech", "travel", "fitness"]
    for niche in niches[:MAX_ALERTS_PER_CREATOR]:
        save(client, creator, niche=niche)

    assert_problem(
        client.post(URL, json={"niche": niches[-1]}, headers=creator.headers),
        409,
        "campaign_alerts_full",
    )
    assert len(mine(client, creator)) == MAX_ALERTS_PER_CREATOR


def test_removing_an_alert_leaves_the_others(client, creator):
    gone, kept = save(client, creator, niche="food"), save(client, creator, niche="tech")

    response = client.delete(f"{URL}/{gone['id']}", headers=creator.headers)

    assert response.status_code == 204
    assert mine(client, creator) == [kept]
    assert_problem(
        client.delete(f"{URL}/{gone['id']}", headers=creator.headers),
        404,
        "campaign_alert_not_found",
    )


def test_another_creators_alert_is_not_found(client, db, clock, creator):
    theirs = save(client, creator, niche="food")
    other = creator_user(db, clock)

    assert_problem(
        client.delete(f"{URL}/{theirs['id']}", headers=other.headers),
        404,
        "campaign_alert_not_found",
    )
    assert mine(client, other) == []
    assert mine(client, creator) == [theirs]


def test_brands_keep_no_alerts(client, db, clock):
    brand = brand_user(db, clock)

    assert client.get(URL, headers=brand.headers).status_code == 403
    assert (
        client.post(URL, json={"niche": "food"}, headers=brand.headers).status_code == 403
    )


def test_alerts_need_a_login(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"niche": "food"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"city": None, "niche": None},
        {"niche": "astrology"},
        {"campaign_type": "lottery"},
        {"city": "M"},
        {"city": "x" * 61},
        {"min_budget_paise": 0},
        {"campaign_type": "barter", "min_budget_paise": 100_000},
        {"niche": "food", "extra": 1},
    ],
)
def test_a_bad_alert_is_refused(client, creator, body):
    assert client.post(URL, json=body, headers=creator.headers).status_code == 422


def test_a_retry_with_the_same_key_saves_one_alert(client, creator):
    headers = {**creator.headers, "Idempotency-Key": "alert-retry-1"}

    first = client.post(URL, json={"niche": "food"}, headers=headers)
    second = client.post(URL, json={"niche": "food"}, headers=headers)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert len(mine(client, creator)) == 1


def test_saving_is_rate_limited(client, creator):
    niches = ["food", "fashion", "beauty", "tech", "travel"]
    for n in range(int(WRITE_LIMIT.split()[0])):
        # Past the cap each answers 409; the limit still counts them.
        client.post(
            URL,
            json={"niche": niches[n % 5], "city": f"City {n}"},
            headers=creator.headers,
        )

    assert (
        client.post(URL, json={"niche": "food"}, headers=creator.headers).status_code
        == 429
    )


def test_the_creators_export_holds_their_alerts(client, db, clock, creator):
    saved = save(client, creator, city="Madurai", niche="food")
    brand = brand_user(db, clock)

    theirs = export_service.build_export(
        db, db.get_one(Account, creator.account_id), clock.now
    )["data"]["campaign_alerts"]
    brands = export_service.build_export(
        db, db.get_one(Account, brand.account_id), clock.now
    )["data"]["campaign_alerts"]

    assert [(a["id"], a["city"], a["niche"]) for a in theirs] == [
        (saved["id"], "Madurai", "food")
    ]
    assert brands == []

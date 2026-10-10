"""A creator's availability, "booked until 20 Nov" (D-083).

FIXED_NOW is 12:00 UTC on 17 September 2026, 17:30 in Tamil Nadu, so "today"
is 17 September unless a test moves the clock.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.auth import availability_service as service
from app.modules.auth.availability_router import WRITE_LIMIT
from app.modules.auth.models.creator import Creator
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import create_account

URL = "/api/v1/creators/me/availability"
TODAY = date(2026, 9, 17)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def put(client, user: User, booked_until):
    value = None if booked_until is None else booked_until.isoformat()
    return client.put(URL, json={"booked_until": value}, headers=user.headers)


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- the rule, without a database --------------------------------------------------------


@pytest.mark.parametrize(
    ("booked_until", "shown", "available_from"),
    [
        (None, None, TODAY),
        (TODAY - timedelta(days=1), None, TODAY),  # passed: taking work again
        (TODAY, TODAY, TODAY + timedelta(days=1)),  # booked through today
        (date(2026, 11, 20), date(2026, 11, 20), date(2026, 11, 21)),
    ],
)
def test_what_a_date_means_today(booked_until, shown, available_from):
    assert service.booked_until_shown(booked_until, TODAY) == shown
    assert service.available_from(booked_until, TODAY) == available_from


# --- the creator's own setting -------------------------------------------------------------


def test_a_new_creator_is_taking_work_from_today(client, creator):
    response = client.get(URL, headers=creator.headers)

    assert response.status_code == 200
    assert response.json() == {"booked_until": None, "available_from": "2026-09-17"}


def test_booked_until_is_set_and_read_back(client, db, creator):
    response = put(client, creator, date(2026, 11, 20))

    assert response.status_code == 200
    assert response.json() == {
        "booked_until": "2026-11-20",
        "available_from": "2026-11-21",
    }
    assert client.get(URL, headers=creator.headers).json()["booked_until"] == "2026-11-20"


def test_clearing_it_means_taking_work(client, creator):
    put(client, creator, date(2026, 11, 20))

    response = put(client, creator, None)

    assert response.json() == {"booked_until": None, "available_from": "2026-09-17"}


def test_once_the_date_passes_it_reads_as_taking_work(client, clock, creator):
    put(client, creator, date(2026, 9, 20))

    clock.advance(timedelta(days=4))  # 21 September
    response = client.get(URL, headers=creator.headers)

    assert response.json() == {"booked_until": None, "available_from": "2026-09-21"}


def test_today_and_a_year_ahead_are_the_limits(client, creator):
    assert put(client, creator, TODAY).status_code == 200
    assert put(client, creator, TODAY + timedelta(days=365)).status_code == 200


@pytest.mark.parametrize(
    "booked_until",
    [TODAY - timedelta(days=1), TODAY + timedelta(days=366)],
    ids=["yesterday", "a year and a day ahead"],
)
def test_a_date_outside_the_limits_is_refused(client, db, creator, booked_until):
    response = put(client, creator, booked_until)

    assert_problem(response, 422, "invalid_availability")
    row = db.query(Creator).filter_by(account_id=creator.account_id).one()
    assert row.booked_until is None


def test_today_is_the_tamil_nadu_day_not_the_server_day(client, clock, creator):
    # 20:00 UTC on 17 September is 01:30 on the 18th in Tamil Nadu: the 17th
    # has already gone for the creator, though not for a UTC server.
    clock.now = datetime(2026, 9, 17, 20, 0, tzinfo=UTC)

    assert_problem(put(client, creator, date(2026, 9, 17)), 422, "invalid_availability")
    assert put(client, creator, date(2026, 9, 18)).status_code == 200


def test_unknown_fields_are_refused(client, creator):
    response = client.put(
        URL,
        json={"booked_until": None, "reason": "wedding"},
        headers=creator.headers,
    )

    assert response.status_code == 422


def test_it_is_in_the_creators_own_export(client, creator):
    put(client, creator, date(2026, 11, 20))

    export = client.get("/api/v1/me/export", headers=creator.headers).json()

    [profile] = export["data"]["creator_profile"]
    assert profile["booked_until"] == "2026-11-20"


# --- who may ---------------------------------------------------------------------------------


def test_a_brand_cannot_have_availability(client, db, clock):
    brand = brand_user(db, clock)

    assert client.get(URL, headers=brand.headers).status_code == 403
    assert put(client, brand, TODAY).status_code == 403


def test_a_creator_without_a_profile_is_told_so(client, db, clock):
    account = create_account(db, "creator")
    user = User(account.id, "creator", clock)

    assert client.get(URL, headers=user.headers).status_code == 404


def test_without_a_token_it_is_refused(client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"booked_until": None}).status_code == 401


def test_setting_it_is_rate_limited(client, creator):
    allowed = int(WRITE_LIMIT.split()[0])
    answers = [put(client, creator, None).status_code for _ in range(allowed + 1)]

    assert answers[:allowed] == [200] * allowed
    assert answers[allowed] == 429

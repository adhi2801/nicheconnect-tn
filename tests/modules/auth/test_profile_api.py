from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.auth.tokens import create_access_token
from tests.factories import FIXED_NOW, create_account

BRAND_URL = "/api/v1/brands/me"
CREATOR_URL = "/api/v1/creators/me"
CAMPAIGNS_URL = "/api/v1/campaigns"
# FIXED_NOW is 17 September 2026 in Tamil Nadu.
ADULT = "1999-04-14"


@pytest.fixture
def now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def client(db, now) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def login(db, now, role: str) -> dict[str, str]:
    account = create_account(db, role)
    token, _ = create_access_token(account.id, role, now)
    return {"Authorization": f"Bearer {token}"}


def brand_body(**overrides) -> dict:
    body = {"name": "Amma Sweets", "email": "hello@ammasweets.in", "date_of_birth": ADULT}
    body.update(overrides)
    return body


def creator_body(**overrides) -> dict:
    body = {
        "display_name": "Priya Eats",
        "handle": "priya.eats",
        "city": "Coimbatore",
        "niches": ["food", "travel"],
        "bio": "Street food across Tamil Nadu.",
        "date_of_birth": ADULT,
    }
    body.update(overrides)
    return body


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- brand profile -------------------------------------------------------


def test_brand_creates_reads_and_changes_its_profile(client, db, now):
    headers = login(db, now, "brand")

    created = client.post(BRAND_URL, json=brand_body(), headers=headers)
    read = client.get(BRAND_URL, headers=headers)
    changed = client.patch(BRAND_URL, json={"name": "Amma Sweets & Co"}, headers=headers)

    assert created.status_code == 201
    assert created.headers["location"] == BRAND_URL
    assert read.json() == created.json()
    assert changed.json()["name"] == "Amma Sweets & Co"
    assert changed.json()["email"] == "hello@ammasweets.in"


def test_brand_email_is_stored_lowercase(client, db, now):
    headers = login(db, now, "brand")

    response = client.post(
        BRAND_URL, json=brand_body(email="  Hello@AmmaSweets.IN "), headers=headers
    )

    assert response.json()["email"] == "hello@ammasweets.in"


def test_reading_before_creating_says_so(client, db, now):
    assert_problem(
        client.get(BRAND_URL, headers=login(db, now, "brand")), 404, "profile_not_found"
    )


def test_second_brand_profile_is_refused(client, db, now):
    headers = login(db, now, "brand")
    client.post(BRAND_URL, json=brand_body(), headers=headers)

    assert_problem(
        client.post(
            BRAND_URL, json=brand_body(email="other@example.com"), headers=headers
        ),
        409,
        "profile_exists",
    )


def test_email_already_used_by_another_brand_is_refused(client, db, now):
    client.post(BRAND_URL, json=brand_body(), headers=login(db, now, "brand"))

    assert_problem(
        client.post(BRAND_URL, json=brand_body(), headers=login(db, now, "brand")),
        409,
        "email_taken",
    )


def test_changing_to_a_taken_email_is_refused(client, db, now):
    client.post(BRAND_URL, json=brand_body(), headers=login(db, now, "brand"))
    second = login(db, now, "brand")
    client.post(BRAND_URL, json=brand_body(email="second@example.com"), headers=second)

    assert_problem(
        client.patch(BRAND_URL, json={"email": "hello@ammasweets.in"}, headers=second),
        409,
        "email_taken",
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "", "email": "a@b.com"}, "name"),
        ({"name": "n" * 151, "email": "a@b.com"}, "name"),
        ({"name": "n", "email": "not-an-email"}, "email"),
        ({"name": "n"}, "email"),
        ({"name": "n", "email": "a@b.com", "id": "sneaky"}, "id"),
    ],
)
def test_invalid_brand_profile_is_rejected(client, db, now, body, field):
    problem = assert_problem(
        client.post(BRAND_URL, json=body, headers=login(db, now, "brand")),
        422,
        "validation_failed",
    )
    assert field in [error["field"] for error in problem["errors"]]


def test_creator_cannot_use_the_brand_profile_endpoints(client, db, now):
    headers = login(db, now, "creator")

    assert_problem(
        client.post(BRAND_URL, json=brand_body(), headers=headers),
        403,
        "role_not_allowed",
    )
    assert_problem(client.get(BRAND_URL, headers=headers), 403, "role_not_allowed")


def test_brand_profile_needs_a_token(client):
    assert_problem(client.get(BRAND_URL), 401, "invalid_token")


# --- creator profile -----------------------------------------------------


def test_creator_creates_reads_and_changes_its_profile(client, db, now):
    headers = login(db, now, "creator")

    created = client.post(CREATOR_URL, json=creator_body(), headers=headers)
    read = client.get(CREATOR_URL, headers=headers)
    changed = client.patch(
        CREATOR_URL, json={"city": "Madurai", "bio": None}, headers=headers
    )

    assert created.status_code == 201
    assert created.json()["languages"] == ["en"]
    assert read.json() == created.json()
    assert changed.json()["city"] == "Madurai"
    assert changed.json()["bio"] is None


@pytest.mark.parametrize("typed", ["@Priya.Eats", " priya.eats ", "PRIYA.EATS"])
def test_handle_is_cleaned_up(client, db, now, typed):
    response = client.post(
        CREATOR_URL, json=creator_body(handle=typed), headers=login(db, now, "creator")
    )

    assert response.json()["handle"] == "priya.eats"


def test_handle_already_taken_is_refused(client, db, now):
    client.post(CREATOR_URL, json=creator_body(), headers=login(db, now, "creator"))

    assert_problem(
        client.post(CREATOR_URL, json=creator_body(), headers=login(db, now, "creator")),
        409,
        "handle_taken",
    )


def test_changing_to_a_taken_handle_is_refused(client, db, now):
    client.post(CREATOR_URL, json=creator_body(), headers=login(db, now, "creator"))
    second = login(db, now, "creator")
    client.post(CREATOR_URL, json=creator_body(handle="second.creator"), headers=second)

    assert_problem(
        client.patch(CREATOR_URL, json={"handle": "priya.eats"}, headers=second),
        409,
        "handle_taken",
    )


def test_second_creator_profile_is_refused(client, db, now):
    headers = login(db, now, "creator")
    client.post(CREATOR_URL, json=creator_body(), headers=headers)

    assert_problem(
        client.post(
            CREATOR_URL, json=creator_body(handle="another.one"), headers=headers
        ),
        409,
        "profile_exists",
    )


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"handle": "ab"}, "handle"),
        ({"handle": "has space"}, "handle"),
        ({"display_name": ""}, "display_name"),
        ({"niches": []}, "niches"),
        ({"niches": ["gaming"]}, "niches"),
        ({"languages": ["ta"]}, "languages"),
        ({"bio": "b" * 501}, "bio"),
        ({"city": "M"}, "city"),
    ],
)
def test_invalid_creator_profile_is_rejected(client, db, now, body, field):
    problem = assert_problem(
        client.post(
            CREATOR_URL, json=creator_body(**body), headers=login(db, now, "creator")
        ),
        422,
        "validation_failed",
    )
    reported = [error["field"] for error in problem["errors"]]
    assert any(name == field or name.startswith(f"{field}.") for name in reported), (
        reported
    )


def test_brand_cannot_use_the_creator_profile_endpoints(client, db, now):
    assert_problem(
        client.post(CREATOR_URL, json=creator_body(), headers=login(db, now, "brand")),
        403,
        "role_not_allowed",
    )


def test_empty_update_is_rejected(client, db, now):
    headers = login(db, now, "creator")
    client.post(CREATOR_URL, json=creator_body(), headers=headers)

    assert_problem(
        client.patch(CREATOR_URL, json={}, headers=headers), 422, "validation_failed"
    )


def test_profiles_belong_to_their_own_account(client, db, now):
    first = login(db, now, "creator")
    second = login(db, now, "creator")
    client.post(CREATOR_URL, json=creator_body(), headers=first)
    client.post(CREATOR_URL, json=creator_body(handle="second.creator"), headers=second)

    first_profile = client.get(CREATOR_URL, headers=first).json()
    second_profile = client.get(CREATOR_URL, headers=second).json()

    assert first_profile["handle"] == "priya.eats"
    assert second_profile["handle"] == "second.creator"
    assert first_profile["account_id"] != second_profile["account_id"]


# --- the gap this closes -------------------------------------------------


def test_brand_can_post_a_campaign_right_after_creating_its_profile(client, db, now):
    headers = login(db, now, "brand")
    client.post(BRAND_URL, json=brand_body(), headers=headers)

    response = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Pongal sweets launch",
            "description": "Three reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "3 Instagram reels",
        },
        headers=headers,
    )

    assert response.status_code == 201
    brand = db.scalars(select(Brand).where(Brand.email == brand_body()["email"])).one()
    assert response.json()["brand_id"] == str(brand.id)


def test_profile_rows_match_what_the_api_returned(client, db, now):
    headers = login(db, now, "creator")
    body = client.post(CREATOR_URL, json=creator_body(), headers=headers).json()

    stored = db.get(Creator, body["id"])
    assert stored.handle == body["handle"]
    assert stored.niches == body["niches"]


# --- adults only (D-086) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("born", "allowed"),
    [
        ("2008-09-17", True),  # 18 today, in Tamil Nadu
        ("2008-09-18", False),  # 18 tomorrow
        ("2012-01-01", False),
        ("1960-05-05", True),
    ],
)
@pytest.mark.parametrize("role", ["brand", "creator"])
def test_only_adults_create_a_profile(client, db, now, role, born, allowed):
    url, body = (
        (BRAND_URL, brand_body) if role == "brand" else (CREATOR_URL, creator_body)
    )

    response = client.post(
        url, json=body(date_of_birth=born), headers=login(db, now, role)
    )

    if allowed:
        assert response.status_code == 201, response.text
    else:
        assert_problem(response, 422, "must_be_18_or_over")


def test_the_day_is_the_tamil_nadu_day(client, db):
    # 20:00 UTC on 16 September is already the 17th in Tamil Nadu.
    late = FIXED_NOW.replace(day=16, hour=20)
    app.dependency_overrides[get_now] = lambda: late

    response = client.post(
        CREATOR_URL,
        json=creator_body(date_of_birth="2008-09-17"),
        headers=login(db, late, "creator"),
    )

    assert response.status_code == 201, response.text


def test_a_date_of_birth_is_required(client, db, now):
    body = creator_body()
    del body["date_of_birth"]

    response = client.post(CREATOR_URL, json=body, headers=login(db, now, "creator"))

    assert response.status_code == 422


def test_only_the_confirmation_is_kept_never_the_date(client, db, now):
    from app.modules.auth.models.account import Account

    headers = login(db, now, "creator")
    client.post(CREATOR_URL, json=creator_body(), headers=headers)

    account = db.scalars(
        select(Account).join(Creator, Creator.account_id == Account.id)
    ).first()
    exported = client.get("/api/v1/me/export", headers=headers).text
    columns = {column.name for column in Account.__table__.columns} | {
        column.name for column in Creator.__table__.columns
    }

    assert account is not None and account.adult_confirmed_at == now
    assert not any("birth" in name for name in columns)
    assert "1999-04-14" not in exported


def test_someone_refused_for_age_is_not_marked_adult(client, db, now):
    from app.modules.auth.models.account import Account

    account = create_account(db, "creator")
    token, _ = create_access_token(account.id, "creator", now)

    client.post(
        CREATOR_URL,
        json=creator_body(date_of_birth="2012-01-01"),
        headers={"Authorization": f"Bearer {token}"},
    )

    confirmed = db.scalar(
        select(Account.id).where(
            Account.id == account.id, Account.adult_confirmed_at.is_not(None)
        )
    )
    assert confirmed is None


@pytest.mark.parametrize(
    ("born", "today", "adult"),
    [
        ("2008-02-29", "2026-02-28", False),
        ("2008-02-29", "2026-03-01", True),
        ("2008-03-01", "2026-03-01", True),
    ],
)
def test_a_leap_day_birthday_turns_18_on_1_march(born, today, adult):
    from datetime import date

    from app.modules.auth.profiles import is_adult

    assert is_adult(date.fromisoformat(born), date.fromisoformat(today)) is adult

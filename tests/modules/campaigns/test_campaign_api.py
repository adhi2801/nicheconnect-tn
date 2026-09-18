from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.models.brand import Brand
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Campaign
from tests.factories import FIXED_NOW, build_brand, create_account

URL = "/api/v1/campaigns"
DISCOVER_URL = f"{URL}/discover"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def clock() -> Clock:
    return Clock(FIXED_NOW)


@pytest.fixture
def client(db, clock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_now] = lambda: clock.now
    limiter.reset()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def brand_login(db, clock) -> tuple[Brand, dict[str, str]]:
    """A brand account with a profile, plus its Authorization header."""
    brand = build_brand(db)
    # Unique per brand: the email column is unique across the table.
    brand.email = f"brand-{brand.account_id}@example.com"
    db.add(brand)
    db.flush()
    token, _ = create_access_token(brand.account_id, "brand", clock.now)
    return brand, {"Authorization": f"Bearer {token}"}


def creator_login(db, clock) -> dict[str, str]:
    account = create_account(db, "creator")
    token, _ = create_access_token(account.id, "creator", clock.now)
    return {"Authorization": f"Bearer {token}"}


def valid_body(**overrides) -> dict:
    body = {
        "title": "Pongal sweets launch",
        "description": "Three reels featuring our new sweet box.",
        "campaign_type": "paid",
        "budget_min_paise": 500_000,
        "budget_max_paise": 1_500_000,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "3 Instagram reels",
    }
    body.update(overrides)
    return body


def create(client, headers, **overrides) -> dict:
    response = client.post(URL, json=valid_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def publish(client, headers, campaign_id: str) -> dict:
    response = client.post(f"{URL}/{campaign_id}/publish", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- create --------------------------------------------------------------


def test_brand_creates_a_draft_campaign(client, db, clock):
    brand, headers = brand_login(db, clock)

    response = client.post(URL, json=valid_body(), headers=headers)

    assert response.status_code == 201
    assert response.headers["location"] == f"{URL}/{response.json()['id']}"
    body = response.json()
    assert body["status"] == "draft"
    assert body["brand_id"] == str(brand.id)
    assert body["currency"] == "INR"
    assert body["budget_min_paise"] == 500_000


def test_creator_cannot_create_a_campaign(client, db, clock):
    assert_problem(
        client.post(URL, json=valid_body(), headers=creator_login(db, clock)),
        403,
        "role_not_allowed",
    )


def test_campaign_needs_a_signed_in_account(client):
    assert_problem(client.post(URL, json=valid_body()), 401, "invalid_token")


def test_brand_without_a_profile_is_told_to_create_one(client, db, clock):
    account = create_account(db, "brand")
    token, _ = create_access_token(account.id, "brand", clock.now)

    assert_problem(
        client.post(URL, json=valid_body(), headers={"Authorization": f"Bearer {token}"}),
        409,
        "brand_profile_required",
    )


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"title": ""}, "title"),
        ({"title": "t" * 121}, "title"),
        ({"cities": []}, "cities"),
        ({"niches": ["gaming"]}, "niches"),
        ({"campaign_type": "gift"}, "campaign_type"),
        ({"budget_min_paise": -1}, "budget_min_paise"),
        ({"description": "d" * 4001}, "description"),
    ],
)
def test_invalid_campaign_fields_are_rejected(client, db, clock, overrides, field):
    _, headers = brand_login(db, clock)

    problem = assert_problem(
        client.post(URL, json=valid_body(**overrides), headers=headers),
        422,
        "validation_failed",
    )
    # List fields report the exact entry, e.g. "niches.0".
    reported = [error["field"] for error in problem["errors"]]
    assert any(name == field or name.startswith(f"{field}.") for name in reported), reported


def test_barter_campaign_with_a_budget_is_rejected_with_a_readable_message(client, db, clock):
    _, headers = brand_login(db, clock)

    problem = assert_problem(
        client.post(URL, json=valid_body(campaign_type="barter"), headers=headers),
        422,
        "validation_failed",
    )
    assert problem["errors"][0]["message"] == (
        "A barter campaign pays in goods, so it has no budget"
    )


def test_unknown_field_is_rejected(client, db, clock):
    _, headers = brand_login(db, clock)

    assert_problem(
        client.post(URL, json=valid_body(status="open"), headers=headers),
        422,
        "validation_failed",
    )


# --- read and visibility -------------------------------------------------


def test_owner_can_read_their_draft(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)

    response = client.get(f"{URL}/{campaign['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == campaign["id"]


def test_creator_cannot_see_a_draft(client, db, clock):
    _, brand_headers = brand_login(db, clock)
    campaign = create(client, brand_headers)

    assert_problem(
        client.get(f"{URL}/{campaign['id']}", headers=creator_login(db, clock)),
        404,
        "campaign_not_found",
    )


def test_creator_can_read_an_open_campaign(client, db, clock):
    _, brand_headers = brand_login(db, clock)
    campaign = publish(client, brand_headers, create(client, brand_headers)["id"])

    response = client.get(f"{URL}/{campaign['id']}", headers=creator_login(db, clock))

    assert response.status_code == 200
    assert response.json()["status"] == "open"


def test_another_brand_cannot_see_a_draft(client, db, clock):
    _, first_headers = brand_login(db, clock)
    campaign = create(client, first_headers)
    _, second_headers = brand_login(db, clock)

    assert_problem(
        client.get(f"{URL}/{campaign['id']}", headers=second_headers),
        404,
        "campaign_not_found",
    )


def test_unknown_campaign_is_not_found(client, db, clock):
    import uuid

    _, headers = brand_login(db, clock)

    assert_problem(
        client.get(f"{URL}/{uuid.uuid4()}", headers=headers), 404, "campaign_not_found"
    )


# --- status transitions --------------------------------------------------


def test_publish_makes_a_draft_open(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)

    assert publish(client, headers, campaign["id"])["status"] == "open"


def test_publishing_twice_is_a_conflict(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = publish(client, headers, create(client, headers)["id"])

    assert_problem(
        client.post(f"{URL}/{campaign['id']}/publish", headers=headers),
        409,
        "campaign_status_conflict",
    )


def test_close_needs_an_open_campaign(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)

    assert_problem(
        client.post(f"{URL}/{campaign['id']}/close", headers=headers),
        409,
        "campaign_status_conflict",
    )


def test_open_campaign_can_be_closed(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = publish(client, headers, create(client, headers)["id"])

    response = client.post(f"{URL}/{campaign['id']}/close", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


@pytest.mark.parametrize("publish_first", [False, True])
def test_draft_and_open_campaigns_can_be_cancelled(client, db, clock, publish_first):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)
    if publish_first:
        publish(client, headers, campaign["id"])

    response = client.post(f"{URL}/{campaign['id']}/cancel", headers=headers)

    assert response.json()["status"] == "cancelled"


def test_closed_campaign_cannot_be_cancelled_or_reopened(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = publish(client, headers, create(client, headers)["id"])
    client.post(f"{URL}/{campaign['id']}/close", headers=headers)

    for action in ("cancel", "publish"):
        assert_problem(
            client.post(f"{URL}/{campaign['id']}/{action}", headers=headers),
            409,
            "campaign_status_conflict",
        )


def test_another_brand_cannot_publish_your_campaign(client, db, clock):
    _, first_headers = brand_login(db, clock)
    campaign = create(client, first_headers)
    _, second_headers = brand_login(db, clock)

    assert_problem(
        client.post(f"{URL}/{campaign['id']}/publish", headers=second_headers),
        404,
        "campaign_not_found",
    )


# --- update --------------------------------------------------------------


def test_draft_can_be_changed_completely(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)

    response = client.patch(
        f"{URL}/{campaign['id']}",
        json={"title": "New title", "budget_min_paise": 100_000, "budget_max_paise": 200_000},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New title"
    assert response.json()["budget_min_paise"] == 100_000


def test_open_campaign_allows_only_safe_changes(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = publish(client, headers, create(client, headers)["id"])

    allowed = client.patch(
        f"{URL}/{campaign['id']}", json={"description": "Updated brief"}, headers=headers
    )
    blocked = client.patch(
        f"{URL}/{campaign['id']}", json={"budget_min_paise": 100_000}, headers=headers
    )

    assert allowed.status_code == 200
    assert allowed.json()["description"] == "Updated brief"
    problem = assert_problem(blocked, 409, "field_not_editable_now")
    assert "budget_min_paise" in problem["detail"]


def test_closed_campaign_cannot_be_changed(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = publish(client, headers, create(client, headers)["id"])
    client.post(f"{URL}/{campaign['id']}/close", headers=headers)

    assert_problem(
        client.patch(f"{URL}/{campaign['id']}", json={"description": "x"}, headers=headers),
        409,
        "campaign_not_editable",
    )


def test_empty_update_is_rejected(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)

    assert_problem(
        client.patch(f"{URL}/{campaign['id']}", json={}, headers=headers),
        422,
        "validation_failed",
    )


def test_another_brand_cannot_change_your_campaign(client, db, clock):
    _, first_headers = brand_login(db, clock)
    campaign = create(client, first_headers)
    _, second_headers = brand_login(db, clock)

    assert_problem(
        client.patch(
            f"{URL}/{campaign['id']}", json={"description": "mine now"}, headers=second_headers
        ),
        404,
        "campaign_not_found",
    )


# --- my list -------------------------------------------------------------


def test_my_list_shows_only_my_campaigns(client, db, clock):
    _, mine = brand_login(db, clock)
    create(client, mine)
    create(client, mine, title="Second")
    _, theirs = brand_login(db, clock)
    create(client, theirs, title="Not mine")

    response = client.get(URL, headers=mine)

    titles = [item["title"] for item in response.json()["items"]]
    assert sorted(titles) == ["Pongal sweets launch", "Second"]
    assert response.json()["next_cursor"] is None


def test_my_list_can_filter_by_status(client, db, clock):
    _, headers = brand_login(db, clock)
    create(client, headers, title="Still a draft")
    publish(client, headers, create(client, headers, title="Live one")["id"])

    response = client.get(URL, params={"status": "open"}, headers=headers)

    assert [item["title"] for item in response.json()["items"]] == ["Live one"]


def test_my_list_pages_through_results(client, db, clock):
    _, headers = brand_login(db, clock)
    for index in range(5):
        clock.advance(timedelta(minutes=1))
        create(client, headers, title=f"Campaign {index}")

    first = client.get(URL, params={"limit": 2}, headers=headers).json()
    second = client.get(
        URL, params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers
    ).json()
    third = client.get(
        URL, params={"limit": 2, "cursor": second["next_cursor"]}, headers=headers
    ).json()

    titles = [item["title"] for page in (first, second, third) for item in page["items"]]
    assert titles == ["Campaign 4", "Campaign 3", "Campaign 2", "Campaign 1", "Campaign 0"]
    assert third["next_cursor"] is None


def test_invalid_cursor_is_rejected(client, db, clock):
    _, headers = brand_login(db, clock)

    assert_problem(
        client.get(URL, params={"cursor": "not-a-cursor"}, headers=headers),
        422,
        "invalid_cursor",
    )


@pytest.mark.parametrize("limit", [0, 101])
def test_limit_outside_the_allowed_range_is_rejected(client, db, clock, limit):
    _, headers = brand_login(db, clock)

    assert_problem(
        client.get(URL, params={"limit": limit}, headers=headers), 422, "validation_failed"
    )


# --- discover ------------------------------------------------------------


def test_discover_shows_only_open_campaigns(client, db, clock):
    _, brand_headers = brand_login(db, clock)
    create(client, brand_headers, title="Draft one")
    publish(client, brand_headers, create(client, brand_headers, title="Open one")["id"])

    response = client.get(DISCOVER_URL, headers=creator_login(db, clock))

    assert [item["title"] for item in response.json()["items"]] == ["Open one"]


def test_discover_filters_combine(client, db, clock):
    _, headers = brand_login(db, clock)
    publish(
        client,
        headers,
        create(client, headers, title="Madurai food", cities=["Madurai"], niches=["food"])["id"],
    )
    publish(
        client,
        headers,
        create(client, headers, title="Chennai tech", cities=["Chennai"], niches=["tech"])["id"],
    )
    creator = creator_login(db, clock)

    by_city = client.get(DISCOVER_URL, params={"city": "Madurai"}, headers=creator).json()
    by_niche = client.get(DISCOVER_URL, params={"niche": "tech"}, headers=creator).json()
    combined = client.get(
        DISCOVER_URL, params={"city": "Madurai", "niche": "tech"}, headers=creator
    ).json()

    assert [item["title"] for item in by_city["items"]] == ["Madurai food"]
    assert [item["title"] for item in by_niche["items"]] == ["Chennai tech"]
    assert combined["items"] == []


def test_discover_filters_by_minimum_budget(client, db, clock):
    _, headers = brand_login(db, clock)
    publish(
        client,
        headers,
        create(client, headers, title="Small", budget_min_paise=100_000, budget_max_paise=200_000)["id"],
    )
    publish(
        client,
        headers,
        create(client, headers, title="Big", budget_min_paise=900_000, budget_max_paise=1_500_000)["id"],
    )

    response = client.get(
        DISCOVER_URL, params={"min_budget_paise": 500_000}, headers=creator_login(db, clock)
    )

    assert [item["title"] for item in response.json()["items"]] == ["Big"]


def test_discover_needs_a_signed_in_account(client):
    assert_problem(client.get(DISCOVER_URL), 401, "invalid_token")


def test_discover_rejects_an_unknown_niche(client, db, clock):
    assert_problem(
        client.get(DISCOVER_URL, params={"niche": "gaming"}, headers=creator_login(db, clock)),
        422,
        "validation_failed",
    )


def test_campaign_rows_are_left_untouched_by_reads(client, db, clock):
    _, headers = brand_login(db, clock)
    campaign = create(client, headers)
    client.get(f"{URL}/{campaign['id']}", headers=headers)

    stored = db.get(Campaign, campaign["id"])
    assert stored.status == "draft"

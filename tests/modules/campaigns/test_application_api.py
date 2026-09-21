from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from app.modules.campaigns.models import Application
from tests.factories import FIXED_NOW, build_brand, build_creator

CAMPAIGNS_URL = "/api/v1/campaigns"
MY_APPLICATIONS_URL = "/api/v1/applications/me"
PITCH = "I run a Madurai street-food page with 12,000 local followers."


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


class User:
    """A signed-in account. `headers` mints a token for the clock's current time,
    so tests that move time forward stay signed in, as a real app would."""

    def __init__(self, account_id, role: str, clock: Clock) -> None:
        self.account_id = account_id
        self.role = role
        self.clock = clock

    @property
    def headers(self) -> dict[str, str]:
        token, _ = create_access_token(self.account_id, self.role, self.clock.now)
        return {"Authorization": f"Bearer {token}"}


def brand_with_profile(db, clock) -> User:
    brand = build_brand(db)
    brand.email = f"brand-{brand.account_id}@example.com"
    db.add(brand)
    db.flush()
    return User(brand.account_id, "brand", clock)


def creator_with_profile(db, clock, handle: str = "priya.eats") -> User:
    creator = build_creator(db, handle=handle)
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def open_campaign(client, brand, **overrides) -> str:
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
    created = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers)
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    published = client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    assert published.status_code == 200
    return campaign_id


def apply(client, creator, campaign_id: str, **overrides):
    body = {"pitch": PITCH, "quoted_amount_paise": 800_000}
    body.update(overrides)
    return client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", json=body, headers=creator.headers
    )


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- applying ------------------------------------------------------------


def test_creator_applies_to_an_open_campaign(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)

    response = apply(client, creator, campaign_id)

    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/v1/applications/{body['id']}"
    assert body["status"] == "submitted"
    assert body["campaign_id"] == campaign_id
    assert body["quoted_amount_paise"] == 800_000
    assert body["rejection_reason"] is None
    assert body["status_changed_at"].startswith("2026-09-17")


def test_applying_twice_is_refused(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, creator, campaign_id)

    assert_problem(apply(client, creator, campaign_id), 409, "already_applied")


def test_cannot_apply_to_a_draft_campaign(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    created = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Draft",
            "description": "Not published yet.",
            "campaign_type": "barter",
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "1 reel",
        },
        headers=brand.headers,
    )

    assert_problem(apply(client, creator, created.json()["id"]), 409, "campaign_not_open")


def test_cannot_apply_after_the_closing_date(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand, applications_close_on="2026-09-20")
    clock.advance(timedelta(days=4))

    assert_problem(apply(client, creator, campaign_id), 409, "applications_closed")


def test_can_apply_on_the_closing_date(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand, applications_close_on="2026-09-20")
    clock.advance(timedelta(days=3))

    assert apply(client, creator, campaign_id).status_code == 201


def test_creator_without_a_profile_is_told_to_finish_it(client, db, clock):
    from tests.factories import create_account

    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    account = create_account(db, "creator")

    assert_problem(
        apply(client, User(account.id, "creator", clock), campaign_id),
        409,
        "creator_profile_required",
    )


def test_brand_cannot_apply(client, db, clock):
    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)

    assert_problem(apply(client, brand, campaign_id), 403, "role_not_allowed")


def test_applying_needs_a_token(client, db, clock):
    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)

    assert_problem(
        client.post(f"{CAMPAIGNS_URL}/{campaign_id}/applications", json={"pitch": PITCH}),
        401,
        "invalid_token",
    )


def test_unknown_campaign_is_not_found(client, db, clock):
    import uuid

    creator = creator_with_profile(db, clock)

    assert_problem(apply(client, creator, str(uuid.uuid4())), 404, "campaign_not_found")


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"pitch": "too short"}, "pitch"),
        ({"pitch": "p" * 1001}, "pitch"),
        ({"pitch": PITCH, "quoted_amount_paise": 0}, "quoted_amount_paise"),
        ({"pitch": PITCH, "status": "accepted"}, "status"),
    ],
)
def test_invalid_application_is_rejected(client, db, clock, body, field):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)

    problem = assert_problem(
        client.post(f"{CAMPAIGNS_URL}/{campaign_id}/applications", json=body, headers=creator.headers),
        422,
        "validation_failed",
    )
    assert field in [error["field"] for error in problem["errors"]]


# --- who can see what ----------------------------------------------------


def test_creator_and_owning_brand_can_read_the_application(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    application_id = apply(client, creator, campaign_id).json()["id"]
    url = f"/api/v1/applications/{application_id}"

    assert client.get(url, headers=creator.headers).status_code == 200
    assert client.get(url, headers=brand.headers).status_code == 200


def test_other_people_cannot_read_the_application(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    application_id = apply(client, creator, campaign_id).json()["id"]
    url = f"/api/v1/applications/{application_id}"
    other_brand = brand_with_profile(db, clock)
    other_creator = creator_with_profile(db, clock, handle="other.creator")

    assert_problem(client.get(url, headers=other_brand.headers), 404, "application_not_found")
    assert_problem(client.get(url, headers=other_creator.headers), 404, "application_not_found")


def test_brand_lists_applications_to_its_own_campaign_only(client, db, clock):
    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, creator_with_profile(db, clock), campaign_id)
    apply(client, creator_with_profile(db, clock, handle="second.creator"), campaign_id)
    other_brand = brand_with_profile(db, clock)

    mine = client.get(f"{CAMPAIGNS_URL}/{campaign_id}/applications", headers=brand.headers)
    theirs = client.get(f"{CAMPAIGNS_URL}/{campaign_id}/applications", headers=other_brand.headers)

    assert len(mine.json()["items"]) == 2
    assert_problem(theirs, 404, "campaign_not_found")


def test_creator_lists_only_their_own_applications(client, db, clock):
    brand = brand_with_profile(db, clock)
    first_campaign = open_campaign(client, brand)
    second_campaign = open_campaign(client, brand, title="Second campaign")
    mine = creator_with_profile(db, clock)
    apply(client, mine, first_campaign)
    apply(client, mine, second_campaign)
    apply(client, creator_with_profile(db, clock, handle="other.creator"), first_campaign)

    response = client.get(MY_APPLICATIONS_URL, headers=mine.headers)

    assert len(response.json()["items"]) == 2
    assert {item["campaign_id"] for item in response.json()["items"]} == {
        first_campaign,
        second_campaign,
    }


# --- decisions -----------------------------------------------------------


def test_brand_shortlists_then_accepts(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]
    url = f"/api/v1/applications/{application_id}"

    clock.advance(timedelta(hours=1))
    shortlisted = client.post(f"{url}/shortlist", headers=brand.headers)
    accepted = client.post(f"{url}/accept", headers=brand.headers)

    assert shortlisted.json()["status"] == "shortlisted"
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["status_changed_at"].startswith("2026-09-17T13")


def test_accept_needs_a_shortlisted_application(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]

    assert_problem(
        client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers),
        409,
        "application_status_conflict",
    )


def test_rejection_carries_a_reason_the_creator_can_see(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]

    rejected = client.post(
        f"/api/v1/applications/{application_id}/reject",
        json={"reason": "budget_mismatch", "note": "We can pay up to Rs 6,000."},
        headers=brand.headers,
    )

    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "budget_mismatch"
    seen_by_creator = client.get(f"/api/v1/applications/{application_id}", headers=creator.headers)
    assert seen_by_creator.json()["rejection_note"] == "We can pay up to Rs 6,000."


def test_rejection_without_a_reason_is_refused(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]

    problem = assert_problem(
        client.post(f"/api/v1/applications/{application_id}/reject", json={}, headers=brand.headers),
        422,
        "validation_failed",
    )
    assert [error["field"] for error in problem["errors"]] == ["reason"]


def test_unknown_rejection_reason_is_refused(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]

    assert_problem(
        client.post(
            f"/api/v1/applications/{application_id}/reject",
            json={"reason": "did_not_like_them"},
            headers=brand.headers,
        ),
        422,
        "validation_failed",
    )


def test_creator_withdraws_their_application(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]

    withdrawn = client.post(
        f"/api/v1/applications/{application_id}/withdraw", headers=creator.headers
    )

    assert withdrawn.json()["status"] == "withdrawn"


def test_brand_cannot_withdraw_and_creator_cannot_decide(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]
    url = f"/api/v1/applications/{application_id}"

    assert_problem(client.post(f"{url}/withdraw", headers=brand.headers), 403, "role_not_allowed")
    assert_problem(client.post(f"{url}/shortlist", headers=creator.headers), 403, "role_not_allowed")


def test_another_brand_cannot_decide_on_your_applicant(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]
    other_brand = brand_with_profile(db, clock)

    assert_problem(
        client.post(f"/api/v1/applications/{application_id}/shortlist", headers=other_brand.headers),
        404,
        "application_not_found",
    )


@pytest.mark.parametrize("action", ["shortlist", "accept", "reject"])
def test_finished_applications_cannot_change(client, db, clock, action):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand)).json()["id"]
    url = f"/api/v1/applications/{application_id}"
    client.post(f"{url}/withdraw", headers=creator.headers)

    body = {"reason": "other"} if action == "reject" else None
    assert_problem(
        client.post(f"{url}/{action}", json=body, headers=brand.headers),
        409,
        "application_status_conflict",
    )


def test_status_filter_and_paging_work(client, db, clock):
    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    application_ids = []
    for index in range(3):
        clock.advance(timedelta(minutes=1))
        creator = creator_with_profile(db, clock, handle=f"creator.{index}")
        application_ids.append(apply(client, creator, campaign_id).json()["id"])
    client.post(f"/api/v1/applications/{application_ids[0]}/shortlist", headers=brand.headers)

    shortlisted = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        params={"status": "shortlisted"},
        headers=brand.headers,
    ).json()
    first_page = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications", params={"limit": 2}, headers=brand.headers
    ).json()
    second_page = client.get(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        params={"limit": 2, "cursor": first_page["next_cursor"]},
        headers=brand.headers,
    ).json()

    assert [item["id"] for item in shortlisted["items"]] == [application_ids[0]]
    assert len(first_page["items"]) == 2
    assert [item["id"] for item in second_page["items"]] == [application_ids[0]]
    assert second_page["next_cursor"] is None


def test_paging_does_not_skip_applications_made_at_the_same_moment(client, db, clock):
    # No clock.advance: all three share one created_at, so the id is the only
    # thing ordering them. Without it a brand never sees the tied applicants.
    brand = brand_with_profile(db, clock)
    campaign_id = open_campaign(client, brand)
    application_ids = {
        apply(client, creator_with_profile(db, clock, handle=f"tied.{index}"), campaign_id).json()[
            "id"
        ]
        for index in range(3)
    }
    url = f"{CAMPAIGNS_URL}/{campaign_id}/applications"

    first = client.get(url, params={"limit": 2}, headers=brand.headers).json()
    second = client.get(
        url, params={"limit": 2, "cursor": first["next_cursor"]}, headers=brand.headers
    ).json()

    seen = [item["id"] for item in first["items"] + second["items"]]
    assert len(seen) == 3
    assert set(seen) == application_ids
    assert second["next_cursor"] is None


def test_stored_row_matches_what_the_api_returned(client, db, clock):
    brand = brand_with_profile(db, clock)
    creator = creator_with_profile(db, clock)
    body = apply(client, creator, open_campaign(client, brand)).json()

    stored = db.get(Application, body["id"])
    assert stored.pitch == body["pitch"]
    assert stored.status == "submitted"
    assert str(stored.campaign_id) == body["campaign_id"]

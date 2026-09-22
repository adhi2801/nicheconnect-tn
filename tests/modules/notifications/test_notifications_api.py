"""Notifications: recorded from real events, readable only by their owner."""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from app.modules.notifications.models import Notification
from tests.factories import FIXED_NOW, build_brand, build_creator

CAMPAIGNS_URL = "/api/v1/campaigns"
URL = "/api/v1/notifications"
PITCH = "I run a Madurai street-food page with 12,000 local followers."


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class User:
    def __init__(self, account_id, role: str, clock: Clock) -> None:
        self.account_id = account_id
        self.role = role
        self.clock = clock

    @property
    def headers(self) -> dict[str, str]:
        token, _ = create_access_token(self.account_id, self.role, self.clock.now)
        return {"Authorization": f"Bearer {token}"}


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


def brand_user(db, clock) -> User:
    brand = build_brand(db)
    brand.email = f"brand-{brand.account_id}@example.com"
    db.add(brand)
    db.flush()
    return User(brand.account_id, "brand", clock)


def creator_user(db, clock, handle: str = "priya.eats") -> User:
    creator = build_creator(db, handle=handle)
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def open_campaign(client, brand: User, title: str = "Pongal sweets launch") -> str:
    created = client.post(
        CAMPAIGNS_URL,
        json={
            "title": title,
            "description": "Three reels featuring our new sweet box.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "3 Instagram reels",
        },
        headers=brand.headers,
    )
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    assert (
        client.post(
            f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
        ).status_code
        == 200
    )
    return campaign_id


def apply(client, creator: User, campaign_id: str) -> str:
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def notifications_of(client, user: User) -> list[dict]:
    response = client.get(URL, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


# --- recorded from events -------------------------------------------------


def test_brand_is_told_when_a_creator_applies(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)

    application_id = apply(client, creator, campaign_id)

    [item] = notifications_of(client, brand)
    assert item["notification_type"] == "application_received"
    assert item["campaign_id"] == campaign_id
    assert item["application_id"] == application_id
    assert item["details"]["campaign_title"] == "Pongal sweets launch"
    assert item["details"]["creator_handle"] == "priya.eats"
    assert item["read_at"] is None


def test_the_creator_is_not_told_about_their_own_application(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    apply(client, creator, open_campaign(client, brand))

    assert notifications_of(client, creator) == []


@pytest.mark.parametrize(
    ("action", "body", "expected_type"),
    [
        ("shortlist", None, "application_shortlisted"),
        ("reject", {"reason": "budget_mismatch"}, "application_rejected"),
    ],
)
def test_creator_is_told_about_the_brands_decision(
    client, db, clock, action, body, expected_type
):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand))

    response = client.post(
        f"/api/v1/applications/{application_id}/{action}",
        json=body,
        headers=brand.headers,
    )

    assert response.status_code == 200, response.text
    [item] = notifications_of(client, creator)
    assert item["notification_type"] == expected_type
    assert item["application_id"] == application_id


def test_a_rejection_notification_carries_the_reason(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand))

    client.post(
        f"/api/v1/applications/{application_id}/reject",
        json={"reason": "audience_mismatch", "note": "Looking for Coimbatore creators."},
        headers=brand.headers,
    )

    [item] = notifications_of(client, creator)
    assert item["details"]["reason"] == "audience_mismatch"
    # The private note is not copied into the notification.
    assert "Coimbatore" not in str(item["details"])


def test_accepting_tells_the_creator(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand))
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    clock.advance(timedelta(minutes=5))  # so "newest first" has a clear order

    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)

    types = [item["notification_type"] for item in notifications_of(client, creator)]
    assert types == ["application_accepted", "application_shortlisted"]


def test_withdrawing_tells_the_brand(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand))
    clock.advance(timedelta(minutes=5))  # so "newest first" has a clear order

    client.post(
        f"/api/v1/applications/{application_id}/withdraw", headers=creator.headers
    )

    types = [item["notification_type"] for item in notifications_of(client, brand)]
    assert types == ["application_withdrawn", "application_received"]


def test_no_notification_when_the_action_is_refused(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = apply(client, creator, open_campaign(client, brand))

    # Accept without shortlisting first: refused, so nothing is recorded.
    assert_problem(
        client.post(
            f"/api/v1/applications/{application_id}/accept", headers=brand.headers
        ),
        409,
        "application_status_conflict",
    )
    assert notifications_of(client, creator) == []


# --- reading and privacy --------------------------------------------------


def test_each_account_sees_only_its_own(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    other_brand = brand_user(db, clock)
    apply(client, creator, open_campaign(client, brand))

    assert len(notifications_of(client, brand)) == 1
    assert notifications_of(client, other_brand) == []


def test_another_account_cannot_mark_mine_read(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    apply(client, creator, open_campaign(client, brand))
    notification_id = notifications_of(client, brand)[0]["id"]

    assert_problem(
        client.post(f"{URL}/{notification_id}/read", headers=creator.headers),
        404,
        "notification_not_found",
    )


def test_unknown_notification_is_not_found(client, db, clock):
    import uuid

    brand = brand_user(db, clock)

    assert_problem(
        client.post(f"{URL}/{uuid.uuid4()}/read", headers=brand.headers),
        404,
        "notification_not_found",
    )


def test_listing_needs_a_token(client):
    assert_problem(client.get(URL), 401, "invalid_token")


# --- unread and marking read ----------------------------------------------


def test_unread_count_and_marking_one_read(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, creator, campaign_id)
    apply(client, creator_user(db, clock, handle="second.creator"), campaign_id)

    before = client.get(f"{URL}/unread-count", headers=brand.headers).json()
    first_id = notifications_of(client, brand)[0]["id"]
    clock.advance(timedelta(minutes=5))
    marked = client.post(f"{URL}/{first_id}/read", headers=brand.headers)
    after = client.get(f"{URL}/unread-count", headers=brand.headers).json()

    assert before == {"unread": 2}
    assert marked.json()["read_at"].startswith("2026-09-17T12:05")
    assert after == {"unread": 1}


def test_marking_read_twice_keeps_the_first_time(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    apply(client, creator, open_campaign(client, brand))
    notification_id = notifications_of(client, brand)[0]["id"]
    first = client.post(f"{URL}/{notification_id}/read", headers=brand.headers).json()

    clock.advance(timedelta(hours=1))
    second = client.post(f"{URL}/{notification_id}/read", headers=brand.headers).json()

    assert second["read_at"] == first["read_at"]


def test_mark_all_read_clears_the_badge(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, creator, campaign_id)
    apply(client, creator_user(db, clock, handle="second.creator"), campaign_id)

    marked = client.post(f"{URL}/read-all", headers=brand.headers)
    again = client.post(f"{URL}/read-all", headers=brand.headers)

    assert marked.json() == {"marked_read": 2}
    assert again.json() == {"marked_read": 0}
    assert client.get(f"{URL}/unread-count", headers=brand.headers).json() == {
        "unread": 0
    }


def test_unread_only_filter(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    campaign_id = open_campaign(client, brand)
    apply(client, creator, campaign_id)
    apply(client, creator_user(db, clock, handle="second.creator"), campaign_id)
    newest_id = notifications_of(client, brand)[0]["id"]
    client.post(f"{URL}/{newest_id}/read", headers=brand.headers)

    unread = client.get(URL, params={"unread_only": True}, headers=brand.headers).json()

    assert [item["id"] for item in unread["items"]] != [newest_id]
    assert len(unread["items"]) == 1


def test_list_pages_newest_first(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    for index in range(3):
        clock.advance(timedelta(minutes=1))
        apply(client, creator_user(db, clock, handle=f"creator.{index}"), campaign_id)

    first = client.get(URL, params={"limit": 2}, headers=brand.headers).json()
    second = client.get(
        URL, params={"limit": 2, "cursor": first["next_cursor"]}, headers=brand.headers
    ).json()

    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    times = [item["created_at"] for item in first["items"] + second["items"]]
    assert times == sorted(times, reverse=True)


def test_paging_does_not_skip_rows_created_at_the_same_moment(client, db, clock):
    # No clock.advance: all three rows share one created_at, which is what a
    # batch or a busy second produces. The id must break the tie, or the
    # second page silently loses everything that shared the first page's
    # last timestamp.
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    for index in range(3):
        apply(client, creator_user(db, clock, handle=f"same.moment.{index}"), campaign_id)

    first = client.get(URL, params={"limit": 2}, headers=brand.headers).json()
    second = client.get(
        URL, params={"limit": 2, "cursor": first["next_cursor"]}, headers=brand.headers
    ).json()

    seen = [item["id"] for item in first["items"] + second["items"]]
    assert len(seen) == 3
    assert len(set(seen)) == 3
    assert second["next_cursor"] is None


def test_stored_row_matches_the_api(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    apply(client, creator, open_campaign(client, brand))

    item = notifications_of(client, brand)[0]
    stored = db.get(Notification, item["id"])
    assert stored.account_id == brand.account_id
    assert stored.details == item["details"]
    assert db.scalars(
        select(Notification).where(Notification.account_id == brand.account_id)
    ).all() == [stored]

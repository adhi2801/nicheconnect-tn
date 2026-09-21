"""The deal memo over HTTP: draft, send, accept or question, cancel."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import app
from app.modules.auth.dependencies import get_now
from app.modules.auth.tokens import create_access_token
from app.modules.deal_memo.models import DealMemo
from tests.factories import FIXED_NOW, build_brand, build_creator

CAMPAIGNS_URL = "/api/v1/campaigns"
MEMOS_URL = "/api/v1/deal-memos"
NOTIFICATIONS_URL = "/api/v1/notifications"
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
    brand = build_brand(db, email=f"brand-{uuid.uuid4().hex[:12]}@example.com")
    db.add(brand)
    db.flush()
    return User(brand.account_id, "brand", clock)


def creator_user(db, clock) -> User:
    creator = build_creator(db, handle=f"memo{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def accepted_application(client, brand: User, creator: User, campaign_type: str = "paid") -> str:
    """A campaign, an application, shortlisted and accepted: ready for a memo."""
    body = {
        "title": "Pongal sweets launch",
        "description": "Three reels featuring our new sweet box.",
        "campaign_type": campaign_type,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "3 Instagram reels",
    }
    if campaign_type != "barter":
        body |= {"budget_min_paise": 500_000, "budget_max_paise": 1_500_000}
    created = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers)
    assert created.status_code == 201, created.text
    campaign_id = created.json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    applied = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert applied.status_code == 201, applied.text
    application_id = applied.json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    return application_id


def draft_memo(client, brand: User, application_id: str, **overrides) -> dict:
    body = {"deliverables": "3 Instagram reels, 1 story set.", "fee_amount_paise": 800_000}
    body.update(overrides)
    response = client.post(
        f"{MEMOS_URL}/for-application/{application_id}", json=body, headers=brand.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def sent_memo(client, brand: User, application_id: str, **overrides) -> dict:
    memo = draft_memo(client, brand, application_id, **overrides)
    response = client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


def notification_types(client, user: User) -> list[str]:
    response = client.get(NOTIFICATIONS_URL, headers=user.headers)
    return [item["notification_type"] for item in response.json()["items"]]


# --- creating -------------------------------------------------------------


def test_brand_drafts_a_memo_with_the_agreed_defaults(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    response = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "3 Instagram reels, 1 story set.", "fee_amount_paise": 800_000},
        headers=brand.headers,
    )

    assert response.status_code == 201
    memo = response.json()
    assert response.headers["location"] == f"{MEMOS_URL}/{memo['id']}"
    assert memo["status"] == "draft"
    assert memo["approval_window_days"] == 7  # D-025
    assert memo["payment_due_days"] == 7  # D-027
    assert memo["cancellation_fee_paise"] == 0
    assert memo["revision_count"] == 0
    assert memo["disclosure_required"] is True


def test_a_memo_needs_an_accepted_application(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    body = {
        "title": "Pongal sweets launch",
        "description": "Three reels.",
        "campaign_type": "paid",
        "budget_min_paise": 500_000,
        "budget_max_paise": 1_500_000,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "3 reels",
    }
    campaign_id = client.post(CAMPAIGNS_URL, json=body, headers=brand.headers).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "3 reels", "fee_amount_paise": 800_000},
            headers=brand.headers,
        ),
        409,
        "application_not_accepted",
    )


def test_one_memo_per_application(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)
    draft_memo(client, brand, application_id)

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "Another memo", "fee_amount_paise": 100_000},
            headers=brand.headers,
        ),
        409,
        "memo_already_exists",
    )


def test_a_paid_campaign_memo_needs_a_fee(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "3 reels"},
            headers=brand.headers,
        ),
        409,
        "paid_memo_needs_fee",
    )


def test_a_barter_memo_must_not_have_a_fee(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator, campaign_type="barter")

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "1 reel", "fee_amount_paise": 500_000},
            headers=brand.headers,
        ),
        409,
        "barter_memo_has_no_fee",
    )
    ok = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "1 reel in exchange for the product"},
        headers=brand.headers,
    )
    assert ok.status_code == 201
    assert ok.json()["fee_amount_paise"] is None


def test_a_creator_cannot_write_a_memo(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "3 reels", "fee_amount_paise": 800_000},
            headers=creator.headers,
        ),
        403,
        "role_not_allowed",
    )


def test_another_brand_cannot_write_a_memo_on_your_applicant(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)
    other_brand = brand_user(db, clock)

    assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}",
            json={"deliverables": "3 reels", "fee_amount_paise": 800_000},
            headers=other_brand.headers,
        ),
        404,
        "application_not_found",
    )


# --- who sees what --------------------------------------------------------


def test_a_draft_is_invisible_to_the_creator_until_it_is_sent(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = draft_memo(client, brand, accepted_application(client, brand, creator))

    assert_problem(
        client.get(f"{MEMOS_URL}/{memo['id']}", headers=creator.headers), 404, "memo_not_found"
    )
    assert client.get(f"{MEMOS_URL}/{memo['id']}", headers=brand.headers).status_code == 200

    client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers)

    assert client.get(f"{MEMOS_URL}/{memo['id']}", headers=creator.headers).status_code == 200


def test_strangers_see_nothing(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))

    for stranger in (brand_user(db, clock), creator_user(db, clock)):
        assert_problem(
            client.get(f"{MEMOS_URL}/{memo['id']}", headers=stranger.headers),
            404,
            "memo_not_found",
        )


def test_my_list_shows_each_side_their_own(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    draft = draft_memo(client, brand, accepted_application(client, brand, creator))
    other_brand, other_creator = brand_user(db, clock), creator_user(db, clock)
    sent_memo(client, other_brand, accepted_application(client, other_brand, other_creator))

    brand_list = client.get(f"{MEMOS_URL}/mine", headers=brand.headers).json()
    creator_list = client.get(f"{MEMOS_URL}/mine", headers=creator.headers).json()

    assert [item["id"] for item in brand_list["items"]] == [draft["id"]]
    # The creator's memo is still a draft, so it is not theirs to see yet.
    assert creator_list["items"] == []


def test_my_list_pages_without_skipping_memos_drafted_at_the_same_moment(client, db, clock):
    # No clock.advance: all three memos share one created_at, so the id is the
    # only thing ordering them. Without it the second page loses the tied rows.
    brand = brand_user(db, clock)
    memo_ids = {
        draft_memo(client, brand, accepted_application(client, brand, creator_user(db, clock)))[
            "id"
        ]
        for _ in range(3)
    }

    first = client.get(f"{MEMOS_URL}/mine", params={"limit": 2}, headers=brand.headers).json()
    second = client.get(
        f"{MEMOS_URL}/mine",
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=brand.headers,
    ).json()

    seen = [item["id"] for item in first["items"] + second["items"]]
    assert len(seen) == 3
    assert set(seen) == memo_ids
    assert second["next_cursor"] is None


# --- the journey ----------------------------------------------------------


def test_send_then_accept(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = draft_memo(client, brand, accepted_application(client, brand, creator))

    clock.advance(timedelta(hours=1))
    sent = client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers).json()
    clock.advance(timedelta(hours=1))
    accepted = client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers).json()

    assert sent["status"] == "sent" and sent["sent_at"] is not None
    assert accepted["status"] == "accepted"
    assert accepted["accepted_at"].startswith("2026-09-17T14")
    assert "memo_sent" in notification_types(client, creator)
    assert "memo_accepted" in notification_types(client, brand)


def test_creator_declines(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))

    declined = client.post(f"{MEMOS_URL}/{memo['id']}/decline", headers=creator.headers).json()

    assert declined["status"] == "declined"
    assert "memo_declined" in notification_types(client, brand)
    # Declining is final.
    assert_problem(
        client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers),
        409,
        "memo_status_conflict",
    )


def test_creator_asks_for_a_change_and_the_brand_resends(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))

    asked = client.post(
        f"{MEMOS_URL}/{memo['id']}/request-change",
        json={"message": "Can we make it 2 reels for the same fee?"},
        headers=creator.headers,
    ).json()
    changed = client.patch(
        f"{MEMOS_URL}/{memo['id']}", json={"deliverables": "2 Instagram reels"}, headers=brand.headers
    ).json()
    resent = client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers).json()

    assert asked["status"] == "change_requested"
    assert asked["revision_count"] == 1
    assert changed["deliverables"] == "2 Instagram reels"
    assert resent["status"] == "sent"
    brand_notifications = client.get(NOTIFICATIONS_URL, headers=brand.headers).json()["items"]
    [change_request] = [
        item for item in brand_notifications if item["notification_type"] == "memo_change_requested"
    ]
    assert change_request["details"]["message"] == "Can we make it 2 reels for the same fee?"


def test_terms_stop_changing_once_accepted(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers)

    assert_problem(
        client.patch(
            f"{MEMOS_URL}/{memo['id']}", json={"fee_amount_paise": 100_000}, headers=brand.headers
        ),
        409,
        "memo_not_editable",
    )


def test_a_creator_cannot_send_or_edit(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = draft_memo(client, brand, accepted_application(client, brand, creator))

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=creator.headers), 403, "role_not_allowed"
    )
    assert_problem(
        client.patch(f"{MEMOS_URL}/{memo['id']}", json={"deliverables": "mine"}, headers=creator.headers),
        403,
        "role_not_allowed",
    )


def test_a_brand_cannot_accept_its_own_memo(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=brand.headers), 403, "role_not_allowed"
    )


# --- cancelling (D-026) ---------------------------------------------------


def test_cancelling_before_work_costs_nothing(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers)

    cancelled = client.post(f"{MEMOS_URL}/{memo['id']}/cancel", headers=brand.headers).json()

    assert cancelled["status"] == "cancelled"
    assert cancelled["cancellation_kind"] == "withdrawn_early"
    assert "memo_cancelled" in notification_types(client, creator)


def test_cancelling_after_work_started_counts(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers)
    # Proof upload does not exist yet; set the marker the way it will be set.
    stored = db.get(DealMemo, memo["id"])
    stored.work_started_at = clock.now
    db.flush()

    cancelled = client.post(f"{MEMOS_URL}/{memo['id']}/cancel", headers=brand.headers).json()

    assert cancelled["cancellation_kind"] == "cancelled_by_brand"


def test_a_creator_withdrawing_after_work_counts_against_them(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers)
    stored = db.get(DealMemo, memo["id"])
    stored.work_started_at = clock.now
    db.flush()

    cancelled = client.post(f"{MEMOS_URL}/{memo['id']}/withdraw", headers=creator.headers).json()

    assert cancelled["cancellation_kind"] == "cancelled_by_creator"
    assert "memo_cancelled" in notification_types(client, brand)


def test_a_cancelled_memo_is_finished(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/cancel", headers=brand.headers)

    for action, user in (("send", brand), ("accept", creator), ("decline", creator)):
        assert_problem(
            client.post(f"{MEMOS_URL}/{memo['id']}/{action}", headers=user.headers),
            409,
            "memo_status_conflict",
        )


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"deliverables": "", "fee_amount_paise": 1}, "deliverables"),
        ({"deliverables": "x", "fee_amount_paise": 0}, "fee_amount_paise"),
        ({"deliverables": "x", "fee_amount_paise": 1, "approval_window_days": 31}, "approval_window_days"),
        ({"deliverables": "x", "fee_amount_paise": 1, "payment_due_days": 0}, "payment_due_days"),
        ({"deliverables": "x", "fee_amount_paise": 1, "usage_rights_days": 0}, "usage_rights_days"),
        ({"deliverables": "x", "fee_amount_paise": 1, "status": "accepted"}, "status"),
    ],
)
def test_invalid_memo_fields_are_rejected(client, db, clock, body, field):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    problem = assert_problem(
        client.post(
            f"{MEMOS_URL}/for-application/{application_id}", json=body, headers=brand.headers
        ),
        422,
        "validation_failed",
    )
    assert field in [error["field"] for error in problem["errors"]]


def test_a_change_request_needs_a_message(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = sent_memo(client, brand, accepted_application(client, brand, creator))

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo['id']}/request-change", json={}, headers=creator.headers),
        422,
        "validation_failed",
    )


def test_reading_a_memo_needs_a_token(client):
    assert_problem(client.get(f"{MEMOS_URL}/{uuid.uuid4()}"), 401, "invalid_token")


def test_the_stored_memo_matches_the_api(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo = draft_memo(
        client,
        brand,
        accepted_application(client, brand, creator),
        usage_rights_days=180,
        cancellation_fee_paise=100_000,
        extra_terms="Shoot in Tamil, subtitles in English.",
    )

    stored = db.get(DealMemo, memo["id"])
    assert stored.usage_rights_days == 180
    assert stored.cancellation_fee_paise == 100_000
    assert stored.extra_terms == "Shoot in Tamil, subtitles in English."

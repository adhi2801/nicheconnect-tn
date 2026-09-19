"""Proof of work: submitted, reviewed, or approved by the clock (D-024, D-025)."""

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
LINK = "https://www.instagram.com/reel/abc123/"


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
    creator = build_creator(db, handle=f"proof{uuid.uuid4().hex[:12]}")
    db.add(creator)
    db.flush()
    return User(creator.account_id, "creator", clock)


def accepted_memo(client, brand: User, creator: User, **memo_fields) -> str:
    """A whole journey: campaign, application, acceptance, memo, accepted."""
    campaign_id = client.post(
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
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    body = {"deliverables": "3 Instagram reels, 1 story set.", "fee_amount_paise": 800_000}
    body.update(memo_fields)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}", json=body, headers=brand.headers
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    accepted = client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    assert accepted.status_code == 200, accepted.text
    return memo_id


def submit(client, creator: User, memo_id: str, **overrides):
    body = {"content_url": LINK, "format": "reel", "disclosure_confirmed": True}
    body.update(overrides)
    return client.post(f"{MEMOS_URL}/{memo_id}/proof", json=body, headers=creator.headers)


def assert_problem(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == code
    return body


def notification_types(client, user: User) -> list[str]:
    return [
        item["notification_type"]
        for item in client.get(NOTIFICATIONS_URL, headers=user.headers).json()["items"]
    ]


# --- submitting -----------------------------------------------------------


def test_creator_submits_proof_and_the_brand_is_told(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    response = submit(client, creator, memo_id)

    assert response.status_code == 201
    proof = response.json()
    assert response.headers["location"] == f"{MEMOS_URL}/{memo_id}/proof/{proof['id']}"
    assert proof["status"] == "submitted"
    assert proof["content_url"] == LINK
    assert proof["disclosure_confirmed"] is True
    assert proof["auto_approved"] is False
    assert "proof_submitted" in notification_types(client, brand)


def test_submitting_marks_that_work_has_started(client, db, clock):
    """The line between a cancellation that counts and one that does not (D-026)."""
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    assert db.get(DealMemo, memo_id).work_started_at is None

    clock.advance(timedelta(hours=2))
    submit(client, creator, memo_id)

    assert db.get(DealMemo, memo_id).work_started_at is not None
    cancelled = client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers).json()
    assert cancelled["cancellation_kind"] == "cancelled_by_brand"


def test_only_one_submission_waits_for_review(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submit(client, creator, memo_id)

    assert_problem(submit(client, creator, memo_id), 409, "proof_already_decided")


def test_proof_needs_an_accepted_memo(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)

    assert_problem(submit(client, creator, memo_id), 409, "memo_status_conflict")


def test_a_brand_cannot_submit_proof(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(submit(client, brand, memo_id), 403, "role_not_allowed")


def test_another_creator_cannot_submit_on_your_memo(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(submit(client, creator_user(db, clock), memo_id), 404, "memo_not_found")


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"content_url": "http://insecure.example.com/post"}, "content_url"),
        ({"content_url": "not a url"}, "content_url"),
        ({"format": "billboard"}, "format"),
        ({"note": "n" * 1001}, "note"),
        ({"status": "approved"}, "status"),
    ],
)
def test_invalid_proof_is_rejected(client, db, clock, overrides, field):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    problem = assert_problem(submit(client, creator, memo_id, **overrides), 422, "validation_failed")
    assert field in [error["field"] for error in problem["errors"]]


# --- reviewing ------------------------------------------------------------


def test_brand_approves_and_the_creator_is_told(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]
    clock.advance(timedelta(days=1))

    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    ).json()

    assert approved["status"] == "approved"
    assert approved["auto_approved"] is False
    assert approved["approved_at"].startswith("2026-09-18")
    assert "proof_approved" in notification_types(client, creator)


def test_brand_asks_for_a_fix_and_the_creator_resubmits(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]

    sent_back = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "The ad label is missing from the caption."},
        headers=brand.headers,
    ).json()
    again = submit(client, creator, memo_id, content_url="https://example.com/fixed")

    assert sent_back["status"] == "revision_requested"
    assert sent_back["revision_note"] == "The ad label is missing from the caption."
    assert again.status_code == 201
    assert "proof_revision_requested" in notification_types(client, creator)


def test_a_decided_submission_cannot_be_decided_again(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers),
        409,
        "proof_already_decided",
    )


def test_a_creator_cannot_approve_their_own_proof(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]

    assert_problem(
        client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=creator.headers),
        403,
        "role_not_allowed",
    )


def test_another_brand_cannot_review_your_proof(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]

    assert_problem(
        client.post(
            f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve",
            headers=brand_user(db, clock).headers,
        ),
        404,
        "memo_not_found",
    )


# --- the clock (D-025) ----------------------------------------------------


def test_proof_approves_itself_when_the_window_passes(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submit(client, creator, memo_id)

    clock.advance(timedelta(days=7))
    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=creator.headers).json()

    assert proof["status"] == "approved"
    assert proof["auto_approved"] is True
    assert proof["approved_at"].startswith("2026-09-24")  # exactly 7 days later
    assert "proof_auto_approved" in notification_types(client, creator)


def test_it_does_not_approve_itself_a_day_early(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submit(client, creator, memo_id)

    clock.advance(timedelta(days=6, hours=23))
    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()

    assert proof["status"] == "submitted"


def test_the_agreed_window_is_what_counts(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator, approval_window_days=3)
    submit(client, creator, memo_id)

    clock.advance(timedelta(days=3))
    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()

    assert proof["status"] == "approved"
    assert proof["auto_approved"] is True


def test_approving_late_reports_the_automatic_approval(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit(client, creator, memo_id).json()["id"]

    clock.advance(timedelta(days=8))
    late = client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)

    assert_problem(late, 409, "proof_already_decided")
    [proof] = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()
    assert proof["auto_approved"] is True


# --- who can see it -------------------------------------------------------


def test_both_sides_see_the_same_submissions(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submit(client, creator, memo_id)

    from_creator = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=creator.headers).json()
    from_brand = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()

    assert [item["id"] for item in from_creator] == [item["id"] for item in from_brand]


def test_a_stranger_sees_nothing(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submit(client, creator, memo_id)

    assert_problem(
        client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=creator_user(db, clock).headers),
        404,
        "memo_not_found",
    )


def test_listing_proof_needs_a_token(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(client.get(f"{MEMOS_URL}/{memo_id}/proof"), 401, "invalid_token")


def test_submissions_are_listed_newest_first(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    first = submit(client, creator, memo_id).json()["id"]
    proof_url = f"{MEMOS_URL}/{memo_id}/proof/{first}/request-revision"
    client.post(proof_url, json={"note": "Please add the ad label."}, headers=brand.headers)
    clock.advance(timedelta(hours=3))
    second = submit(client, creator, memo_id, content_url="https://example.com/second").json()["id"]

    listed = client.get(f"{MEMOS_URL}/{memo_id}/proof", headers=brand.headers).json()

    assert [item["id"] for item in listed] == [second, first]

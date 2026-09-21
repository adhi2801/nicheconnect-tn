"""Every write outside login is safe to retry (D-040).

The scenario: someone on patchy mobile data taps a button, the reply never
arrives, and the app sends it again. Without an Idempotency-Key the retry
either does the work twice (a second campaign) or comes back as a confusing
"already done" error, although the first attempt worked. With one, the retry
gets back the answer that was lost.

How the key is stored, scoped and refused on reuse is tested once, in
tests/core/test_idempotency.py and test_application_idempotency_api.py. This
file proves every router is wired, and that no future write can be added
without it.
"""

import uuid
from collections.abc import Iterator

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.idempotency import HEADER, RedisIdempotencyStore, set_store
from app.core.idempotent_route import REPLAYED_HEADER
from app.main import app
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from tests.deal_flow import (
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)

REDIS_URL = "redis://localhost:6379/2"

# Login has its own rules and is not covered by D-040: replaying a one-time
# code or a refresh response is a security question, decided separately.
NOT_COVERED_PREFIX = "/api/v1/auth/"

CAMPAIGN = {
    "title": "Pongal sweets launch",
    "description": "Three reels featuring our new sweet box.",
    "campaign_type": "paid",
    "budget_min_paise": 500_000,
    "budget_max_paise": 1_500_000,
    "cities": ["Madurai"],
    "niches": ["food"],
    "deliverables": "3 Instagram reels",
}


@pytest.fixture(autouse=True)
def store() -> Iterator[None]:
    """A real Redis, on a database of its own, emptied around each test."""
    connection = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    connection.flushdb()
    set_store(RedisIdempotencyStore(connection))
    try:
        yield
    finally:
        set_store(None)
        connection.flushdb()
        connection.close()


def twice(client: TestClient, method: str, url: str, user: User, **kwargs):
    """Send the same request twice under one key, as a retrying app would.

    The key is a random UUID, which is what a real client sends.
    """
    headers = {**user.headers, HEADER: str(uuid.uuid4())}
    first = client.request(method, url, headers=headers, **kwargs)
    second = client.request(method, url, headers=headers, **kwargs)
    return first, second


def my_campaigns(client: TestClient, brand: User) -> list[dict]:
    """The brand's own campaigns. The local database may hold seed data, so
    nothing here counts the whole table."""
    return client.get(CAMPAIGNS_URL, headers=brand.headers).json()["items"]


def assert_replayed(first, second, status: int) -> None:
    assert first.status_code == status, first.text
    assert second.status_code == status, second.text
    assert second.headers[REPLAYED_HEADER] == "true"
    assert second.json() == first.json()


# --- nothing can be left out --------------------------------------------------


def test_every_write_outside_login_accepts_an_idempotency_key():
    missing = [
        f"{method.upper()} {path}"
        for path, operations in app.openapi()["paths"].items()
        if not path.startswith(NOT_COVERED_PREFIX)
        for method, operation in operations.items()
        if method in ("post", "patch")
        and not any(p.get("name") == HEADER for p in operation.get("parameters", []))
    ]

    assert missing == [], "Writes a retry could repeat: " + ", ".join(missing)


# --- what a retry used to do, and does no longer -------------------------------


def test_a_retried_campaign_is_created_once(client, db, clock):
    brand = brand_user(db, clock)

    first, second = twice(client, "POST", CAMPAIGNS_URL, brand, json=CAMPAIGN)

    assert_replayed(first, second, 201)
    assert second.headers["location"] == first.headers["location"]
    assert len(my_campaigns(client, brand)) == 1


def test_a_retried_publish_is_not_a_conflict(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = client.post(CAMPAIGNS_URL, json=CAMPAIGN, headers=brand.headers).json()[
        "id"
    ]

    first, second = twice(client, "POST", f"{CAMPAIGNS_URL}/{campaign_id}/publish", brand)

    assert_replayed(first, second, 200)


def test_a_retried_campaign_edit_replays(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = client.post(CAMPAIGNS_URL, json=CAMPAIGN, headers=brand.headers).json()[
        "id"
    ]

    first, second = twice(
        client,
        "PATCH",
        f"{CAMPAIGNS_URL}/{campaign_id}",
        brand,
        json={"title": "Pongal sweets, second batch"},
    )

    assert_replayed(first, second, 200)


def accepted_application(client: TestClient, brand: User, creator: User) -> str:
    """A published campaign and an application the brand has accepted."""
    campaign_id = client.post(CAMPAIGNS_URL, json=CAMPAIGN, headers=brand.headers).json()[
        "id"
    ]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    return str(application_id)


MEMO = {
    "deliverables": "3 Instagram reels",
    "fee_amount_paise": 800_000,
    "content_due_on": "2026-12-31",
}


def test_a_retried_memo_is_drafted_once(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    first, second = twice(
        client,
        "POST",
        f"{MEMOS_URL}/for-application/{application_id}",
        brand,
        json=MEMO,
    )

    assert_replayed(first, second, 201)
    memos = select(func.count()).select_from(DealMemo)
    assert db.scalar(memos.where(DealMemo.application_id == application_id)) == 1


def test_a_retried_acceptance_is_not_a_conflict(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}", json=MEMO, headers=brand.headers
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)

    first, second = twice(client, "POST", f"{MEMOS_URL}/{memo_id}/accept", creator)

    assert_replayed(first, second, 200)


def test_a_retried_proof_is_submitted_once(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    first, second = twice(
        client,
        "POST",
        f"{MEMOS_URL}/{memo_id}/proof",
        creator,
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
    )

    assert_replayed(first, second, 201)
    proofs = select(func.count()).select_from(DeliverableProof)
    assert db.scalar(proofs.where(DeliverableProof.deal_memo_id == memo_id)) == 1


def test_a_retried_approval_is_not_a_conflict(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]

    first, second = twice(
        client,
        "POST",
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve",
        brand,
    )

    assert_replayed(first, second, 200)


def test_a_retried_profile_is_created_once(client, db, clock):
    from tests.factories import create_account

    account = create_account(db, "creator")
    creator = User(account.id, "creator", clock)

    first, second = twice(
        client,
        "POST",
        "/api/v1/creators/me",
        creator,
        json={
            "display_name": "Priya Eats",
            "handle": "priya.retry",
            "city": "Coimbatore",
            "niches": ["food"],
            "languages": ["en"],
        },
    )

    assert_replayed(first, second, 201)


def test_a_retried_mark_as_read_replays(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    accepted_memo(client, brand, creator)

    first, second = twice(client, "POST", "/api/v1/notifications/read-all", creator)

    assert_replayed(first, second, 200)


def test_without_a_key_nothing_changes(client, db, clock):
    """The header is optional: a request without one runs, every time."""
    brand = brand_user(db, clock)

    for _ in range(2):
        response = client.post(CAMPAIGNS_URL, json=CAMPAIGN, headers=brand.headers)
        assert response.status_code == 201
        assert REPLAYED_HEADER not in response.headers

    assert len(my_campaigns(client, brand)) == 2

"""POST /api/v1/brands/me/payments/mark-paid: several payments, each on its own.

The scenario: a brand pays five creators through its bank's bulk transfer,
the bank rejects one row, and the brand records the four that went
through. One bad row must never hold back the other creators' notice that
their money is on its way, and nothing here may reveal another brand's deal.
"""

import uuid
from collections.abc import Iterator

import pytest
import redis
from fastapi.testclient import TestClient

from app.core.idempotency import HEADER, RedisIdempotencyStore, set_store
from app.core.idempotent_route import REPLAYED_HEADER
from app.modules.payment_status.bulk_router import BULK_LIMIT
from app.modules.payment_status.service import MAX_BULK_MARK_PAID
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    NOTIFICATIONS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import create_account

URL = "/api/v1/brands/me/payments/mark-paid"
REDIS_URL = "redis://localhost:6379/2"


def approved_deal(client: TestClient, brand: User, creator: User) -> str:
    """A deal with approved work, so its payment record is open."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    return memo_id


def row(memo_id, reference: str = "412345678901", method: str = "upi") -> dict:
    return {"memo_id": str(memo_id), "method": method, "reference": reference}


def mark(client: TestClient, brand: User, *rows: dict, headers: dict | None = None):
    return client.post(
        URL, json={"payments": list(rows)}, headers=headers or brand.headers
    )


def payment_state(client: TestClient, user: User, memo_id: str) -> str:
    response = client.get(f"{MEMOS_URL}/{memo_id}/payment", headers=user.headers)
    assert response.status_code == 200, response.text
    return str(response.json()["state"])


def notification_types(client: TestClient, user: User) -> list[str]:
    items = client.get(NOTIFICATIONS_URL, headers=user.headers).json()["items"]
    return [item["notification_type"] for item in items]


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


# --- recording ---------------------------------------------------------------


def test_several_payments_are_recorded_in_one_request(client, db, clock, brand):
    creators = [creator_user(db, clock) for _ in range(3)]
    memo_ids = [approved_deal(client, brand, creator) for creator in creators]

    response = mark(
        client, brand, *(row(m, f"41234567890{i}") for i, m in enumerate(memo_ids))
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["recorded"], body["refused"]) == (3, 0)
    assert [r["index"] for r in body["results"]] == [0, 1, 2]
    assert [r["memo_id"] for r in body["results"]] == memo_ids
    assert all(r["payment"]["state"] == "paid" for r in body["results"])
    for creator, memo_id in zip(creators, memo_ids, strict=True):
        # Exactly the single path's rules: the creator is told to look.
        assert "payment_marked_paid" in notification_types(client, creator)
        assert payment_state(client, creator, memo_id) == "paid"


def test_a_refused_row_never_holds_back_the_others(client, db, clock, brand):
    already = approved_deal(client, brand, creator_user(db, clock))
    client.post(
        f"{MEMOS_URL}/{already}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678999"},
        headers=brand.headers,
    )
    fresh = approved_deal(client, brand, creator_user(db, clock))

    body = mark(client, brand, row(already), row(fresh)).json()

    first, second = body["results"]
    assert first["outcome"] == "refused"
    assert first["problem"]["code"] == "payment_already_marked_paid"
    assert first["problem"]["status"] == 409
    assert first["payment"] is None
    assert second["outcome"] == "recorded"
    assert payment_state(client, brand, fresh) == "paid"
    assert (body["recorded"], body["refused"]) == (1, 1)


def test_a_reference_the_single_endpoint_would_refuse_is_refused_here_too(
    client, db, clock, brand
):
    good = approved_deal(client, brand, creator_user(db, clock))
    bad = approved_deal(client, brand, creator_user(db, clock))

    body = mark(client, brand, row(good), row(bad, reference="UTR@123!")).json()

    assert body["results"][0]["outcome"] == "recorded"
    refused = body["results"][1]
    assert refused["problem"]["code"] == "invalid_payment_reference"
    assert payment_state(client, brand, bad) == "due"
    # The method was set before the reference was checked; the row's own
    # savepoint must undo that too, or the final commit would write it.
    unchanged = client.get(f"{MEMOS_URL}/{bad}/payment", headers=brand.headers).json()
    assert unchanged["method"] is None
    assert unchanged["reference"] is None


# --- what it must not reveal or accept ------------------------------------------


def test_another_brands_deal_is_refused_as_not_found(client, db, clock, brand):
    other_brand = brand_user(db, clock)
    theirs = approved_deal(client, other_brand, creator_user(db, clock))

    result = mark(client, brand, row(theirs)).json()["results"][0]

    assert result["outcome"] == "refused"
    assert result["problem"]["code"] == "memo_not_found"
    assert result["problem"]["status"] == 404
    # Nothing happened to their payment.
    assert payment_state(client, other_brand, theirs) == "due"


def test_an_unknown_deal_is_refused_as_not_found(client, brand):
    result = mark(client, brand, row(uuid.uuid4())).json()["results"][0]

    assert result["problem"]["code"] == "memo_not_found"


def test_a_deal_with_no_payment_record_yet_is_refused(client, db, clock, brand):
    not_approved = accepted_memo(client, brand, creator_user(db, clock))

    result = mark(client, brand, row(not_approved)).json()["results"][0]

    assert result["problem"]["code"] == "payment_record_not_found"


def test_a_deal_listed_twice_refuses_the_whole_request(client, db, clock, brand):
    memo_id = approved_deal(client, brand, creator_user(db, clock))

    response = mark(client, brand, row(memo_id), row(memo_id, "412345678902"))

    assert response.status_code == 422
    assert payment_state(client, brand, memo_id) == "due"


@pytest.mark.parametrize(
    "payments",
    [
        [],
        [row(uuid.uuid4()) for _ in range(MAX_BULK_MARK_PAID + 1)],
        [row(uuid.uuid4(), method="cheque")],
        [row(uuid.uuid4(), reference="12")],
    ],
    ids=["empty", "over the limit", "unknown method", "reference too short"],
)
def test_a_request_that_is_not_usable_is_refused_whole(client, brand, payments):
    response = client.post(URL, json={"payments": payments}, headers=brand.headers)

    assert response.status_code == 422


# --- who may use it ------------------------------------------------------------------


def test_a_creator_cannot_use_it(client, db, clock):
    creator = creator_user(db, clock)

    response = mark(client, creator, row(uuid.uuid4()))

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_a_brand_without_a_profile_is_told_to_finish_it(client, db, clock):
    account = create_account(db, "brand")

    response = mark(client, User(account.id, "brand", clock), row(uuid.uuid4()))

    assert response.status_code == 409
    assert response.json()["code"] == "brand_profile_required"


def test_it_needs_a_token(client):
    response = client.post(URL, json={"payments": [row(uuid.uuid4())]})

    assert response.status_code == 401


def test_it_is_rate_limited_more_tightly_than_a_single_write(client, brand):
    for _ in range(int(BULK_LIMIT.split()[0])):
        assert mark(client, brand, row(uuid.uuid4())).status_code == 200

    response = mark(client, brand, row(uuid.uuid4()))

    assert response.status_code == 429


# --- retries -------------------------------------------------------------------------


@pytest.fixture
def store() -> Iterator[None]:
    connection = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    connection.flushdb()
    set_store(RedisIdempotencyStore(connection))
    try:
        yield
    finally:
        set_store(None)
        connection.flushdb()
        connection.close()


def test_a_retry_gets_the_original_answer_and_notifies_nobody_twice(
    client, db, clock, brand, store
):
    creator = creator_user(db, clock)
    memo_id = approved_deal(client, brand, creator)
    headers = {**brand.headers, HEADER: str(uuid.uuid4())}

    first = mark(client, brand, row(memo_id), headers=headers)
    second = mark(client, brand, row(memo_id), headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.headers[REPLAYED_HEADER] == "true"
    assert second.json() == first.json()
    assert first.json()["results"][0]["outcome"] == "recorded"
    assert notification_types(client, creator).count("payment_marked_paid") == 1

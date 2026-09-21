"""Reading a creator's delivery record over HTTP, end to end through real deals."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.db.session import engine
from app.modules.auth.models.creator import Creator
from app.modules.deal_memo.delivery_router import READ_LIMIT
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user


def record_url(creator_id) -> str:
    return f"/api/v1/creators/{creator_id}/delivery-record"


def creator_id_of(db, user: User) -> str:
    return str(db.scalar(select(Creator.id).where(Creator.account_id == user.account_id)))


def delivered_deal(client: TestClient, brand: User, creator: User, **memo_fields) -> str:
    """One deal taken all the way to approved work."""
    memo_id = accepted_memo(client, brand, creator, **memo_fields)
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


@contextmanager
def count_queries() -> Iterator[list[str]]:
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


# --- what it says ----------------------------------------------------------


def test_a_creator_with_no_deals_reads_as_new(client, db, brand, creator):
    response = client.get(record_url(creator_id_of(db, creator)), headers=brand.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "new_creator_no_history_yet"
    assert body["deals_completed"] == 0
    assert body["currently_overdue"] == 0
    assert body["delivered_on_time_share"] is None
    assert body["disclosure_confirmed_share"] is None


def test_three_delivered_deals_read_as_a_clean_record(client, db, brand, creator):
    for _ in range(3):
        delivered_deal(client, brand, creator)

    body = client.get(
        record_url(creator_id_of(db, creator)), headers=brand.headers
    ).json()

    assert body["status"] == "has_delivery_history"
    assert body["deals_completed"] == 3
    assert body["deals_delivered"] == 3
    assert body["delivered_on_time_share"] == 1.0
    assert body["disclosure_confirmed_share"] == 1.0


def test_silence_past_the_agreed_date_is_counted_by_the_calendar(
    client, db, brand, creator, clock
):
    accepted_memo(client, brand, creator, content_due_on="2026-09-20")
    clock.advance(timedelta(days=20))

    body = client.get(
        record_url(creator_id_of(db, creator)), headers=brand.headers
    ).json()

    assert body["deals_not_delivered"] == 1
    assert body["currently_overdue"] == 1
    # Still below the floor, and still impossible to miss.
    assert body["status"] == "new_creator_no_history_yet"


def test_a_brand_with_no_history_with_this_creator_can_still_read_it(
    client, db, brand, creator, clock
):
    delivered_deal(client, brand, creator)
    stranger_brand = brand_user(db, clock)

    response = client.get(
        record_url(creator_id_of(db, creator)), headers=stranger_brand.headers
    )

    assert response.status_code == 200
    assert response.json()["deals_delivered"] == 1


def test_a_creator_can_read_their_own_record(client, db, brand, creator):
    delivered_deal(client, brand, creator)

    response = client.get(record_url(creator_id_of(db, creator)), headers=creator.headers)

    assert response.status_code == 200
    assert response.json()["deals_delivered"] == 1


def test_one_creators_deals_never_land_on_another_creators_record(
    client, db, brand, creator, clock
):
    delivered_deal(client, brand, creator)
    other = creator_user(db, clock)

    body = client.get(record_url(creator_id_of(db, other)), headers=brand.headers).json()

    assert body["deals_completed"] == 0
    assert body["deals_delivered"] == 0


# --- who may read it -----------------------------------------------------------


def test_another_creator_cannot_read_it(client, db, creator, clock):
    other = creator_user(db, clock)

    response = client.get(record_url(creator_id_of(db, creator)), headers=other.headers)

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_another_creator_cannot_even_learn_whether_an_id_exists(client, db, clock):
    import uuid

    other = creator_user(db, clock)

    response = client.get(record_url(uuid.uuid4()), headers=other.headers)

    assert response.status_code == 403


def test_it_is_not_public(client, db, creator):
    response = client.get(record_url(creator_id_of(db, creator)))

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_an_unknown_creator_is_not_found(client, brand):
    import uuid

    response = client.get(record_url(uuid.uuid4()), headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_an_invalid_id_is_rejected(client, brand):
    response = client.get(record_url("not-an-id"), headers=brand.headers)

    assert response.status_code == 422


def test_it_is_rate_limited(client, db, brand, creator):
    url = record_url(creator_id_of(db, creator))
    limit = int(READ_LIMIT.split()[0])
    for _ in range(limit):
        assert client.get(url, headers=brand.headers).status_code == 200

    response = client.get(url, headers=brand.headers)

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"


# --- cost ------------------------------------------------------------------


def test_the_number_of_queries_does_not_grow_with_the_number_of_deals(
    client, db, brand, creator
):
    url = record_url(creator_id_of(db, creator))
    delivered_deal(client, brand, creator)
    with count_queries() as one_deal:
        client.get(url, headers=brand.headers)

    for _ in range(3):
        delivered_deal(client, brand, creator)
    with count_queries() as four_deals:
        client.get(url, headers=brand.headers)

    assert len(four_deals) == len(one_deal)

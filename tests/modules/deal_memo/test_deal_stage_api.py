"""The deal's stage through the API: one deal walked through all five (D-076)."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import engine
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)

RRN = "412345678901"


def stage(client: TestClient, user: User, memo_id: str) -> tuple[str, str | None]:
    response = client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return body["stage"], body["waiting_on"]


def listed(client: TestClient, user: User, **params: object) -> list[dict]:
    response = client.get(f"{MEMOS_URL}/mine", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_one_deal_walks_through_all_five_stages(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    assert stage(client, brand, memo_id) == ("agreed", "creator")

    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    assert stage(client, creator, memo_id) == ("in_progress", "brand")

    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    assert stage(client, brand, memo_id) == ("payment", "brand")

    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    assert stage(client, brand, memo_id) == ("payment", "creator")

    client.post(f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers)
    assert stage(client, creator, memo_id) == ("finished", None)


def test_the_list_carries_each_deals_stage(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    row = listed(client, brand)[0]

    assert row["id"] == memo_id
    assert (row["stage"], row["waiting_on"], row["has_open_dispute"]) == (
        "agreed",
        "creator",
        False,
    )


def campaign_of(client: TestClient, user: User, memo_id: str) -> str:
    application_id = client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers).json()[
        "application_id"
    ]
    return client.get(
        f"/api/v1/applications/{application_id}", headers=user.headers
    ).json()["campaign_id"]


def test_the_board_can_ask_for_one_campaigns_deals(client, db, clock):
    brand = brand_user(db, clock)
    first = accepted_memo(client, brand, creator_user(db, clock))
    accepted_memo(client, brand, creator_user(db, clock))

    found = listed(client, brand, campaign_id=campaign_of(client, brand, first))

    assert [row["id"] for row in found] == [first]


def test_another_brands_campaign_filter_finds_nothing(client, db, clock):
    brand, stranger = brand_user(db, clock), brand_user(db, clock)
    memo_id = accepted_memo(client, brand, creator_user(db, clock))

    found = listed(client, stranger, campaign_id=campaign_of(client, brand, memo_id))

    assert found == []


def test_a_malformed_campaign_filter_is_refused(client, db, clock):
    response = client.get(
        f"{MEMOS_URL}/mine",
        params={"campaign_id": "not-an-id"},
        headers=brand_user(db, clock).headers,
    )

    assert response.status_code == 422


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
def three_paid_deals(client, db, clock):
    """One brand, three deals all at payment, so every stage lookup runs."""
    brand = brand_user(db, clock)
    lone_creator = creator_user(db, clock)
    for creator in (lone_creator, creator_user(db, clock), creator_user(db, clock)):
        memo_id = accepted_memo(client, brand, creator)
        proof_id = client.post(
            f"{MEMOS_URL}/{memo_id}/proof",
            json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
            headers=creator.headers,
        ).json()["id"]
        client.post(
            f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
        )
    return brand, lone_creator


def test_stages_for_a_longer_list_cost_no_more_queries(client, three_paid_deals):
    brand, lone_creator = three_paid_deals
    with count_queries() as one:
        assert len(listed(client, lone_creator)) == 1
    with count_queries() as three:
        assert len(listed(client, brand)) == 3

    assert len(three) == len(one)

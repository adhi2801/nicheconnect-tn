"""A campaign at a glance: applicants, deals by stage, and Complete (D-076)."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import engine
from app.modules.deal_memo.stage import DEAL_STAGES
from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    PITCH,
    User,
    brand_user,
    creator_user,
)

RRN = "412345678901"


def summary_url(campaign_id: str) -> str:
    return f"{CAMPAIGNS_URL}/{campaign_id}/summary"


def open_campaign(client: TestClient, brand: User) -> str:
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Diwali gift boxes",
            "description": "Reels showing our new gift boxes in local homes.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 1_500_000,
            "cities": ["Madurai"],
            "niches": ["food"],
            "deliverables": "2 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    published = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers
    )
    assert published.status_code == 200, published.text
    return campaign_id


def apply(client: TestClient, campaign_id: str, creator: User) -> str:
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def agree(client: TestClient, brand: User, creator: User, application_id: str) -> str:
    """Shortlist, accept, write, send and accept a memo: an agreed deal."""
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 Instagram reels.",
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    accepted = client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    assert accepted.status_code == 200, accepted.text
    return memo_id


def finish(client: TestClient, brand: User, creator: User, memo_id: str) -> None:
    """Work sent and approved, money sent and confirmed."""
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    confirmed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )
    assert confirmed.status_code == 200, confirmed.text


def summary(client: TestClient, brand: User, campaign_id: str) -> dict:
    response = client.get(summary_url(campaign_id), headers=brand.headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def board(client, db, clock):
    """Three applicants: one deal finished, one deal at payment, one rejected."""
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    done, paying, turned_down = (creator_user(db, clock) for _ in range(3))
    finished_memo = agree(client, brand, done, apply(client, campaign_id, done))
    finish(client, brand, done, finished_memo)
    paying_memo = agree(client, brand, paying, apply(client, campaign_id, paying))
    proof_id = client.post(
        f"{MEMOS_URL}/{paying_memo}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=paying.headers,
    ).json()["id"]
    client.post(
        f"{MEMOS_URL}/{paying_memo}/proof/{proof_id}/approve", headers=brand.headers
    )
    rejected = apply(client, campaign_id, turned_down)
    client.post(
        f"/api/v1/applications/{rejected}/reject",
        json={"reason": "budget_mismatch"},
        headers=brand.headers,
    )
    return {
        "brand": brand,
        "campaign_id": campaign_id,
        "paying": paying,
        "paying_memo": paying_memo,
    }


# --- the counts --------------------------------------------------------------------------


def test_a_new_campaign_counts_nothing_and_is_not_complete(client, db, clock):
    brand = brand_user(db, clock)
    body = summary(client, brand, open_campaign(client, brand))

    assert set(body["applications"].values()) == {0}
    assert set(body["deals_by_stage"].values()) == {0}
    assert (body["deals_agreed"], body["deals_finished"], body["complete"]) == (
        0,
        0,
        False,
    )


def test_every_stage_is_counted_zeros_included(client, board):
    body = summary(client, board["brand"], board["campaign_id"])

    assert set(body["deals_by_stage"]) == set(DEAL_STAGES)


def test_applicants_and_deals_are_counted_where_they_stand(client, board):
    body = summary(client, board["brand"], board["campaign_id"])

    assert body["applications"]["accepted"] == 2
    assert body["applications"]["rejected"] == 1
    assert body["deals_by_stage"]["finished"] == 1
    assert body["deals_by_stage"]["payment"] == 1
    assert (body["deals_finished"], body["deals_agreed"]) == (1, 2)
    assert body["deals_waiting_on_brand"] == 1  # the payment to mark as sent


# --- complete ----------------------------------------------------------------------------


def close(client: TestClient, brand: User, campaign_id: str) -> None:
    response = client.post(f"{CAMPAIGNS_URL}/{campaign_id}/close", headers=brand.headers)
    assert response.status_code == 200, response.text


def test_closed_with_a_deal_still_open_is_not_complete(client, board):
    close(client, board["brand"], board["campaign_id"])

    assert summary(client, board["brand"], board["campaign_id"])["complete"] is False


def test_closed_with_every_deal_finished_is_complete(client, board):
    brand = board["brand"]
    client.post(
        f"{MEMOS_URL}/{board['paying_memo']}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    client.post(
        f"{MEMOS_URL}/{board['paying_memo']}/payment/confirm",
        headers=board["paying"].headers,
    )
    assert summary(client, brand, board["campaign_id"])["complete"] is False  # still open

    close(client, brand, board["campaign_id"])

    body = summary(client, brand, board["campaign_id"])
    assert (body["deals_finished"], body["deals_agreed"], body["complete"]) == (
        2,
        2,
        True,
    )


def test_closed_with_no_deal_at_all_is_not_complete(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    close(client, brand, campaign_id)

    assert summary(client, brand, campaign_id)["complete"] is False


# --- cost and access ---------------------------------------------------------------------


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


def test_a_bigger_campaign_costs_no_more_queries(client, db, clock, board):
    brand = board["brand"]
    small = open_campaign(client, brand)
    lone = creator_user(db, clock)
    finish(client, brand, lone, agree(client, brand, lone, apply(client, small, lone)))

    with count_queries() as one_deal:
        summary(client, brand, small)
    with count_queries() as two_deals:
        summary(client, brand, board["campaign_id"])

    assert len(two_deals) == len(one_deal)


def test_another_brands_campaign_is_not_found(client, db, clock, board):
    stranger = brand_user(db, clock)

    response = client.get(summary_url(board["campaign_id"]), headers=stranger.headers)

    assert response.status_code == 404


def test_a_creator_cannot_read_a_campaigns_summary(client, board):
    response = client.get(
        summary_url(board["campaign_id"]), headers=board["paying"].headers
    )

    assert response.status_code == 403


def test_it_needs_a_login(client, board):
    assert client.get(summary_url(board["campaign_id"])).status_code == 401


def test_an_unknown_campaign_is_not_found(client, db, clock):
    response = client.get(
        summary_url("00000000-0000-4000-8000-000000000000"),
        headers=brand_user(db, clock).headers,
    )

    assert response.status_code == 404


def test_a_memo_left_unanswered_keeps_it_from_complete(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    done = creator_user(db, clock)
    finish(
        client, brand, done, agree(client, brand, done, apply(client, campaign_id, done))
    )
    waiting = creator_user(db, clock)
    application_id = apply(client, campaign_id, waiting)
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 Instagram reels.",
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    close(client, brand, campaign_id)

    body = summary(client, brand, campaign_id)
    assert body["deals_by_stage"]["memo_sent"] == 1
    assert (body["deals_finished"], body["deals_agreed"], body["complete"]) == (
        1,
        1,
        False,
    )

"""A brand never ends a deal to avoid paying for posted work (D-147).

Proof is evidence of work already posted. Two holes closed:

- a brand cancelling while proof waited inside its review window ended the deal
  before the clock could approve it (D-146), so no payment was ever owed. It now
  answers the proof first: approves it, or asks for a fix;
- a deal cancelled after its proof was approved still owes its payment, but
  counted as finished, so the brand could delete its account with money owed.
  It now holds the deletion until the creator confirms the money arrived.
"""

from datetime import timedelta

import pytest

from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    PAYMENT_REFERENCE,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.modules.deal_memo.test_barter_shipment_api import barter_memo

DELETION_URL = "/api/v1/me/deletion"


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def send_proof(client, creator: User, memo_id: str) -> str:
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert proof.status_code == 201, proof.text
    return str(proof.json()["id"])


def cancel(client, brand: User, memo_id: str):
    return client.post(f"{MEMOS_URL}/{memo_id}/cancel", headers=brand.headers)


def held_by(client, user: User) -> list[str]:
    response = client.get(DELETION_URL, headers=user.headers)
    assert response.status_code == 200, response.text
    return list(response.json()["unfinished_deal_ids"])


def memo_status(client, user: User, memo_id: str) -> str:
    return str(
        client.get(f"{MEMOS_URL}/{memo_id}", headers=user.headers).json()["status"]
    )


def test_a_brand_cannot_cancel_while_proof_waits(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    send_proof(client, creator, memo_id)

    assert_problem(cancel(client, brand, memo_id), 409, "proof_awaiting_answer")
    assert memo_status(client, brand, memo_id) == "accepted"


def test_a_brand_may_cancel_once_it_asked_for_a_fix(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    proof_id = send_proof(client, creator, memo_id)
    asked = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "Please add the paid-partnership label to the reel."},
        headers=brand.headers,
    )
    assert asked.status_code == 200, asked.text

    assert cancel(client, brand, memo_id).status_code == 200


def test_the_creator_may_still_cancel_while_proof_waits(client, brand, creator):
    """The rule protects the creator; it never traps them in a deal."""
    memo_id = accepted_memo(client, brand, creator)
    send_proof(client, creator, memo_id)

    cancelled = client.post(f"{MEMOS_URL}/{memo_id}/withdraw", headers=creator.headers)

    assert cancelled.status_code == 200, cancelled.text


def test_cancelling_after_approval_still_owes_and_holds_deletion(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    proof_id = send_proof(client, creator, memo_id)
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text

    assert cancel(client, brand, memo_id).status_code == 200

    assert held_by(client, brand) == [memo_id]
    assert held_by(client, creator) == [memo_id]


def test_once_the_window_closed_the_brand_may_cancel_and_still_owes(
    client, clock, brand, creator
):
    memo_id = accepted_memo(client, brand, creator)
    send_proof(client, creator, memo_id)
    clock.advance(timedelta(days=8))  # past the 7-day window: the clock approved it

    assert cancel(client, brand, memo_id).status_code == 200

    assert held_by(client, brand) == [memo_id]


def test_the_hold_lifts_when_the_creator_confirms_the_money(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    proof_id = send_proof(client, creator, memo_id)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    assert cancel(client, brand, memo_id).status_code == 200

    marked = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": PAYMENT_REFERENCE},
        headers=brand.headers,
    )
    assert marked.status_code == 200, marked.text
    assert held_by(client, brand) == [memo_id]  # said to be sent is not arrived

    confirmed = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    assert held_by(client, brand) == []


def test_a_cancelled_barter_deal_owes_nothing(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    proof_id = send_proof(client, creator, memo_id)
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)

    assert cancel(client, brand, memo_id).status_code == 200

    assert held_by(client, brand) == []


def test_a_deal_cancelled_before_any_proof_owes_nothing(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    assert cancel(client, brand, memo_id).status_code == 200

    assert held_by(client, brand) == []

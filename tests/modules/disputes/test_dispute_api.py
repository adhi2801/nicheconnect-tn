"""Raising and answering a dispute over HTTP, from both sides of a real deal."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    accepted_memo,
    brand_user,
    creator_user,
)

RRN = "412345678901"
REASON = "The payment was marked sent on 8 September but nothing has reached my account."
RECEIPT = "https://example.com/upi-receipt.png"


def dispute_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/payment/dispute"


@pytest.fixture
def deal(client: TestClient, db, clock):
    """A deal with approved work and a payment the brand says it sent."""
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
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
    return {"memo_id": memo_id, "brand": brand, "creator": creator, "clock": clock}


def raise_dispute(client, deal, who="creator", reason=REASON):
    return client.post(
        dispute_url(deal["memo_id"]),
        json={"reason": reason},
        headers=deal[who].headers,
    )


# --- raising one ----------------------------------------------------------


def test_a_creator_can_say_the_money_never_came(client, deal):
    response = raise_dispute(client, deal)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["opened_by"] == "creator"
    assert body["state"] == "open"
    assert body["outcome"] is None


def test_a_brand_can_raise_one_too(client, deal):
    """Not only creators are wronged. A brand may say the work was not what
    was agreed."""
    response = raise_dispute(
        client,
        deal,
        who="brand",
        reason="The reel was posted and then deleted within a day.",
    )

    assert response.status_code == 201
    assert response.json()["opened_by"] == "brand"


def test_the_reason_opens_the_timeline(client, deal):
    body = raise_dispute(client, deal).json()

    assert len(body["timeline"]) == 1
    assert body["timeline"][0]["kind"] == "opened"
    assert body["timeline"][0]["note"] == REASON


def test_the_other_side_has_seven_days_to_answer(client, deal):
    body = raise_dispute(client, deal).json()

    opened_on = body["created_at"][:10]
    assert body["response_due_on"] > opened_on


def test_a_payment_can_only_be_disputed_once(client, deal):
    raise_dispute(client, deal)

    again = raise_dispute(client, deal, who="brand")

    assert again.status_code == 409
    assert again.json()["code"] == "dispute_already_open"


def test_a_reason_that_says_nothing_is_refused(client, deal):
    response = client.post(
        dispute_url(deal["memo_id"]),
        json={"reason": "not paid"},
        headers=deal["creator"].headers,
    )

    assert response.status_code == 422


def test_there_is_nothing_to_dispute_before_a_payment_exists(client, db, clock):
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    response = client.post(
        dispute_url(memo_id), json={"reason": REASON}, headers=creator.headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "payment_record_not_found"


# --- both sides, one record -----------------------------------------------


def test_both_sides_read_the_same_record(client, deal):
    raise_dispute(client, deal)

    as_creator = client.get(dispute_url(deal["memo_id"]), headers=deal["creator"].headers)
    as_brand = client.get(dispute_url(deal["memo_id"]), headers=deal["brand"].headers)

    assert as_creator.json() == as_brand.json()


def test_the_brand_can_answer_on_the_record(client, deal):
    raise_dispute(client, deal)

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={
            "note": "Sent by UPI on the 8th, receipt attached.",
            "evidence_url": RECEIPT,
        },
        headers=deal["brand"].headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "response"
    assert body["evidence_url"] == RECEIPT


def test_the_side_that_raised_it_adds_evidence_not_a_response(client, deal):
    raise_dispute(client, deal)

    body = client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={"note": "Here is my bank statement for that week."},
        headers=deal["creator"].headers,
    ).json()

    assert body["kind"] == "evidence"


def test_the_timeline_keeps_the_order_things_were_said(client, deal):
    raise_dispute(client, deal)
    deal["clock"].advance(timedelta(days=1))
    client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={"note": "Sent by UPI, receipt attached.", "evidence_url": RECEIPT},
        headers=deal["brand"].headers,
    )
    deal["clock"].advance(timedelta(days=1))
    client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={"note": "That reference does not appear on my statement."},
        headers=deal["creator"].headers,
    )

    timeline = client.get(
        dispute_url(deal["memo_id"]), headers=deal["creator"].headers
    ).json()["timeline"]

    assert [entry["actor_role"] for entry in timeline] == ["creator", "brand", "creator"]
    assert [entry["kind"] for entry in timeline] == ["opened", "response", "evidence"]


def test_an_entry_must_actually_say_something(client, deal):
    raise_dispute(client, deal)

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/entries", json={}, headers=deal["brand"].headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "nothing_to_record"


def test_a_late_account_is_still_accepted(client, deal):
    """Refusing it would make the record less true, not more orderly."""
    raise_dispute(client, deal)
    deal["clock"].advance(timedelta(days=60))

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={"note": "Only just saw this, sorry. Here is what happened."},
        headers=deal["brand"].headers,
    )

    assert response.status_code == 201


# --- nobody outside sees it -----------------------------------------------


def test_a_stranger_cannot_read_it(client, db, deal, clock):
    raise_dispute(client, deal)
    outsider = brand_user(db, clock)

    response = client.get(dispute_url(deal["memo_id"]), headers=outsider.headers)

    assert response.status_code == 404


def test_reading_it_needs_a_login(client, deal):
    raise_dispute(client, deal)

    assert client.get(dispute_url(deal["memo_id"])).status_code == 401


# --- how it ends ----------------------------------------------------------


def test_settling_it_by_phone_is_a_real_outcome(client, deal):
    raise_dispute(client, deal)

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/close",
        json={
            "outcome": "resolved_informally",
            "note": "Sorted on a call, money received.",
        },
        headers=deal["creator"].headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "resolved_informally"


def test_closing_it_lands_on_the_timeline(client, deal):
    raise_dispute(client, deal)
    # Nobody opens and closes a dispute in the same microsecond, and two
    # entries at the very same instant have no honest order to give.
    deal["clock"].advance(timedelta(days=1))

    body = client.post(
        f"{dispute_url(deal['memo_id'])}/close",
        json={"outcome": "resolved_paid"},
        headers=deal["brand"].headers,
    ).json()

    assert body["timeline"][-1]["kind"] == "closed"


def test_nothing_is_added_after_it_is_settled(client, deal):
    raise_dispute(client, deal)
    client.post(
        f"{dispute_url(deal['memo_id'])}/close",
        json={"outcome": "resolved_paid"},
        headers=deal["brand"].headers,
    )

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/entries",
        json={"note": "One more thing I forgot to mention."},
        headers=deal["creator"].headers,
    )

    assert response.status_code == 409


def test_an_outcome_that_blames_somebody_is_not_accepted(client, deal):
    """There is no endpoint that decides who was right, and there is not
    going to be one (D-028)."""
    raise_dispute(client, deal)

    response = client.post(
        f"{dispute_url(deal['memo_id'])}/close",
        json={"outcome": "creator_was_lying"},
        headers=deal["brand"].headers,
    )

    assert response.status_code == 422


def test_thirty_days_of_silence_reads_as_unresolved(client, deal):
    raise_dispute(client, deal)
    deal["clock"].advance(timedelta(days=31))

    body = client.get(
        dispute_url(deal["memo_id"]), headers=deal["creator"].headers
    ).json()

    assert body["state"] == "unresolved"
    assert body["outcome"] is None


# --- what it does to the payment ------------------------------------------


def test_an_open_dispute_holds_the_payment_short_of_unpaid(client, db, clock):
    """A payment being argued about is not a payment nobody will discuss."""
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={"reason": REASON},
        headers=creator.headers,
    )
    clock.advance(timedelta(days=25))

    payment = client.get(f"{MEMOS_URL}/{memo_id}/payment", headers=creator.headers).json()

    assert payment["has_open_dispute"] is True
    assert payment["state"] == "late"

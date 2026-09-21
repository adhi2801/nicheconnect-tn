"""The payment handshake: the brand says it sent it, the creator says it came.

Two statements of different kinds. "I sent it" is a claim only the brand can
make; "it arrived" is a fact only the creator can confirm. Neither side can
make the other's, and these tests are what hold that apart.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.modules.payment_status import service
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    accepted_memo,
    brand_user,
    creator_user,
)

RRN = "412345678901"
NEFT_UTR = "SBIN226092012345"


def payment_url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/payment"


@pytest.fixture
def deal(client: TestClient, db, clock):
    """A deal whose work has been submitted and approved, so payment is open."""
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    submitted = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert submitted.status_code == 201, submitted.text
    proof_id = submitted.json()["id"]
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    return {"memo_id": memo_id, "brand": brand, "creator": creator, "clock": clock}


# --- the record appears when the work is approved -------------------------


def test_approving_the_work_opens_the_payment_record(client, deal):
    """Approval is what starts the payment clock (D-027)."""
    response = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount_paise"] == 800_000
    assert body["currency"] == "INR"
    assert body["state"] == "due"
    assert body["marked_paid_at"] is None


def test_payment_is_due_seven_days_after_approval(client, deal):
    body = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers).json()

    approved_on = service.india_date(deal["clock"].now)
    assert body["due_on"] == (approved_on + timedelta(days=7)).isoformat()


def test_both_sides_see_the_same_record(client, deal):
    as_brand = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers)
    as_creator = client.get(payment_url(deal["memo_id"]), headers=deal["creator"].headers)

    assert as_brand.json() == as_creator.json()


def test_a_deal_with_no_approved_work_has_no_payment_record(client, db, clock):
    brand = brand_user(db, clock)
    creator = creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)

    response = client.get(payment_url(memo_id), headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "payment_record_not_found"


# --- who may say what -----------------------------------------------------


def test_the_brand_marks_it_paid(client, deal):
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "paid"
    assert body["method"] == "upi"
    assert body["marked_paid_at"] is not None


def test_a_creator_cannot_claim_the_brand_paid(client, deal):
    """The claim is the brand's to make; nobody can make it for them."""
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["creator"].headers,
    )

    assert response.status_code in (403, 404)


def test_the_creator_confirms_it_arrived(client, deal):
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    response = client.post(
        f"{payment_url(deal['memo_id'])}/confirm", headers=deal["creator"].headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "confirmed"


def test_a_brand_cannot_confirm_its_own_payment(client, deal):
    """Otherwise 'confirmed' would mean nothing at all."""
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    response = client.post(
        f"{payment_url(deal['memo_id'])}/confirm", headers=deal["brand"].headers
    )

    assert response.status_code in (403, 404)


def test_nothing_can_be_confirmed_before_it_is_claimed(client, deal):
    response = client.post(
        f"{payment_url(deal['memo_id'])}/confirm", headers=deal["creator"].headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "payment_not_marked_paid"


def test_it_cannot_be_marked_paid_twice(client, deal):
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "cash", "reference": "paid at the shop"},
        headers=deal["brand"].headers,
    )

    again = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    assert again.status_code == 409
    assert again.json()["code"] == "payment_already_marked_paid"


# --- a stranger sees nothing ----------------------------------------------


def test_someone_elses_deal_is_not_visible(client, db, deal, clock):
    outsider = brand_user(db, clock)

    response = client.get(payment_url(deal["memo_id"]), headers=outsider.headers)

    assert response.status_code == 404


def test_reading_it_needs_a_login(client, deal):
    assert client.get(payment_url(deal["memo_id"])).status_code == 401


# --- what the record says -------------------------------------------------


def test_a_upi_reference_is_flagged_as_checkable(client, deal):
    """Only a real 12-digit UPI reference could ever be matched (D-027)."""
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    assert response.json()["reference_auto_matchable"] is True


def test_a_bank_reference_is_recorded_but_not_checkable(client, deal):
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "bank_transfer", "reference": NEFT_UTR},
        headers=deal["brand"].headers,
    )

    body = response.json()
    assert body["reference"] == NEFT_UTR
    assert body["reference_auto_matchable"] is False


def test_cash_at_an_event_is_a_perfectly_good_record(client, deal):
    """A Tamil Nadu shop paying cash must not be stuck looking unpaid."""
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "cash", "reference": "Handed over at the Pongal event"},
        headers=deal["brand"].headers,
    )

    assert response.status_code == 200
    assert response.json()["state"] == "paid"


@pytest.mark.parametrize(
    "body",
    [
        {"method": "cheque", "reference": RRN},
        {"method": "upi", "reference": "ab"},
        {"method": "upi"},
        {"method": "upi", "reference": RRN, "note": "extra"},
    ],
)
def test_a_bad_claim_is_refused(client, deal, body):
    response = client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json=body,
        headers=deal["brand"].headers,
    )

    assert response.status_code == 422


# --- the clock ------------------------------------------------------------


def test_it_reads_late_once_the_due_date_passes(client, deal):
    deal["clock"].advance(timedelta(days=8))

    body = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers).json()

    assert body["state"] == "late"
    assert body["days_overdue"] == 1


def test_it_reads_unpaid_after_long_silence(client, deal):
    deal["clock"].advance(timedelta(days=40))

    body = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers).json()

    assert body["state"] == "unpaid"


def test_the_state_moves_without_anything_running_on_a_schedule(client, deal):
    """The whole reason there is no status column: no job, no staleness."""
    seen = []
    for days in (0, 8, 40):
        deal["clock"].advance(timedelta(days=days))
        seen.append(
            client.get(
                payment_url(deal["memo_id"]), headers=deal["brand"].headers
            ).json()["state"]
        )

    assert seen == ["due", "late", "unpaid"]


def test_paying_late_still_reads_as_paid(client, deal):
    """Being late is not a permanent mark on the record; not paying is."""
    deal["clock"].advance(timedelta(days=30))

    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )
    body = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers).json()

    assert body["state"] == "paid"
    assert body["days_overdue"] == 0


# --- a dropped connection -------------------------------------------------


def test_marking_it_paid_twice_from_one_tap_records_it_once(client, deal):
    """backend.md section 2 names payment POSTs for Idempotency-Key.

    A retry must not become a second claim, nor come back as a confusing
    conflict about something the brand already did.
    """
    import redis

    from app.core.idempotency import HEADER, RedisIdempotencyStore, set_store

    store_client = redis.Redis.from_url("redis://localhost:6379/2", decode_responses=True)
    store_client.flushdb()
    set_store(RedisIdempotencyStore(store_client))
    try:
        key = "0f9c2a44-1111-4e22-9abc-7d5e6f801234"
        headers = {**deal["brand"].headers, HEADER: key}
        body = {"method": "upi", "reference": RRN}

        first = client.post(
            f"{payment_url(deal['memo_id'])}/mark-paid", json=body, headers=headers
        )
        retry = client.post(
            f"{payment_url(deal['memo_id'])}/mark-paid", json=body, headers=headers
        )

        assert first.status_code == 200, first.text
        assert retry.status_code == 200
        assert retry.json() == first.json()
    finally:
        set_store(None)
        store_client.flushdb()
        store_client.close()


# --- when the creator never answers ---------------------------------------


def test_the_record_says_plainly_when_the_creator_never_answered(client, deal):
    """A brand that genuinely paid must not look unconfirmed forever, and a
    creator must not have a confirmation put in their mouth."""
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )
    deal["clock"].advance(timedelta(days=8))

    body = client.get(payment_url(deal["memo_id"]), headers=deal["brand"].headers).json()

    assert body["state"] == "unconfirmed"
    assert body["confirmed_at"] is None


def test_the_creator_can_still_confirm_long_afterwards(client, deal):
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )
    deal["clock"].advance(timedelta(days=45))

    response = client.post(
        f"{payment_url(deal['memo_id'])}/confirm", headers=deal["creator"].headers
    )

    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"


def test_the_creator_is_told_to_look_for_the_money(client, deal):
    """Otherwise nothing ever prompts them to confirm."""
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )

    notifications = client.get(
        "/api/v1/notifications", headers=deal["creator"].headers
    ).json()["items"]

    assert "payment_marked_paid" in {n["notification_type"] for n in notifications}


def test_the_brand_is_told_the_money_landed(client, deal):
    client.post(
        f"{payment_url(deal['memo_id'])}/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=deal["brand"].headers,
    )
    client.post(f"{payment_url(deal['memo_id'])}/confirm", headers=deal["creator"].headers)

    notifications = client.get(
        "/api/v1/notifications", headers=deal["brand"].headers
    ).json()["items"]

    assert "payment_confirmed" in {n["notification_type"] for n in notifications}

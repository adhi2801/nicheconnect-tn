"""GET /api/v1/me/attention, end to end through real deals.

Every kind is checked twice: it appears, with the right deadline, when
something is waiting, and it disappears the moment that thing is done. An
item that lingers after the work is done is as wrong as one that never
shows. The clock starts at FIXED_NOW, 12:00 UTC on 17 September 2026, which
is the same date in Tamil Nadu.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.attention import BRAND_KINDS, CREATOR_KINDS
from app.db.session import engine
from app.modules.auth.attention_router import READ_LIMIT
from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    LINK,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import create_account

URL = "/api/v1/me/attention"
REASON = "The payment was marked as sent but nothing has reached my account yet."


# --- journeys --------------------------------------------------------------------


def attention(client: TestClient, user: User) -> dict:
    response = client.get(URL, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def items_of(client: TestClient, user: User, kind: str) -> list[dict]:
    return [item for item in attention(client, user)["items"] if item["kind"] == kind]


def open_campaign(
    client: TestClient, brand: User, title: str = "Morning run club"
) -> str:
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": title,
            "description": "Two reels about our new trail shoes.",
            "campaign_type": "paid",
            "budget_min_paise": 300_000,
            "budget_max_paise": 800_000,
            "cities": ["Coimbatore"],
            "niches": ["fitness"],
            "deliverables": "2 reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    return str(campaign_id)


def apply(client: TestClient, creator: User, campaign_id: str) -> str:
    response = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def accepted_application(client: TestClient, brand: User, creator: User) -> str:
    application_id = apply(client, creator, open_campaign(client, brand))
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    return application_id


def sent_memo(client: TestClient, brand: User, creator: User) -> str:
    application_id = accepted_application(client, brand, creator)
    memo_id = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 reels",
            "fee_amount_paise": 600_000,
            "content_due_on": AGREED_DUE_ON,
        },
        headers=brand.headers,
    ).json()["id"]
    sent = client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert sent.status_code == 200, sent.text
    return str(memo_id)


def submit_proof(client: TestClient, creator: User, memo_id: str) -> str:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def approved_deal(client: TestClient, brand: User, creator: User) -> str:
    """Work approved on 17 September: the payment is due on the 24th."""
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)
    approved = client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers
    )
    assert approved.status_code == 200, approved.text
    return memo_id


def mark_paid(client: TestClient, brand: User, memo_id: str) -> None:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )
    assert response.status_code == 200, response.text


def raise_dispute(client: TestClient, user: User, memo_id: str) -> None:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute",
        json={"reason": REASON},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text


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


# --- a brand ---------------------------------------------------------------------


def test_a_new_brand_has_nothing_waiting_and_every_kind_counted(client, db, clock):
    body = attention(client, brand_user(db, clock))

    assert body["role"] == "brand"
    assert body["as_of"] == "2026-09-17"
    assert (body["total"], body["truncated"], body["items"]) == (0, False, [])
    assert body["counts"] == dict.fromkeys(BRAND_KINDS, 0)


def test_applications_waiting_are_one_item_per_campaign_until_decided(client, db, clock):
    brand = brand_user(db, clock)
    campaign_id = open_campaign(client, brand)
    first = apply(client, creator_user(db, clock), campaign_id)
    second = apply(client, creator_user(db, clock), campaign_id)
    client.post(f"/api/v1/applications/{second}/shortlist", headers=brand.headers)

    [item] = items_of(client, brand, "review_applications")
    assert (item["campaign_id"], item["count"], item["due_on"]) == (campaign_id, 2, None)

    for application_id in (first, second):
        client.post(
            f"/api/v1/applications/{application_id}/reject",
            json={"reason": "timing"},
            headers=brand.headers,
        )
    assert items_of(client, brand, "review_applications") == []


def test_an_accepted_creator_without_a_memo_is_a_memo_to_draft(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    application_id = accepted_application(client, brand, creator)

    [item] = items_of(client, brand, "draft_memo")
    assert item["application_id"] == application_id
    assert item["counterparty"].startswith("proof")  # the creator's handle

    client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "2 reels", "fee_amount_paise": 600_000},
        headers=brand.headers,
    )
    assert items_of(client, brand, "draft_memo") == []


def test_a_memo_the_creator_questioned_is_back_with_the_brand(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = sent_memo(client, brand, creator)
    client.post(
        f"{MEMOS_URL}/{memo_id}/request-change",
        json={"message": "Can we make it one reel for the same fee?"},
        headers=creator.headers,
    )

    [item] = items_of(client, brand, "revise_memo")
    assert (item["memo_id"], item["due_on"]) == (memo_id, AGREED_DUE_ON)

    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert items_of(client, brand, "revise_memo") == []


def test_proof_to_review_is_due_the_day_it_would_approve_itself(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)

    [item] = items_of(client, brand, "review_proof")
    assert (item["proof_id"], item["due_on"], item["days_left"]) == (
        proof_id,
        "2026-09-24",
        7,
    )

    # The window runs out: the proof approves itself, and nothing is left
    # for the brand to decide. The clock settles it, not a scheduled job.
    clock.advance(timedelta(days=7))
    assert items_of(client, brand, "review_proof") == []


def test_a_payment_owed_is_listed_until_the_brand_says_it_paid(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = approved_deal(client, brand, creator)

    [item] = items_of(client, brand, "pay_creator")
    assert item["memo_id"] == memo_id
    assert (item["due_on"], item["days_left"]) == ("2026-09-24", 7)
    assert (item["amount_paise"], item["currency"]) == (800_000, "INR")

    mark_paid(client, brand, memo_id)
    assert items_of(client, brand, "pay_creator") == []


def test_a_dispute_the_creator_raised_waits_for_the_brands_account(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = approved_deal(client, brand, creator)
    raise_dispute(client, creator, memo_id)

    [item] = items_of(client, brand, "respond_to_dispute")
    assert (item["memo_id"], item["due_on"]) == (memo_id, "2026-09-24")
    # The one who raised it has nothing to answer.
    assert items_of(client, creator, "respond_to_dispute") == []

    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/dispute/entries",
        json={"note": "We paid on the 20th; the bank reference is attached."},
        headers=brand.headers,
    )
    assert items_of(client, brand, "respond_to_dispute") == []


# --- a creator -------------------------------------------------------------------


def test_a_new_creator_has_nothing_waiting_and_every_kind_counted(client, db, clock):
    body = attention(client, creator_user(db, clock))

    assert body["role"] == "creator"
    assert body["counts"] == dict.fromkeys(CREATOR_KINDS, 0)
    assert body["items"] == []


def test_a_memo_to_answer_is_due_by_the_agreed_date(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = sent_memo(client, brand, creator)

    [item] = items_of(client, creator, "answer_memo")
    assert (item["memo_id"], item["due_on"]) == (memo_id, AGREED_DUE_ON)
    assert item["counterparty"]  # the brand's name

    client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    assert items_of(client, creator, "answer_memo") == []
    # Accepting turns it into work to deliver.
    assert [i["memo_id"] for i in items_of(client, creator, "deliver_work")] == [memo_id]


def test_work_waiting_on_the_brand_is_not_the_creators_to_do(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    [item] = items_of(client, creator, "deliver_work")
    assert item["due_on"] == AGREED_DUE_ON

    submit_proof(client, creator, memo_id)
    assert items_of(client, creator, "deliver_work") == []


def test_changes_asked_for_become_work_to_resubmit(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = accepted_memo(client, brand, creator)
    proof_id = submit_proof(client, creator, memo_id)
    client.post(
        f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/request-revision",
        json={"note": "Please add the product name in the caption."},
        headers=brand.headers,
    )

    assert [i["memo_id"] for i in items_of(client, creator, "resubmit_work")] == [memo_id]
    assert items_of(client, creator, "deliver_work") == []

    submit_proof(client, creator, memo_id)
    assert items_of(client, creator, "resubmit_work") == []


def test_money_the_brand_says_it_sent_waits_for_the_creators_confirmation(
    client, db, clock
):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = approved_deal(client, brand, creator)
    assert items_of(client, creator, "confirm_payment") == []

    mark_paid(client, brand, memo_id)
    [item] = items_of(client, creator, "confirm_payment")
    assert (item["due_on"], item["amount_paise"]) == ("2026-09-24", 800_000)

    client.post(f"{MEMOS_URL}/{memo_id}/payment/confirm", headers=creator.headers)
    assert items_of(client, creator, "confirm_payment") == []


def test_a_payment_past_its_date_is_overdue_on_both_sides(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    approved_deal(client, brand, creator)
    # Not due yet: nothing for the creator to act on.
    assert items_of(client, creator, "payment_overdue") == []

    clock.advance(timedelta(days=10))  # 27 September; due on the 24th

    [owed] = items_of(client, brand, "pay_creator")
    [overdue] = items_of(client, creator, "payment_overdue")
    assert owed["days_left"] == overdue["days_left"] == -3


def test_a_dispute_the_brand_raised_waits_for_the_creators_account(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    memo_id = approved_deal(client, brand, creator)
    mark_paid(client, brand, memo_id)
    raise_dispute(client, brand, memo_id)

    [item] = items_of(client, creator, "respond_to_dispute")
    assert item["memo_id"] == memo_id

    # Thirty days on it is `unresolved`, a fact, and nothing is left to answer.
    clock.advance(timedelta(days=31))
    assert items_of(client, creator, "respond_to_dispute") == []


# --- across the whole list -------------------------------------------------------


def test_the_most_urgent_comes_first(client, db, clock):
    brand = brand_user(db, clock)
    approved_deal(client, brand, creator_user(db, clock))  # payment due the 24th
    apply(client, creator_user(db, clock), open_campaign(client, brand))  # undated
    clock.advance(timedelta(days=10))  # the payment is now 3 days late
    reviewing = accepted_memo(client, brand, creator := creator_user(db, clock))
    submit_proof(client, creator, reviewing)  # review due in 7 days

    kinds = [item["kind"] for item in attention(client, brand)["items"]]

    assert kinds == ["pay_creator", "review_proof", "review_applications"]


def test_nothing_of_anybody_elses_ever_appears(client, db, clock):
    brand, creator = brand_user(db, clock), creator_user(db, clock)
    other_brand, other_creator = brand_user(db, clock), creator_user(db, clock)
    approved_deal(client, other_brand, other_creator)
    apply(client, other_creator, open_campaign(client, other_brand))

    assert attention(client, brand)["total"] == 0
    assert attention(client, creator)["total"] == 0


def test_a_brand_needs_a_profile_first(client, db, clock):
    account = create_account(db, "brand")

    response = client.get(URL, headers=User(account.id, "brand", clock).headers)

    assert response.status_code == 409
    assert response.json()["code"] == "brand_profile_required"


def test_a_creator_needs_a_profile_first(client, db, clock):
    account = create_account(db, "creator")

    response = client.get(URL, headers=User(account.id, "creator", clock).headers)

    assert response.status_code == 409
    assert response.json()["code"] == "creator_profile_required"


def test_it_is_rate_limited(client, db, clock):
    brand = brand_user(db, clock)
    for _ in range(int(READ_LIMIT.split()[0])):
        assert client.get(URL, headers=brand.headers).status_code == 200

    response = client.get(URL, headers=brand.headers)

    assert response.status_code == 429


def test_the_number_of_queries_does_not_grow_with_the_work(client, db, clock):
    brand = brand_user(db, clock)
    approved_deal(client, brand, creator_user(db, clock))
    with count_queries() as one:
        attention(client, brand)

    for _ in range(3):
        approved_deal(client, brand, creator_user(db, clock))
        apply(
            client,
            creator_user(db, clock),
            open_campaign(client, brand, f"C{uuid.uuid4()}"),
        )
    with count_queries() as many:
        body = attention(client, brand)

    assert body["total"] == 7  # 4 payments to make, 3 campaigns with applicants
    assert len(many) == len(one)

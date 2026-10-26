"""A barter deal's shipment on the record (item 68, D-131).

The rules worth proving: only an agreed barter deal takes a shipment; only
its brand records it and only its creator says it arrived, once; every step
is sealed onto the deal record, a correction included; and a row rewritten
behind the app's back shows on the record.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select, text

from app.modules.auth.models.account import Account
from app.modules.deal_memo import record_service
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.deal_memo.shipment_router import WRITE_LIMIT
from app.modules.me import export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import MEMOS_URL, User, accepted_memo, brand_user, creator_user
from tests.modules.deal_memo.test_deal_memo_api import (
    accepted_application,
    draft_memo,
)

NUMBER = "EE123456789IN"


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def barter_memo(client, brand: User, creator: User, *, accept: bool = True) -> str:
    application_id = accepted_application(client, brand, creator, "barter")
    memo = draft_memo(
        client, brand, application_id, fee_amount_paise=None, content_due_on=None
    )
    sent = client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers)
    assert sent.status_code == 200, sent.text
    if accept:
        accepted = client.post(
            f"{MEMOS_URL}/{memo['id']}/accept", headers=creator.headers
        )
        assert accepted.status_code == 200, accepted.text
    return memo["id"]


def url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/shipment"


def ship(client, brand: User, memo_id: str, carrier="india_post", number=NUMBER):
    return client.put(
        url(memo_id),
        json={"carrier": carrier, "tracking_number": number},
        headers=brand.headers,
    )


def shipped(client, brand: User, memo_id: str, **kwargs) -> dict:
    response = ship(client, brand, memo_id, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def receive(client, creator: User, memo_id: str):
    return client.post(f"{url(memo_id)}/received", headers=creator.headers)


def entries(db, memo_id: str, kind: str) -> list[DealRecordEntry]:
    return list(
        db.scalars(
            select(DealRecordEntry)
            .where(DealRecordEntry.deal_memo_id == memo_id, DealRecordEntry.kind == kind)
            .order_by(DealRecordEntry.sequence)
        ).all()
    )


def notices(db, user: User, kind: str) -> int:
    return len(
        db.scalars(
            select(Notification.id).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


def record_of(client, user: User, memo_id: str) -> dict:
    response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- shipping -----------------------------------------------------------------------


def test_the_brand_records_a_shipment_both_sides_read_it(
    client, db, clock, brand, creator
):
    memo_id = barter_memo(client, brand, creator)

    body = shipped(client, brand, memo_id)

    assert (body["carrier"], body["tracking_number"]) == ("india_post", NUMBER)
    assert (body["shipped_at"][:10], body["received_at"]) == (
        clock.now.date().isoformat(),
        None,
    )
    for user in (brand, creator):
        read = client.get(url(memo_id), headers=user.headers)
        assert read.status_code == 200, read.text
        assert read.json() == body
    (entry,) = entries(db, memo_id, "product_shipped")
    assert entry.actor_role == "brand"
    assert entry.facts == {
        "shipment_id": body["id"],
        "carrier": "india_post",
        "tracking_sha256": record_service.fingerprint(NUMBER),
    }
    assert notices(db, creator, "product_shipped") == 1


def test_a_number_is_cleaned_as_couriers_write_it(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)

    body = shipped(client, brand, memo_id, number=" ee 1234-56789 in ")

    assert body["tracking_number"] == NUMBER


@pytest.mark.parametrize(
    ("carrier", "number"),
    [
        ("pigeon", "ABCD12345678"),
        ("india_post", "1234567890123"),  # not India Post's shape
        ("india_post", "EE123456789US"),
        ("delhivery", "AB1234"),  # too short
        ("delhivery", "A" * 21),  # too long
        ("delhivery", "ABC$12345678"),
        ("delhivery", ""),
    ],
)
def test_a_bad_shipment_is_refused(client, brand, creator, carrier, number):
    memo_id = barter_memo(client, brand, creator)

    assert ship(client, brand, memo_id, carrier, number).status_code == 422


def test_a_mistyped_number_is_corrected_and_both_stay_on_the_record(
    client, db, clock, brand, creator
):
    memo_id = barter_memo(client, brand, creator)
    first = shipped(client, brand, memo_id, carrier="delhivery", number="123456789012")
    clock.advance(timedelta(hours=1))

    second = shipped(client, brand, memo_id, carrier="delhivery", number="123456789013")

    assert second["id"] == first["id"]
    assert second["tracking_number"] == "123456789013"
    assert second["shipped_at"] > first["shipped_at"]
    sealed = [e.facts["tracking_sha256"] for e in entries(db, memo_id, "product_shipped")]
    assert sealed == [
        record_service.fingerprint("123456789012"),
        record_service.fingerprint("123456789013"),
    ]


def test_the_same_shipment_again_changes_nothing(client, db, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    first = shipped(client, brand, memo_id)

    again = shipped(client, brand, memo_id)

    assert again == first
    assert len(entries(db, memo_id, "product_shipped")) == 1
    assert notices(db, creator, "product_shipped") == 1


def test_a_paid_deal_takes_no_shipment(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(ship(client, brand, memo_id), 409, "shipment_closed")


def test_a_barter_deal_not_yet_agreed_takes_no_shipment(client, brand, creator):
    memo_id = barter_memo(client, brand, creator, accept=False)

    assert_problem(ship(client, brand, memo_id), 409, "shipment_closed")


def test_only_the_brand_ships(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)

    response = client.put(
        url(memo_id),
        json={"carrier": "india_post", "tracking_number": NUMBER},
        headers=creator.headers,
    )

    assert response.status_code == 403


# --- receiving ----------------------------------------------------------------------


def test_the_creator_says_it_arrived_once(client, db, clock, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    shipped(client, brand, memo_id)
    clock.advance(timedelta(days=2))

    response = receive(client, creator, memo_id)

    assert response.status_code == 200, response.text
    assert response.json()["received_at"][:10] == clock.now.date().isoformat()
    (entry,) = entries(db, memo_id, "product_received")
    assert (entry.actor_role, entry.facts) == (
        "creator",
        {"shipment_id": response.json()["id"]},
    )
    assert notices(db, brand, "product_received") == 1
    assert_problem(receive(client, creator, memo_id), 409, "shipment_already_received")
    assert_problem(
        ship(client, brand, memo_id, number="EE987654321IN"),
        409,
        "shipment_already_received",
    )


def test_nothing_can_arrive_before_it_is_sent(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)

    assert_problem(receive(client, creator, memo_id), 404, "shipment_not_found")
    assert_problem(
        client.get(url(memo_id), headers=brand.headers), 404, "shipment_not_found"
    )


def test_only_the_creator_says_it_arrived(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    shipped(client, brand, memo_id)

    assert receive(client, brand, memo_id).status_code == 403


def test_another_brand_or_creator_reaches_nothing(client, db, clock, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    shipped(client, brand, memo_id)
    other_brand, other_creator = brand_user(db, clock), creator_user(db, clock)

    for user in (other_brand, other_creator):
        assert_problem(
            client.get(url(memo_id), headers=user.headers), 404, "memo_not_found"
        )
    assert_problem(ship(client, other_brand, memo_id), 404, "memo_not_found")
    assert_problem(receive(client, other_creator, memo_id), 404, "memo_not_found")


def test_a_retry_with_the_same_key_says_it_arrived_once(client, db, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    shipped(client, brand, memo_id)
    headers = {**creator.headers, "Idempotency-Key": "received-retry-1"}

    first = client.post(f"{url(memo_id)}/received", headers=headers)
    second = client.post(f"{url(memo_id)}/received", headers=headers)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert len(entries(db, memo_id, "product_received")) == 1


def test_shipping_is_rate_limited(client, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    for _ in range(int(WRITE_LIMIT.split()[0])):
        assert ship(client, brand, memo_id).status_code == 200

    assert ship(client, brand, memo_id).status_code == 429


# --- the record and the exports -------------------------------------------------------


def test_the_record_shows_a_shipment_rewritten_behind_its_back(
    client, db, brand, creator
):
    memo_id = barter_memo(client, brand, creator)
    assert record_of(client, brand, memo_id)["shipment_unchanged"] is None
    shipped(client, brand, memo_id)
    assert record_of(client, brand, memo_id)["shipment_unchanged"] is True

    db.execute(
        text(
            "UPDATE barter_shipment SET tracking_number = 'EE111111111IN' WHERE deal_memo_id = :m"
        ),
        {"m": memo_id},
    )
    db.expire_all()

    for user in (brand, creator):
        body = record_of(client, user, memo_id)
        assert body["shipment_unchanged"] is False
        assert body["intact"] is True  # the chain itself was never touched


def test_both_exports_hold_the_shipment(client, db, clock, brand, creator):
    memo_id = barter_memo(client, brand, creator)
    body = shipped(client, brand, memo_id)

    for user in (brand, creator):
        exported = export_service.build_export(
            db, db.get_one(Account, user.account_id), clock.now
        )["data"]["barter_shipments"]
        assert [(s["id"], s["tracking_number"]) for s in exported] == [
            (body["id"], NUMBER)
        ]

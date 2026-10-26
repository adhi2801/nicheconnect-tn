"""The barter_shipment table's rules, each broken with raw SQL (item 68, D-131)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.modules.deal_memo.test_memo_deliverables_model import (
    parents,  # noqa: F401 - fixture
)


def insert(db, memo_id, carrier: str, number: str, received: str = "NULL") -> None:
    db.execute(
        text(
            f"INSERT INTO barter_shipment (deal_memo_id, carrier, tracking_number, shipped_at, received_at) VALUES (:m, {carrier}, {number}, now(), {received})"  # noqa: S608 - fixed SQL from the parameters below
        ),
        {"m": memo_id},
    )


@pytest.mark.parametrize(
    ("carrier", "number", "received", "rule"),
    [
        ("'pigeon'", "'ABCD12345678'", "NULL", "ck_barter_shipment_carrier_allowed"),
        (
            "'delhivery'",
            "'abcd12345678'",
            "NULL",
            "ck_barter_shipment_tracking_number_shape",
        ),
        ("'delhivery'", "'AB12'", "NULL", "ck_barter_shipment_tracking_number_shape"),
        (
            "'india_post'",
            "'1234567890123'",
            "NULL",
            "ck_barter_shipment_india_post_number_shape",
        ),
        (
            "'delhivery'",
            "'ABCD12345678'",
            "now() - interval '1 day'",
            "ck_barter_shipment_received_after_shipped",
        ),
    ],
)
def test_the_database_refuses_a_bad_shipment(
    db,
    parents,  # noqa: F811
    carrier,
    number,
    received,
    rule,
):
    with pytest.raises(IntegrityError, match=rule):
        insert(db, parents["memo_deliverable"], carrier, number, received)


def test_a_deal_has_one_shipment(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"], "'delhivery'", "'ABCD12345678'")

    with pytest.raises(IntegrityError, match="uq_barter_shipment_deal_memo_id"):
        insert(db, parents["memo_deliverable"], "'dtdc'", "'ZZZZ12345678'")


def test_a_deal_with_a_shipment_cannot_be_deleted(db, parents):  # noqa: F811
    insert(db, parents["memo_deliverable"], "'delhivery'", "'ABCD12345678'")

    with pytest.raises(IntegrityError, match="fk_barter_shipment_deal_memo_id_deal_memo"):
        db.execute(
            text("DELETE FROM deal_memo WHERE id = :m"),
            {"m": parents["memo_deliverable"]},
        )

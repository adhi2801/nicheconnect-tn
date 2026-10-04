"""My payments: every payment across my deals, and the totals (D-075).

One brand with three creators, one deal each, at three points of the
payment: still to pay, marked as sent, and confirmed. Each side sees only
its own, every view holds exactly one, and the totals add up.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import engine
from app.modules.auth.tokens import create_access_token
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import create_account
from tests.modules.disputes.test_dispute_api import REASON

URL = "/api/v1/payments/mine"
TOTALS_URL = "/api/v1/payments/mine/totals"
RRN = "412345678901"
FEE = 800_000


def approved_deal(client: TestClient, brand: User, creator: User) -> str:
    """An accepted memo whose work is approved, so its payment is open."""
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


def mark_paid(client: TestClient, brand: User, memo_id: str) -> None:
    response = client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": RRN},
        headers=brand.headers,
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def book(client: TestClient, db, clock):
    """One brand, three creators: to pay, awaiting confirmation, finished."""
    brand = brand_user(db, clock)
    unpaid, sent, settled = (creator_user(db, clock) for _ in range(3))
    memos = {}
    for name, creator in (("to_pay", unpaid), ("awaiting", sent), ("finished", settled)):
        memos[name] = approved_deal(client, brand, creator)
        clock.advance(timedelta(minutes=1))  # a clear newest-first order
    mark_paid(client, brand, memos["awaiting"])
    mark_paid(client, brand, memos["finished"])
    confirmed = client.post(
        f"{MEMOS_URL}/{memos['finished']}/payment/confirm", headers=settled.headers
    )
    assert confirmed.status_code == 200, confirmed.text
    return {
        "brand": brand,
        "creators": {"to_pay": unpaid, "awaiting": sent, "finished": settled},
        "memos": memos,
        "clock": clock,
    }


def items(client: TestClient, user: User, **params: object) -> list[dict]:
    response = client.get(URL, params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- what each side sees -----------------------------------------------------------------


def test_a_brand_sees_every_payment_it_owes_or_made_newest_first(client, book):
    found = items(client, book["brand"])

    memos = book["memos"]
    assert [row["deal_memo_id"] for row in found] == [
        memos["finished"],
        memos["awaiting"],
        memos["to_pay"],
    ]
    assert [row["state"] for row in found] == ["confirmed", "paid", "due"]


def test_each_row_carries_its_deal_so_no_second_call_is_needed(client, book):
    row = items(client, book["brand"], view="to_pay")[0]

    assert row["campaign_title"] == "Pongal sweets launch"
    assert row["creator_handle"].startswith("proof")
    assert row["creator_display_name"]
    assert row["brand_name"]
    assert row["amount_paise"] == FEE
    assert row["has_open_dispute"] is False


def test_a_creator_sees_only_the_payment_owed_to_them(client, book):
    found = items(client, book["creators"]["awaiting"])

    assert [row["deal_memo_id"] for row in found] == [book["memos"]["awaiting"]]


def test_nobody_else_sees_any_of_them(client, db, book):
    stranger_brand = brand_user(db, book["clock"])
    stranger_creator = creator_user(db, book["clock"])

    assert items(client, stranger_brand) == []
    assert items(client, stranger_creator) == []


@pytest.mark.parametrize(
    ("view", "memo"),
    [
        ("to_pay", "to_pay"),
        ("awaiting_confirmation", "awaiting"),
        ("finished", "finished"),
    ],
)
def test_each_view_holds_exactly_its_own_payments(client, book, view, memo):
    found = items(client, book["brand"], view=view)

    assert [row["deal_memo_id"] for row in found] == [book["memos"][memo]]


def test_a_disputed_payment_says_so(client, book):
    raised = client.post(
        f"{MEMOS_URL}/{book['memos']['awaiting']}/payment/dispute",
        json={"reason": REASON},
        headers=book["creators"]["awaiting"].headers,
    )
    assert raised.status_code == 201, raised.text

    found = {row["deal_memo_id"]: row for row in items(client, book["brand"])}
    assert found[book["memos"]["awaiting"]]["has_open_dispute"] is True
    assert found[book["memos"]["to_pay"]]["has_open_dispute"] is False


def test_a_late_payment_reads_late_in_the_list(client, book):
    book["clock"].advance(timedelta(days=10))

    row = items(client, book["brand"], view="to_pay")[0]
    assert row["state"] == "late"
    assert row["days_overdue"] > 0


# --- pages -------------------------------------------------------------------------------


def test_pages_follow_one_another_without_gaps_or_repeats(client, book):
    first = client.get(URL, params={"limit": 2}, headers=book["brand"].headers).json()
    second = client.get(
        URL,
        params={"limit": 2, "cursor": first["next_cursor"]},
        headers=book["brand"].headers,
    ).json()

    assert first["next_cursor"] is not None
    assert second["next_cursor"] is None
    seen = [row["id"] for row in first["items"] + second["items"]]
    assert len(seen) == len(set(seen)) == 3


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


def test_a_longer_list_costs_no_more_queries(client, db, book):
    """No query per row (CLAUDE.md section 7): one page of one payment and a
    page of three take the same number of round trips."""
    with count_queries() as one:
        items(client, book["creators"]["to_pay"])
    with count_queries() as three:
        items(client, book["brand"])

    assert len(three) == len(one)


# --- totals ------------------------------------------------------------------------------


def totals(client: TestClient, user: User) -> dict:
    response = client.get(TOTALS_URL, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_totals_add_up_across_every_deal(client, book):
    body = totals(client, book["brand"])

    assert body["to_pay"] == {"count": 1, "amount_paise": FEE, "currency": "INR"}
    assert body["awaiting_confirmation"]["count"] == 1
    assert body["finished"] == {"count": 1, "amount_paise": FEE, "currency": "INR"}


def test_overdue_is_always_returned_even_at_zero(client, book):
    assert totals(client, book["brand"])["overdue"] == {
        "count": 0,
        "amount_paise": 0,
        "currency": "INR",
    }


def test_overdue_counts_what_is_past_its_due_date(client, book):
    book["clock"].advance(timedelta(days=10))

    body = totals(client, book["brand"])
    assert body["overdue"]["count"] == 1
    assert body["overdue"]["amount_paise"] == FEE
    assert body["as_of"] == book["clock"].now.date().isoformat()


def test_a_creators_totals_cover_only_their_own(client, book):
    body = totals(client, book["creators"]["finished"])

    assert body["finished"]["count"] == 1
    assert body["to_pay"]["count"] == 0


def test_a_new_account_has_all_zero_totals(client, db, clock):
    body = totals(client, brand_user(db, clock))

    assert all(
        body[name]["count"] == 0
        for name in ("to_pay", "overdue", "awaiting_confirmation", "finished")
    )


# --- refusals ----------------------------------------------------------------------------


@pytest.mark.parametrize("url", [URL, TOTALS_URL])
def test_it_needs_a_login(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", [URL, TOTALS_URL])
def test_an_admin_has_no_payments_of_its_own(client, db, clock, url):
    admin = create_account(db, "admin")
    token, _ = create_access_token(admin.id, "admin", clock.now)

    response = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["code"] == "not_a_payment_party"


@pytest.mark.parametrize("url", [URL, TOTALS_URL])
def test_a_brand_without_a_profile_is_told_to_create_one(client, db, clock, url):
    account = create_account(db, "brand")
    token, _ = create_access_token(account.id, "brand", clock.now)

    response = client.get(url, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 409


@pytest.mark.parametrize(
    "params", [{"view": "everything"}, {"limit": 0}, {"limit": 101}, {"cursor": "nope"}]
)
def test_a_bad_query_is_refused(client, book, params):
    response = client.get(URL, params=params, headers=book["brand"].headers)

    assert response.status_code == 422

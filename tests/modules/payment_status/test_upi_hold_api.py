"""A new UPI ID waits 24 hours before brands see it (item 82, D-107).

A code stops a stolen session from setting one; it does not stop a SIM
swap, since the code goes to whoever has the number. So a new ID waits,
brands keep seeing the one before, and the creator is told and can cancel
it without a code. These tests are about that wait and that code; the UPI
ID's own rules are in test_upi_api.py.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.clock import india_date
from app.core.config import settings
from app.modules.auth.models.creator import Creator
from app.modules.notifications.models import Notification
from app.modules.payment_status.upi_change_models import UPI_CHANGE_HOLD, CreatorUpiChange
from app.modules.payment_status.upi_models import CreatorUpi
from tests.deal_flow import (
    LINK,
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
)
from tests.factories import FIXED_NOW
from tests.step_up import ask_for_code, with_code

URL = "/api/v1/creators/me/upi"
WAITING_URL = "/api/v1/creators/me/upi/waiting"
ATTENTION_URL = "/api/v1/me/attention"
NOTICE = "upi-2026-10"
FIRST = "meena.cooks@okhdfcbank"
SECOND = "meena.new@okaxis"
THIEF = "quick.cash@ybl"


@pytest.fixture(autouse=True)
def notice_ready(monkeypatch):
    monkeypatch.setattr(settings, "upi_notice_version", NOTICE)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def body(upi_id: str, notice: str = NOTICE) -> dict[str, object]:
    return {"upi_id": upi_id, "consent": True, "notice_version": notice}


def give(client, user: User, upi_id: str):
    headers = with_code(client, user.headers, "set_upi_id", upi_id=upi_id)
    return client.put(URL, json=body(upi_id), headers=headers)


def mine(client, user: User) -> dict:
    return client.get(URL, headers=user.headers).json()


def approved_deal(client, brand: User, creator: User) -> str:
    memo_id = accepted_memo(client, brand, creator)
    proof_id = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof_id}/approve", headers=brand.headers)
    return memo_id


def brand_sees(client, brand: User, memo_id: str) -> str | None:
    response = client.get(
        f"{MEMOS_URL}/{memo_id}/payment/pay-details", headers=brand.headers
    )
    assert response.status_code == 200, response.text
    return response.json()["upi_id"]


def stamp(moment) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def told(db, user: User, kind: str) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


def creator_id_of(db, user: User):
    return db.scalar(select(Creator.id).where(Creator.account_id == user.account_id))


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- the code -----------------------------------------------------------------------------


def test_setting_one_without_a_code_is_refused(client, db, creator):
    response = client.put(URL, json=body(FIRST), headers=creator.headers)

    assert_problem(response, 401, "step_up_required")
    assert "insufficient_user_authentication" in response.headers["www-authenticate"]
    assert mine(client, creator)["waiting"] is None


def test_a_code_for_one_upi_id_cannot_set_another(client, creator):
    """The thief who tricks someone into sharing a code meant for their own ID."""
    headers = with_code(client, creator.headers, "set_upi_id", upi_id=FIRST)

    response = client.put(URL, json=body(THIEF), headers=headers)

    assert_problem(response, 400, "step_up_code_invalid")
    assert mine(client, creator)["waiting"] is None


def test_the_code_is_bound_to_the_stored_spelling(client, creator):
    """Asked for in capitals, used in capitals: both become one spelling."""
    code = ask_for_code(client, creator.headers, "set_upi_id", upi_id=FIRST.upper())

    response = client.put(
        URL,
        json=body(FIRST.upper()),
        headers={**creator.headers, "Step-Up-Code": code},
    )

    assert response.status_code == 200, response.text
    assert response.json()["waiting"]["upi_id"] == FIRST


def test_a_stale_notice_does_not_spend_the_code(client, creator):
    """Read the new notice and try again: the same code still works."""
    headers = with_code(client, creator.headers, "set_upi_id", upi_id=FIRST)

    assert_problem(
        client.put(URL, json=body(FIRST, "upi-2026-01"), headers=headers),
        409,
        "upi_notice_changed",
    )
    assert client.put(URL, json=body(FIRST), headers=headers).status_code == 200


def test_a_code_sets_one_id_once(client, creator):
    headers = with_code(client, creator.headers, "set_upi_id", upi_id=FIRST)
    assert client.put(URL, json=body(FIRST), headers=headers).status_code == 200

    assert_problem(
        client.put(URL, json=body(FIRST), headers=headers), 400, "step_up_code_invalid"
    )


# --- the wait -----------------------------------------------------------------------------


def test_a_first_id_waits_and_brands_see_none_meanwhile(client, clock, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    set_at = clock.now

    waiting = give(client, creator, FIRST).json()["waiting"]

    assert waiting["usable_at"] == stamp(set_at + UPI_CHANGE_HOLD)
    assert brand_sees(client, brand, memo_id) is None
    assert mine(client, creator)["upi_id"] is None


def test_a_new_id_waits_while_brands_still_see_the_one_before(
    client, clock, brand, creator
):
    memo_id = approved_deal(client, brand, creator)
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)

    give(client, creator, THIEF)

    assert brand_sees(client, brand, memo_id) == FIRST
    read = mine(client, creator)
    assert read["upi_id"] == FIRST
    assert read["waiting"]["upi_id"] == THIEF


def test_the_wait_ends_exactly_at_its_time(client, clock, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    give(client, creator, FIRST)

    clock.advance(UPI_CHANGE_HOLD - timedelta(seconds=1))
    assert brand_sees(client, brand, memo_id) is None

    clock.advance(timedelta(seconds=1))
    assert brand_sees(client, brand, memo_id) == FIRST
    assert mine(client, creator)["waiting"] is None


def test_once_in_effect_brands_are_warned_it_is_new(client, clock, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)

    details = client.get(
        f"{MEMOS_URL}/{memo_id}/payment/pay-details", headers=brand.headers
    ).json()

    assert details["upi_id_set_at"] == stamp(clock.now)
    assert details["upi_id_changed_recently"] is True


def test_a_second_change_replaces_the_first_and_starts_again(client, clock, creator):
    give(client, creator, FIRST)
    clock.advance(timedelta(hours=20))

    waiting = give(client, creator, SECOND).json()["waiting"]

    assert waiting["upi_id"] == SECOND
    assert waiting["usable_at"] == stamp(clock.now + UPI_CHANGE_HOLD)
    clock.advance(timedelta(hours=5))
    assert mine(client, creator)["upi_id"] is None  # the first never took effect


def test_setting_the_id_in_effect_renews_consent_at_once(client, db, clock, creator):
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD + timedelta(days=2))

    read = give(client, creator, FIRST).json()

    assert read["upi_id"] == FIRST
    assert read["consented_at"] == stamp(clock.now)
    assert read["waiting"] is None
    assert len(told(db, creator, "upi_change_pending")) == 1  # only the first


def test_setting_the_id_in_effect_drops_one_waiting(client, clock, creator):
    """The creator saying "my ID is this one" leaves nothing else waiting."""
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)
    give(client, creator, THIEF)

    read = give(client, creator, FIRST).json()

    assert read["upi_id"] == FIRST
    assert read["waiting"] is None


def test_a_change_whose_wait_is_over_is_written_into_the_current_row(
    client, db, clock, creator
):
    give(client, creator, FIRST)
    usable_at = clock.now + UPI_CHANGE_HOLD
    clock.advance(timedelta(days=3))

    give(client, creator, SECOND)

    current = db.scalars(
        select(CreatorUpi)
        .where(CreatorUpi.creator_id == creator_id_of(db, creator))
        .execution_options(populate_existing=True)
    ).one()
    assert current.upi_id == FIRST
    assert current.updated_at == usable_at  # when brands began to see it
    change = db.scalars(
        select(CreatorUpiChange)
        .where(CreatorUpiChange.creator_id == creator_id_of(db, creator))
        .execution_options(populate_existing=True)
    ).one()
    assert change.upi_id == SECOND


# --- telling the creator, and cancelling --------------------------------------------------


def test_the_creator_is_told_of_a_waiting_change(client, db, clock, creator):
    give(client, creator, FIRST)

    [notification] = told(db, creator, "upi_change_pending")
    assert notification.details == {
        "usable_at": (clock.now + UPI_CHANGE_HOLD).isoformat()
    }
    assert FIRST not in str(notification.details)


def test_a_waiting_change_is_on_the_attention_list_until_it_takes_effect(
    client, clock, creator
):
    give(client, creator, FIRST)
    usable_at = clock.now + UPI_CHANGE_HOLD

    [item] = [
        item
        for item in client.get(ATTENTION_URL, headers=creator.headers).json()["items"]
        if item["kind"] == "upi_change_pending"
    ]
    assert item["due_on"] == india_date(usable_at).isoformat()

    clock.advance(UPI_CHANGE_HOLD)
    after = client.get(ATTENTION_URL, headers=creator.headers).json()
    assert after["counts"]["upi_change_pending"] == 0


def test_cancelling_keeps_what_brands_see(client, db, clock, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)
    give(client, creator, THIEF)

    response = client.delete(WAITING_URL, headers=creator.headers)

    assert response.status_code == 204
    assert mine(client, creator)["waiting"] is None
    clock.advance(UPI_CHANGE_HOLD)
    assert brand_sees(client, brand, memo_id) == FIRST
    assert len(told(db, creator, "upi_change_cancelled")) == 1


def test_cancelling_needs_no_code(client, db, creator):
    """The owner whose number someone else holds can still stop it."""
    give(client, creator, THIEF)

    assert client.delete(WAITING_URL, headers=creator.headers).status_code == 204


def test_cancelling_nothing_is_fine_and_says_nothing(client, db, creator):
    assert client.delete(WAITING_URL, headers=creator.headers).status_code == 204
    assert client.delete(WAITING_URL, headers=creator.headers).status_code == 204
    assert told(db, creator, "upi_change_cancelled") == []


def test_a_change_already_in_effect_cannot_be_cancelled(client, clock, creator):
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)

    assert_problem(
        client.delete(WAITING_URL, headers=creator.headers),
        409,
        "upi_change_already_in_effect",
    )
    assert mine(client, creator)["upi_id"] == FIRST


def test_withdrawing_removes_a_waiting_id_too(client, db, clock, creator):
    give(client, creator, FIRST)
    clock.advance(UPI_CHANGE_HOLD)
    give(client, creator, SECOND)

    assert client.delete(URL, headers=creator.headers).status_code == 204

    assert mine(client, creator) == {
        "upi_id": None,
        "consented_at": None,
        "notice_version": None,
        "updated_at": None,
        "waiting": None,
    }
    clock.advance(UPI_CHANGE_HOLD)
    assert mine(client, creator)["upi_id"] is None


def test_only_a_creator_cancels(client, brand):
    assert client.delete(WAITING_URL, headers=brand.headers).status_code == 403
    assert client.delete(WAITING_URL).status_code == 401


def test_one_creators_cancel_never_touches_anothers(client, db, clock, creator):
    someone = creator_user(db, clock)
    give(client, someone, FIRST)

    client.delete(WAITING_URL, headers=creator.headers)

    assert mine(client, someone)["waiting"]["upi_id"] == FIRST


# --- the database's own rules -------------------------------------------------------------


def _insert(
    db,
    creator_id,
    upi_id: str = FIRST,
    *,
    notice: str = NOTICE,
    waits: timedelta = UPI_CHANGE_HOLD,
) -> None:
    db.execute(
        text(
            "INSERT INTO creator_upi_change "
            "(creator_id, upi_id, consented_at, notice_version, usable_at) "
            "VALUES (:creator_id, :upi_id, :at, :notice, :usable_at)"
        ),
        {
            "creator_id": creator_id,
            "upi_id": upi_id,
            "at": FIXED_NOW,
            "notice": notice,
            "usable_at": FIXED_NOW + waits,
        },
    )


@pytest.mark.parametrize(
    ("upi_id", "overrides", "constraint"),
    [
        ("9876543210@ybl", {}, "upi_id_not_a_phone_number"),
        ("Meena@okaxis", {}, "upi_id_format"),
        (FIRST, {"notice": "  "}, "notice_version_not_blank"),
        (FIRST, {"waits": timedelta(hours=1)}, "usable_a_day_after_consent"),
        (FIRST, {"waits": timedelta(0)}, "usable_a_day_after_consent"),
    ],
)
def test_the_database_refuses_a_bad_waiting_id(
    db, creator, upi_id, overrides, constraint
):
    with pytest.raises(IntegrityError, match=f"ck_creator_upi_change_{constraint}"):
        _insert(db, creator_id_of(db, creator), upi_id, **overrides)


def test_the_database_keeps_one_waiting_id_per_creator(db, creator):
    _insert(db, creator_id_of(db, creator))

    with pytest.raises(IntegrityError, match="uq_creator_upi_change_creator_id"):
        _insert(db, creator_id_of(db, creator), SECOND)

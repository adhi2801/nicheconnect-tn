"""The UPI pay link (D-085): the creator's UPI ID, given with consent, and
the brand paying it from its own UPI app.

The rules that matter: nobody can add one until the notice exists; consent
is explicit and versioned; a phone-number UPI ID is refused; withdrawing is
always possible; only the brand on the deal sees the ID, and only while the
payment is open; no link above UPI's limit; and nothing here ever moves
money.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.modules.auth.models.creator import Creator
from app.modules.payment_status import upi_service
from app.modules.payment_status.upi_router import PAY_DETAILS_LIMIT, WRITE_LIMIT
from tests.deal_flow import LINK, MEMOS_URL, User, accepted_memo, brand_user, creator_user

URL = "/api/v1/creators/me/upi"
NOTICE = "upi-2026-10"
UPI_ID = "meena.cooks@okhdfcbank"


@pytest.fixture(autouse=True)
def notice_ready(monkeypatch):
    """The notice exists, as it will once the validation pack supplies it."""
    monkeypatch.setattr(settings, "upi_notice_version", NOTICE)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def give(client, user: User, upi_id: str = UPI_ID, **overrides: object):
    body: dict[str, object] = {
        "upi_id": upi_id,
        "consent": True,
        "notice_version": NOTICE,
    }
    body.update(overrides)
    return client.put(URL, json=body, headers=user.headers)


def approved_deal(client, brand: User, creator: User, **memo_fields: object) -> str:
    """A deal whose work is approved, so its payment record is open."""
    memo_id = accepted_memo(client, brand, creator, **memo_fields)
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


def pay_details(client, user: User, memo_id: str):
    return client.get(f"{MEMOS_URL}/{memo_id}/payment/pay-details", headers=user.headers)


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- the creator's own UPI ID -------------------------------------------------------------


def test_nobody_can_add_one_until_the_notice_exists(client, creator, monkeypatch):
    monkeypatch.setattr(settings, "upi_notice_version", None)

    assert_problem(give(client, creator), 503, "upi_not_open_yet")


def test_a_creator_gives_their_upi_id_with_consent(client, creator, clock):
    response = give(client, creator, "Meena.Cooks@OKHDFCBANK")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upi_id"] == UPI_ID  # stored in one spelling
    assert body["notice_version"] == NOTICE
    assert body["consented_at"] == clock.now.isoformat().replace("+00:00", "Z")
    assert client.get(URL, headers=creator.headers).json()["upi_id"] == UPI_ID


def test_none_given_reads_as_nothing(client, creator):
    assert client.get(URL, headers=creator.headers).json() == {
        "upi_id": None,
        "consented_at": None,
        "notice_version": None,
        "updated_at": None,
    }


@pytest.mark.parametrize(
    "overrides",
    [{"consent": False}, {"consent": None}, {"notice_version": ""}, {"note": "hi"}],
    ids=["consent refused", "consent missing", "no notice version", "unknown field"],
)
def test_consent_is_explicit(client, creator, overrides):
    body = {"upi_id": UPI_ID, "consent": True, "notice_version": NOTICE, **overrides}
    body = {key: value for key, value in body.items() if value is not None}

    response = client.put(URL, json=body, headers=creator.headers)

    assert response.status_code == 422


def test_consent_to_an_old_notice_is_sent_back(client, creator):
    assert_problem(
        give(client, creator, notice_version="upi-2026-01"), 409, "upi_notice_changed"
    )


@pytest.mark.parametrize(
    "upi_id",
    [
        "meena",
        "meena@",
        "@okaxis",
        "m@okaxis",
        "meena cooks@okaxis",
        "meena@1bank",
        "a@b@c",
    ],
)
def test_a_upi_id_that_is_not_one_is_refused(client, creator, upi_id):
    assert give(client, creator, upi_id).status_code == 422


@pytest.mark.parametrize(
    "upi_id", ["9876543210@ybl", "919876543210@paytm", "6000000000@okaxis"]
)
def test_a_phone_number_upi_id_is_refused_and_says_why(client, creator, upi_id):
    response = give(client, creator, upi_id)

    assert response.status_code == 422
    assert "phone number" in response.json()["errors"][0]["message"]


@pytest.mark.parametrize("upi_id", ["98765@ybl", "meena9876543210@ybl", "5876543210@ybl"])
def test_a_upi_id_with_digits_that_is_not_a_phone_number_is_fine(client, creator, upi_id):
    assert give(client, creator, upi_id).status_code == 200


def test_changing_it_gives_consent_again(client, creator, clock):
    give(client, creator)
    clock.advance(timedelta(days=3))

    body = give(client, creator, "meena.new@okaxis").json()

    assert body["upi_id"] == "meena.new@okaxis"
    assert body["consented_at"] == clock.now.isoformat().replace("+00:00", "Z")


def test_withdrawing_deletes_it(client, creator):
    give(client, creator)

    removed = client.delete(URL, headers=creator.headers)

    assert removed.status_code == 204
    assert client.get(URL, headers=creator.headers).json()["upi_id"] is None


def test_withdrawing_works_even_while_adding_is_closed(client, creator, monkeypatch):
    give(client, creator)
    monkeypatch.setattr(settings, "upi_notice_version", None)

    assert client.delete(URL, headers=creator.headers).status_code == 204
    assert client.delete(URL, headers=creator.headers).status_code == 204  # repeatable


def test_a_brand_has_no_upi_id(client, brand):
    assert client.get(URL, headers=brand.headers).status_code == 403
    assert give(client, brand).status_code == 403


def test_without_a_login_it_is_refused(client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={}).status_code == 401
    assert client.delete(URL).status_code == 401


def test_giving_it_is_rate_limited(client, creator):
    allowed = int(WRITE_LIMIT.split()[0])

    answers = [give(client, creator).status_code for _ in range(allowed + 1)]

    assert answers[:allowed] == [200] * allowed
    assert answers[allowed] == 429


def test_it_is_in_the_creators_export_and_not_the_brands(client, creator, brand):
    give(client, creator)

    creator_data = client.get("/api/v1/me/export", headers=creator.headers).json()["data"]
    brand_data = client.get("/api/v1/me/export", headers=brand.headers).json()["data"]

    [row] = creator_data["upi_id"]
    assert row["upi_id"] == UPI_ID
    assert row["notice_version"] == NOTICE
    assert "upi_id" not in brand_data


# --- the brand paying --------------------------------------------------------------------


def test_the_brand_gets_a_pay_link_for_the_open_payment(client, db, brand, creator):
    give(client, creator)
    memo_id = approved_deal(client, brand, creator)
    name = db.scalar(
        select(Creator.display_name).where(Creator.account_id == creator.account_id)
    )

    response = pay_details(client, brand, memo_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["upi_id"] == UPI_ID
    assert body["amount_paise"] == 800_000
    assert body["currency"] == "INR"
    assert body["unavailable_reason"] is None
    assert body["pay_link"] == upi_service.pay_link(
        UPI_ID, name, 800_000, "Pongal sweets launch"
    )
    assert body["pay_link"].startswith("upi://pay?pa=meena.cooks%40okhdfcbank&pn=")
    assert "&am=8000.00&cu=INR&tn=Pongal%20sweets%20launch" in body["pay_link"]


def test_a_fresh_upi_id_is_flagged_to_the_brand(client, clock, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    give(client, creator)

    assert pay_details(client, brand, memo_id).json()["upi_id_changed_recently"] is True

    clock.advance(timedelta(hours=25))
    assert pay_details(client, brand, memo_id).json()["upi_id_changed_recently"] is False


def test_without_a_upi_id_the_brand_is_told_to_pay_another_way(client, brand, creator):
    memo_id = approved_deal(client, brand, creator)

    body = pay_details(client, brand, memo_id).json()

    assert body["pay_link"] is None
    assert body["upi_id"] is None
    assert body["unavailable_reason"] == "no_upi_id"


def test_above_upis_limit_there_is_no_link(client, brand, creator):
    give(client, creator)
    memo_id = approved_deal(client, brand, creator, fee_amount_paise=1_00_001 * 100)

    body = pay_details(client, brand, memo_id).json()

    assert body["pay_link"] is None
    assert body["unavailable_reason"] == "above_upi_limit"


def test_exactly_at_the_limit_there_is_a_link(client, brand, creator):
    give(client, creator)
    memo_id = approved_deal(client, brand, creator, fee_amount_paise=1_00_000 * 100)

    body = pay_details(client, brand, memo_id).json()

    assert body["unavailable_reason"] is None
    assert "&am=100000.00&" in body["pay_link"]


def test_once_marked_paid_the_upi_id_is_not_shown_again(client, brand, creator):
    give(client, creator)
    memo_id = approved_deal(client, brand, creator)
    client.post(
        f"{MEMOS_URL}/{memo_id}/payment/mark-paid",
        json={"method": "upi", "reference": "412345678901"},
        headers=brand.headers,
    )

    assert_problem(
        pay_details(client, brand, memo_id), 409, "payment_already_marked_paid"
    )


def test_before_the_work_is_approved_there_is_nothing_to_pay(client, brand, creator):
    give(client, creator)
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(pay_details(client, brand, memo_id), 404, "payment_record_not_found")


def test_the_creator_does_not_read_pay_details(client, brand, creator):
    memo_id = approved_deal(client, brand, creator)

    assert pay_details(client, creator, memo_id).status_code == 403


def test_another_brand_cannot_see_the_upi_id(client, db, clock, brand, creator):
    give(client, creator)
    memo_id = approved_deal(client, brand, creator)

    assert_problem(
        pay_details(client, brand_user(db, clock), memo_id), 404, "memo_not_found"
    )


def test_pay_details_need_a_login(client, brand, creator):
    memo_id = approved_deal(client, brand, creator)

    assert client.get(f"{MEMOS_URL}/{memo_id}/payment/pay-details").status_code == 401


def test_pay_details_are_rate_limited_harder_than_other_reads(client, brand, creator):
    memo_id = approved_deal(client, brand, creator)
    allowed = int(PAY_DETAILS_LIMIT.split()[0])

    answers = [
        pay_details(client, brand, memo_id).status_code for _ in range(allowed + 1)
    ]

    assert allowed < 60
    assert answers[:allowed] == [200] * allowed
    assert answers[allowed] == 429


# --- the link itself ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paise", "amount"),
    [(800_000, "8000.00"), (5, "0.05"), (1_00_000_00, "100000.00"), (12_345, "123.45")],
)
def test_the_amount_is_rupees_with_two_decimals(paise, amount):
    assert f"&am={amount}&" in upi_service.pay_link(UPI_ID, "Meena", paise, "x")


def test_every_value_is_percent_encoded():
    link = upi_service.pay_link("a.b@okaxis", "Meena & Co", 100, "Diwali: 2 reels/day")

    assert "pn=Meena%20%26%20Co" in link
    assert "tn=Diwali%3A%202%20reels%2Fday" in link
    assert " " not in link


def test_only_person_to_person_fields_are_sent():
    link = upi_service.pay_link(UPI_ID, "Meena", 100, "x")
    keys = [part.split("=")[0] for part in link.removeprefix("upi://pay?").split("&")]

    assert keys == ["pa", "pn", "am", "cu", "tn"]


def test_the_note_is_kept_short():
    link = upi_service.pay_link(UPI_ID, "Meena", 100, "x" * 80)

    assert link.endswith("tn=" + "x" * upi_service.NOTE_MAX_LENGTH)


# --- the database's own rules -------------------------------------------------------------


def _insert(db, creator_id, upi_id: str, notice: str = NOTICE) -> None:
    db.execute(
        text(
            "INSERT INTO creator_upi (creator_id, upi_id, consented_at, notice_version) "
            "VALUES (:creator_id, :upi_id, now(), :notice)"
        ),
        {"creator_id": creator_id, "upi_id": upi_id, "notice": notice},
    )


def _creator_id(db, user: User):
    return db.scalar(select(Creator.id).where(Creator.account_id == user.account_id))


@pytest.mark.parametrize(
    ("upi_id", "notice", "constraint"),
    [
        ("9876543210@ybl", NOTICE, "upi_id_not_a_phone_number"),
        ("Meena@okaxis", NOTICE, "upi_id_format"),
        ("meena", NOTICE, "upi_id_format"),
        (UPI_ID, "  ", "notice_version_not_blank"),
    ],
)
def test_the_database_refuses_a_bad_row(db, creator, upi_id, notice, constraint):
    with pytest.raises(IntegrityError, match=f"ck_creator_upi_{constraint}"):
        _insert(db, _creator_id(db, creator), upi_id, notice)


def test_the_database_keeps_one_per_creator(db, creator):
    _insert(db, _creator_id(db, creator), UPI_ID)

    with pytest.raises(IntegrityError, match="uq_creator_upi_creator_id"):
        _insert(db, _creator_id(db, creator), "meena.two@okaxis")

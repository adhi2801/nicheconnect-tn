"""Direct offers through the API (D-189): sending, the creator's list, the link.

Accepting is in test_direct_offer_accept_api.py, the hidden campaign and
application in test_direct_offer_hidden_api.py, races in
test_direct_offer_concurrency.py.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.main import app
from app.modules.auth.models.account import Account
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.deal_memo import direct_offer_notices as notices
from app.modules.deal_memo.direct_offer_models import DirectOffer
from app.modules.deal_memo.direct_offer_rules import hash_link_token, is_link_token
from tests.deal_flow import brand_user, creator_user
from tests.direct_offers import (
    ACCEPT_URL,
    CODE_URL,
    FEE,
    LINK_URL,
    OFFERS_URL,
    STOP_URL,
    TEST_WORDING,
    accept_body,
    link,
    offer_body,
    phone_of,
    send,
    sent,
    switch_on,
)
from tests.factories import fake_phone
from tests.query_counts import queries_for


@pytest.fixture
def on(monkeypatch) -> None:
    switch_on(monkeypatch)


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


def row(db, offer_id) -> DirectOffer:
    return db.scalars(
        select(DirectOffer)
        .where(DirectOffer.id == offer_id)
        .execution_options(populate_existing=True)
    ).one()


# --- the switch, and the wording it guards -------------------------------------


def test_every_route_is_off_by_default(client, db, clock, monkeypatch):
    """The creator's routes, and a link that exists, say the feature is off.
    A link sent while it was on still serves nothing once it is off."""
    creator = creator_user(db, clock)
    switch_on(monkeypatch)
    offer = sent(client, creator)
    monkeypatch.setattr(settings, "direct_offers_enabled", False)
    held = link(offer["link_token"])
    answers = [
        client.post(OFFERS_URL, json=offer_body(), headers=creator.headers),
        client.get(OFFERS_URL, headers=creator.headers),
        client.get(f"{OFFERS_URL}/{offer['id']}", headers=creator.headers),
        client.post(f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers),
        client.get(LINK_URL, headers=held),
        client.post(STOP_URL, headers=held),
        client.post(CODE_URL, headers=held),
        client.post(
            ACCEPT_URL, json=accept_body("042917", offer["terms_sha256"]), headers=held
        ),
    ]

    assert [a.status_code for a in answers] == [503] * 8
    assert {a.json()["code"] for a in answers} == {"direct_offers_unavailable"}
    # Refused before anything is written: not ended, and not even opened.
    stored = row(db, offer["id"])
    assert (stored.status, stored.opened_at) == ("sent", None)


def test_while_off_a_link_that_opens_nothing_is_not_found(client, db, clock):
    """No offer can be sent while the feature is off, so a token that opens
    none is not found, as when it is on: a stranger's guess at a public route
    meets a 404, never a 5xx (the contract fuzzing, testing.md section 6)."""
    for token in ("a" * 64, "not-a-token"):
        held = link(token)
        answers = [
            client.get(LINK_URL, headers=held),
            client.post(STOP_URL, headers=held),
            client.post(CODE_URL, headers=held),
            client.post(ACCEPT_URL, json=accept_body("042917", "0" * 64), headers=held),
        ]

        assert [a.status_code for a in answers] == [404] * 4, token
        assert {a.json()["code"] for a in answers} == {"direct_offer_not_found"}


def test_the_switch_alone_serves_nothing_while_the_wording_is_a_placeholder(
    client, db, clock, monkeypatch
):
    monkeypatch.setattr(settings, "direct_offers_enabled", True)
    creator = creator_user(db, clock)

    response = send(client, creator)

    assert response.status_code == 503
    assert notices.PLACEHOLDER_MARK not in response.text


def test_the_placeholders_are_marked_and_never_ready():
    assert notices.PLACEHOLDER_MARK in notices.LINK_PAGE_NOTICE
    assert notices.PLACEHOLDER_MARK in notices.CODE_MESSAGE
    assert not notices.wording_ready()


def test_the_app_refuses_to_start_switched_on_with_placeholder_wording():
    with pytest.raises(RuntimeError, match="placeholders"):
        notices.refuse_switch_without_wording(True)
    notices.refuse_switch_without_wording(False)


def test_real_wording_and_the_switch_turn_it_on(client, db, clock, on):
    assert notices.wording_ready()
    assert send(client, creator_user(db, clock)).status_code == 201


def test_the_features_list_says_whether_it_is_on(client, monkeypatch):
    assert client.get("/api/v1/features").json()["direct_offers"] == {
        "on": False,
        "share_percent": 100,
        "off_code": "direct_offers_unavailable",
    }
    switch_on(monkeypatch)
    assert client.get("/api/v1/features").json()["direct_offers"]["on"] is True


# --- sending --------------------------------------------------------------------


def test_a_creator_sends_an_offer_and_gets_its_link_once(client, db, clock, on):
    creator = creator_user(db, clock)
    phone = fake_phone()

    response = send(client, creator, phone)

    assert response.status_code == 201, response.text
    body = response.json()
    assert response.headers["location"] == f"{OFFERS_URL}/{body['id']}"
    assert response.headers["cache-control"] == "no-store"
    assert is_link_token(body["link_token"])
    assert body["status"] == "sent"
    assert body["brand_name"] == "Amma Sweets"
    assert body["fee_amount_paise"] == FEE
    assert body["deliverable_items"] == [
        {"platform": "instagram", "format": "reel", "quantity": 2, "note": None}
    ]
    assert body["expires_at"] == "2026-10-01T12:00:00Z"
    assert body["opened_at"] is None and body["deal_memo_id"] is None
    assert len(body["terms_sha256"]) == 64
    # The number is never answered; the token is kept only as its HMAC.
    assert phone not in response.text
    stored = row(db, body["id"])
    assert stored.token_hash == hash_link_token(body["link_token"])
    assert body["link_token"] not in stored.token_hash
    assert stored.recipient_phone == phone


def test_a_send_is_refused_with_a_bad_body(client, db, clock, on):
    creator = creator_user(db, clock)

    bad = [
        offer_body(brand_phone="12345"),
        offer_body(fee_amount_paise=0),
        offer_body(fee_amount_paise=10_000_000_001),
        offer_body(brand_name=""),
        offer_body(deliverables="x" * 2001),
        offer_body(approval_window_days=31),
        offer_body(extra_terms="x" * 2001),
        offer_body(deliverable_items=[{"platform": "instagram"}] * 11),
        {**offer_body(), "status": "accepted"},
    ]
    without_fee = offer_body()
    del without_fee["fee_amount_paise"]
    bad.append(without_fee)

    answers = [
        client.post(OFFERS_URL, json=body, headers=creator.headers).status_code
        for body in bad
    ]
    assert answers == [422] * len(bad)


def test_sending_needs_a_signed_in_creator(client, db, clock, on):
    assert client.post(OFFERS_URL, json=offer_body()).status_code == 401
    brand = brand_user(db, clock)
    assert (
        client.post(OFFERS_URL, json=offer_body(), headers=brand.headers).status_code
        == 403
    )


def test_a_due_date_must_be_from_today_to_a_year_ahead(client, db, clock, on):
    creator = creator_user(db, clock)

    passed = send(client, creator, content_due_on="2026-09-16")
    too_far = send(client, creator, content_due_on="2027-09-18")

    assert passed.status_code == 409
    assert passed.json()["code"] == "due_date_has_passed"
    assert too_far.status_code == 422
    assert too_far.json()["code"] == "due_date_too_far"
    assert too_far.json()["errors"][0]["field"] == "content_due_on"
    assert send(client, creator, content_due_on="2027-09-17").status_code == 201


def test_a_creator_cannot_send_an_offer_to_their_own_number(client, db, clock, on):
    creator = creator_user(db, clock)

    response = send(client, creator, phone_of(db, creator))

    assert response.status_code == 409
    assert response.json()["code"] == "direct_offer_own_number"


def test_a_creator_who_left_meanwhile_sends_nothing(db, clock, on):
    """A token is refused once its account is deleted, so only an erasure
    landing between the sign-in check and the creator's lock reaches this:
    the send reads the account again under that lock and starts nothing with
    someone who left (D-122)."""
    from app.modules.auth.models.creator import Creator
    from app.modules.deal_memo import direct_offer_service
    from app.modules.deal_memo.direct_offer_schemas import DirectOfferCreate
    from app.modules.deal_memo.exceptions import CreatorLeft

    creator = creator_user(db, clock)
    profile = db.scalars(
        select(Creator).where(Creator.account_id == creator.account_id)
    ).one()
    account = db.get_one(Account, creator.account_id)
    account.deletion_requested_at = clock.now - timedelta(days=30)
    account.deletion_takes_effect_at = clock.now
    account.phone = None
    account.deleted_at = clock.now
    # Committed to the test's savepoint, so the send's own rollback keeps it
    # and the last line asks a real question.
    db.commit()
    profile_id = profile.id
    fields = DirectOfferCreate.model_validate(offer_body()).model_dump()

    with pytest.raises(CreatorLeft):
        direct_offer_service.send(db, profile, fields, clock.now)

    assert (
        db.scalar(select(DirectOffer.id).where(DirectOffer.creator_id == profile_id))
        is None
    )


def test_ten_offers_a_tamil_nadu_day_then_none_until_midnight(
    client, db, clock, on, unlimited
):
    creator = creator_user(db, clock)
    for _ in range(10):
        assert send(client, creator).status_code == 201

    refused = send(client, creator)

    assert refused.status_code == 429
    assert refused.json()["code"] == "direct_offer_daily_limit"
    # 12:00 UTC is 17:30 in Tamil Nadu: six and a half hours to midnight.
    assert refused.headers["retry-after"] == str(6 * 3600 + 1800)
    clock.advance(timedelta(hours=6, minutes=30))
    assert send(client, creator).status_code == 201


def test_another_creator_s_offers_do_not_count_against_the_day(
    client, db, clock, on, unlimited
):
    first, second = creator_user(db, clock), creator_user(db, clock)
    for _ in range(10):
        assert send(client, first).status_code == 201

    assert send(client, second).status_code == 201


def test_one_number_receives_three_offers_a_week_from_anyone(
    client, db, clock, on, unlimited
):
    phone = fake_phone()
    for _ in range(3):
        assert send(client, creator_user(db, clock), phone).status_code == 201
    clock.advance(timedelta(days=1))

    refused = send(client, creator_user(db, clock), phone)

    assert refused.status_code == 429
    assert refused.json()["code"] == "direct_offer_number_limit"
    assert refused.headers["retry-after"] == str(6 * 86400)
    assert send(client, creator_user(db, clock)).status_code == 201
    clock.advance(timedelta(days=6))
    assert send(client, creator_user(db, clock), phone).status_code == 201


def test_sending_has_a_rate_limit(client, db, clock, on):
    creator = creator_user(db, clock)
    answers = [send(client, creator).status_code for _ in range(6)]

    assert answers[:5] == [201] * 5
    assert answers[5] == 429


# --- the creator's list ----------------------------------------------------------


def test_the_list_pages_newest_first_without_gaps_or_repeats(client, db, clock, on):
    creator = creator_user(db, clock)
    ids = []
    for _ in range(5):
        ids.append(sent(client, creator)["id"])
        clock.advance(timedelta(minutes=1))

    seen, cursor = [], None
    while True:
        params = {"limit": 2} | ({"cursor": cursor} if cursor else {})
        page = client.get(OFFERS_URL, params=params, headers=creator.headers).json()
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == list(reversed(ids))
    assert all("link_token" not in item for item in page["items"])


def test_the_list_shows_only_my_own_offers(client, db, clock, on):
    mine, theirs = creator_user(db, clock), creator_user(db, clock)
    own = sent(client, mine)["id"]
    sent(client, theirs)

    items = client.get(OFFERS_URL, headers=mine.headers).json()["items"]

    assert [item["id"] for item in items] == [own]


def test_a_long_page_costs_the_queries_a_short_one_does(client, db, clock, on, unlimited):
    creator = creator_user(db, clock)
    sent(client, creator)
    short = queries_for(client, OFFERS_URL, creator.headers)
    for _ in range(6):
        sent(client, creator)
    long = queries_for(client, OFFERS_URL, creator.headers)

    assert len(client.get(OFFERS_URL, headers=creator.headers).json()["items"]) == 7
    assert long == short


def test_the_list_needs_a_creator_and_a_valid_page(client, db, clock, on):
    creator = creator_user(db, clock)
    assert client.get(OFFERS_URL).status_code == 401
    assert (
        client.get(OFFERS_URL, headers=brand_user(db, clock).headers).status_code == 403
    )
    assert (
        client.get(OFFERS_URL, params={"limit": 0}, headers=creator.headers).status_code
        == 422
    )
    assert (
        client.get(
            OFFERS_URL, params={"cursor": "nonsense"}, headers=creator.headers
        ).status_code
        == 422
    )


def test_one_offer_is_read_by_its_creator_only(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    url = f"{OFFERS_URL}/{offer['id']}"

    mine = client.get(url, headers=creator.headers)
    stranger = client.get(url, headers=creator_user(db, clock).headers)

    assert mine.status_code == 200
    assert mine.json()["terms_sha256"] == offer["terms_sha256"]
    assert stranger.status_code == 404
    assert stranger.json()["code"] == "direct_offer_not_found"
    assert (
        client.get(
            f"{OFFERS_URL}/{offer['terms_sha256'][:8]}", headers=creator.headers
        ).status_code
        == 422
    )
    unknown = "0190a1b2-0000-7000-8000-000000000000"
    assert (
        client.get(f"{OFFERS_URL}/{unknown}", headers=creator.headers).status_code == 404
    )
    assert client.get(url).status_code == 401


# --- withdrawing ----------------------------------------------------------------


def test_withdrawing_ends_the_link_and_erases_the_number_and_name(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)

    response = client.post(
        f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"
    assert response.json()["brand_name"] is None
    assert response.json()["ended_at"] == "2026-09-17T12:00:00Z"
    stored = row(db, offer["id"])
    assert stored.recipient_phone is None and stored.brand_name is None
    gone = client.get(LINK_URL, headers=link(offer["link_token"]))
    assert gone.status_code == 409
    assert gone.json()["code"] == "direct_offer_withdrawn"


def test_an_offer_is_withdrawn_once_and_only_by_its_creator(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    url = f"{OFFERS_URL}/{offer['id']}/withdraw"

    assert client.post(url, headers=creator_user(db, clock).headers).status_code == 404
    assert client.post(url).status_code == 401
    assert client.post(url, headers=creator.headers).status_code == 200
    again = client.post(url, headers=creator.headers)
    assert again.status_code == 409
    assert again.json()["code"] == "direct_offer_withdrawn"


def test_an_expired_offer_cannot_be_withdrawn(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    clock.advance(timedelta(days=14))

    response = client.post(
        f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "direct_offer_expired"
    listed = client.get(f"{OFFERS_URL}/{offer['id']}", headers=creator.headers).json()
    assert listed["status"] == "expired" and listed["brand_name"] is None


# --- the link -------------------------------------------------------------------


def test_the_link_shows_the_creator_and_the_terms_and_nothing_else(client, db, clock, on):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)

    response = client.get(LINK_URL, headers=link(offer["link_token"]))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["creator"] == {
        "display_name": "Priya Eats",
        "handle": body["creator"]["handle"],
    }
    assert body["brand_name"] == "Amma Sweets"
    assert body["fee_amount_paise"] == FEE
    assert body["terms_sha256"] == offer["terms_sha256"]
    assert body["notice"] == TEST_WORDING
    assert response.headers["cache-control"] == "no-store"
    assert phone not in response.text
    assert "id" not in body and "deal_memo_id" not in body
    assert set(body) == {
        "creator",
        "brand_name",
        "expires_at",
        "notice",
        "deliverables",
        "deliverable_items",
        "fee_amount_paise",
        "currency",
        "cancellation_fee_paise",
        "approval_window_days",
        "payment_due_days",
        "usage_rights_days",
        "content_due_on",
        "disclosure_required",
        "draft_review",
        "extra_terms",
        "terms_sha256",
    }


def test_the_first_opening_is_shown_to_the_creator_once(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    clock.advance(timedelta(hours=2))
    assert client.get(LINK_URL, headers=link(offer["link_token"])).status_code == 200
    clock.advance(timedelta(hours=2))
    assert client.get(LINK_URL, headers=link(offer["link_token"])).status_code == 200

    listed = client.get(f"{OFFERS_URL}/{offer['id']}", headers=creator.headers).json()

    assert listed["opened_at"] == "2026-09-17T14:00:00Z"


def test_a_first_opening_noted_twice_keeps_the_earlier(client, db, clock, on):
    """Two first readings at once both find the offer unopened; the statement
    that notes it matches only an unopened offer, so the later never moves it."""
    from app.modules.deal_memo.direct_offer_service import note_first_opening

    offer = sent(client, creator_user(db, clock))
    first = clock.now + timedelta(minutes=1)

    note_first_opening(db, offer["id"], first)
    note_first_opening(db, offer["id"], first + timedelta(minutes=5))

    assert row(db, offer["id"]).opened_at == first


def test_a_later_reading_writes_nothing(client, db, clock, on):
    """Once opened, a reading of the link is the one query that finds it."""
    from tests.query_counts import count_queries

    offer = sent(client, creator_user(db, clock))
    token = link(offer["link_token"])
    assert client.get(LINK_URL, headers=token).status_code == 200

    with count_queries() as statements:
        assert client.get(LINK_URL, headers=token).status_code == 200

    touching = [sql for sql in statements if "direct_offer" in sql]
    assert len(touching) == 1, statements
    assert touching[0].lstrip().upper().startswith("SELECT"), touching


def test_a_link_nobody_sent_finds_nothing(client, db, clock, on):
    sent(client, creator_user(db, clock))
    for token in ("b" * 64, "short", "x" * 128):
        response = client.get(LINK_URL, headers=link(token))
        assert response.status_code == 404
        assert response.json()["code"] == "direct_offer_not_found"
    assert client.get(LINK_URL).status_code == 422
    assert client.get(LINK_URL, headers=link("x" * 129)).status_code == 422


def test_a_token_of_the_wrong_shape_never_reaches_the_offers(client, db, clock, on):
    """Each link route refuses a malformed token before asking the database
    anything about offers (security.md section 1)."""
    from tests.query_counts import count_queries

    for method, url in (("GET", LINK_URL), ("POST", STOP_URL)):
        with count_queries() as statements:
            response = client.request(method, url, headers=link("not-a-token"))
        assert response.status_code == 404
        assert not [sql for sql in statements if "direct_offer" in sql], statements


def test_an_expired_link_says_so(client, db, clock, on):
    offer = sent(client, creator_user(db, clock))
    clock.advance(timedelta(days=14) - timedelta(microseconds=1))
    assert client.get(LINK_URL, headers=link(offer["link_token"])).status_code == 200
    clock.advance(timedelta(microseconds=1))

    response = client.get(LINK_URL, headers=link(offer["link_token"]))

    assert response.status_code == 409
    assert response.json()["code"] == "direct_offer_expired"


def test_a_suspended_creator_s_link_finds_nothing(client, db, clock, on):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    account = db.get_one(Account, creator.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.flush()

    assert client.get(LINK_URL, headers=link(offer["link_token"])).status_code == 404


def test_the_link_has_a_rate_limit_by_address(client, db, clock, on):
    offer = sent(client, creator_user(db, clock))
    answers = [
        client.get(LINK_URL, headers=link(offer["link_token"])).status_code
        for _ in range(61)
    ]

    assert answers[:60] == [200] * 60
    assert answers[60] == 429


@pytest.mark.parametrize(
    ("route", "allowed"),
    [("list", 60), ("read", 60), ("withdraw", 30), ("stop", 10)],
)
def test_the_other_routes_have_their_rate_limits(client, db, clock, on, route, allowed):
    """The creator's list, one offer and withdrawing, per account; "stop
    these", per address. The answer before the limit may be a refusal (a
    second withdrawal is 409), but the one after it is always 429."""
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    calls = {
        "list": lambda: client.get(OFFERS_URL, headers=creator.headers),
        "read": lambda: client.get(
            f"{OFFERS_URL}/{offer['id']}", headers=creator.headers
        ),
        "withdraw": lambda: client.post(
            f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers
        ),
        "stop": lambda: client.post(STOP_URL, headers=link(offer["link_token"])),
    }
    answers = [calls[route]().status_code for _ in range(allowed + 1)]

    assert 429 not in answers[:allowed], answers
    assert answers[allowed] == 429


# --- "stop these" ----------------------------------------------------------------


def test_stop_these_blocks_that_creator_from_that_number_only(client, db, clock, on):
    creator, other = creator_user(db, clock), creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)

    stopped = client.post(STOP_URL, headers=link(offer["link_token"]))

    assert stopped.status_code == 204
    stored = row(db, offer["id"])
    assert stored.status == "stopped"
    assert stored.recipient_phone is None and stored.brand_name is None
    refused = send(client, creator, phone)
    assert refused.status_code == 409
    assert refused.json()["code"] == "direct_offer_stopped_by_recipient"
    assert send(client, other, phone).status_code == 201
    assert send(client, creator).status_code == 201
    gone = client.get(LINK_URL, headers=link(offer["link_token"]))
    assert gone.json()["code"] == "direct_offer_stopped"


def test_stop_these_works_after_a_withdrawal_or_expiry_and_twice(client, db, clock, on):
    creator = creator_user(db, clock)
    withdrawn = sent(client, creator)
    client.post(f"{OFFERS_URL}/{withdrawn['id']}/withdraw", headers=creator.headers)
    expiring = sent(client, creator)
    clock.advance(timedelta(days=15))

    for offer in (withdrawn, expiring):
        assert client.post(STOP_URL, headers=link(offer["link_token"])).status_code == 204
        assert client.post(STOP_URL, headers=link(offer["link_token"])).status_code == 204
        assert row(db, offer["id"]).status == "stopped"
    assert row(db, withdrawn["id"]).ended_at == row(db, withdrawn["id"]).created_at


def test_stop_these_on_an_unknown_link_finds_nothing(client, db, clock, on):
    response = client.post(STOP_URL, headers=link("c" * 64))
    assert response.status_code == 404
    assert client.post(STOP_URL, headers=link("short")).status_code == 404
    assert client.post(STOP_URL).status_code == 422


# --- the code -------------------------------------------------------------------


def test_the_code_goes_to_the_number_the_creator_named(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)

    response = client.post(CODE_URL, headers=link(offer["link_token"]))

    assert response.status_code == 202
    assert response.json() == {"expires_in_seconds": 300}
    assert sender.last_code_for(phone) is not None
    assert phone not in response.text


def test_the_code_keeps_the_number_s_own_caps(client, db, clock, on, sender, unlimited):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    for _ in range(3):
        assert client.post(CODE_URL, headers=link(offer["link_token"])).status_code == 202

    refused = client.post(CODE_URL, headers=link(offer["link_token"]))

    assert refused.status_code == 429
    assert refused.json()["code"] == "otp_send_limit_reached"


def test_no_code_for_an_ended_or_unknown_offer(client, db, clock, on, sender):
    creator = creator_user(db, clock)
    offer = sent(client, creator)
    client.post(f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers)

    ended = client.post(CODE_URL, headers=link(offer["link_token"]))
    unknown = client.post(CODE_URL, headers=link("d" * 64))

    assert ended.status_code == 409 and ended.json()["code"] == "direct_offer_withdrawn"
    assert unknown.status_code == 404
    assert sender.sent == []


def test_the_code_request_has_a_rate_limit_by_address(client, db, clock, on, sender):
    offers = [sent(client, creator_user(db, clock)) for _ in range(4)]
    answers = [
        client.post(CODE_URL, headers=link(offer["link_token"])).status_code
        for offer in offers
    ]

    assert answers == [202, 202, 202, 429]

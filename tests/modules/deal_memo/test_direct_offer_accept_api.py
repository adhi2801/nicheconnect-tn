"""Accepting a direct offer through the API (D-189).

One step makes the brand's account and profile, the hidden campaign and
application, and the memo agreed by both, its record opened by the
creator's proposal and sealed with the brand's acceptance; every refusal
after the code leaves the code unused and nothing made.
"""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.main import app
from app.modules.auth.models.account import Account
from app.modules.auth.models.attribution import AccountAttribution
from app.modules.auth.models.brand import Brand
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service
from app.modules.deal_memo.direct_offer_models import DirectOffer
from app.modules.deal_memo.models import DealMemo
from app.modules.notifications.models import Notification
from tests.deal_flow import MEMOS_URL, User, brand_user, creator_user
from tests.direct_offers import (
    ACCEPT_URL,
    FEE,
    LINK_URL,
    OFFERS_URL,
    STOP_URL,
    accept,
    accept_body,
    bearer,
    code_for,
    link,
    phone_of,
    sent,
    switch_on,
)
from tests.factories import fake_phone


@pytest.fixture
def on(monkeypatch) -> None:
    switch_on(monkeypatch)


@pytest.fixture
def sender(client) -> Iterator[FakeOtpSender]:
    fake = FakeOtpSender()
    app.dependency_overrides[get_otp_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_otp_sender, None)


def offer_row(db, offer_id) -> DirectOffer:
    return db.scalars(
        select(DirectOffer)
        .where(DirectOffer.id == offer_id)
        .execution_options(populate_existing=True)
    ).one()


def accounts_on(db, phone: str) -> list[str]:
    return sorted(db.scalars(select(Account.role).where(Account.phone == phone)).all())


def test_accepting_makes_the_brand_and_the_agreed_deal_in_one_step(
    client, db, clock, on, sender
):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    clock.advance(timedelta(hours=3))

    response = accept(client, sender, offer, phone, brand_name="Amma Sweets Madurai")

    assert response.status_code == 200, response.text
    body = response.json()
    assert response.headers["cache-control"] == "no-store"
    assert body["account"]["role"] == "brand" and body["account"]["is_new"] is True
    account = db.get_one(Account, body["account"]["id"])
    assert account.phone == phone and account.adult_confirmed_at == clock.now
    brand = db.scalars(select(Brand).where(Brand.account_id == account.id)).one()
    assert brand.name == "Amma Sweets Madurai"
    attribution = db.scalars(
        select(AccountAttribution).where(AccountAttribution.account_id == account.id)
    ).one()
    assert (attribution.source, attribution.campaign_tag) == ("other", "direct-offer")

    memo = db.get_one(DealMemo, body["deal_memo_id"])
    application = db.get_one(Application, memo.application_id)
    campaign = db.get_one(Campaign, application.campaign_id)
    assert (campaign.campaign_type, campaign.status, campaign.brand_id) == (
        "direct",
        "closed",
        brand.id,
    )
    assert campaign.budget_min_paise is None
    assert (application.origin, application.status, application.pitch) == (
        "direct",
        "accepted",
        None,
    )
    assert memo.status == "accepted" and memo.terms_version == 3
    assert memo.sent_at == clock.now - timedelta(hours=3)
    assert memo.accepted_at == clock.now
    assert memo.fee_amount_paise == FEE and memo.usage_rights_days == 90
    assert [(i.platform, i.format, i.quantity) for i in memo.deliverable_items] == [
        ("instagram", "reel", 2)
    ]
    assert record_service.terms_fingerprint(memo) == offer["terms_sha256"]

    stored = offer_row(db, offer["id"])
    assert stored.status == "accepted" and stored.deal_memo_id == memo.id
    assert stored.recipient_phone is None and stored.brand_name is None

    told = db.scalars(
        select(Notification).where(Notification.account_id == creator.account_id)
    ).all()
    assert [(n.notification_type, n.application_id) for n in told] == [
        ("memo_accepted", application.id)
    ]


def test_the_record_opens_with_the_proposal_and_seals_the_acceptance(
    client, db, clock, on, sender
):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    clock.advance(timedelta(hours=3))
    body = accept(client, sender, offer, phone).json()

    record = client.get(
        f"{MEMOS_URL}/{body['deal_memo_id']}/record", headers=creator.headers
    ).json()

    assert record["intact"] is True
    assert record["terms_unchanged_since_accepted"] is True
    kinds = [(e["kind"], e["actor_role"]) for e in record["entries"]]
    assert kinds == [
        ("direct_offer_proposed", "creator"),
        ("direct_offer_accepted", "brand"),
    ]
    proposed, accepted = record["entries"]
    assert proposed["occurred_at"] == "2026-09-17T12:00:00.000000Z"
    assert accepted["occurred_at"] == "2026-09-17T15:00:00.000000Z"
    assert proposed["facts"]["terms_sha256"] == offer["terms_sha256"]
    assert accepted["facts"] == {
        "terms_sha256": offer["terms_sha256"],
        "fee_amount_paise": FEE,
        "content_due_on": "2026-10-15",
        "proven_by": "phone_code",
    }
    assert proposed["actor_account_sha256"] == record_service.actor_fingerprint(
        creator.account_id
    )
    assert accepted["actor_account_sha256"] == record_service.actor_fingerprint(
        body["account"]["id"]
    )


def test_the_record_sees_a_changed_term_after_acceptance(client, db, clock, on, sender):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    memo_id = accept(client, sender, offer, phone).json()["deal_memo_id"]
    memo = db.get_one(DealMemo, memo_id)
    memo.fee_amount_paise = FEE + 1
    db.flush()

    record = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=creator.headers).json()

    assert record["intact"] is True
    assert record["terms_unchanged_since_accepted"] is False


def test_both_sides_then_read_the_deal_as_any_other(client, db, clock, on, sender):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    body = accept(client, sender, offer, phone).json()
    brand_headers = bearer(body["access_token"])

    as_brand = client.get(f"{MEMOS_URL}/{body['deal_memo_id']}", headers=brand_headers)
    as_creator = client.get(
        f"{MEMOS_URL}/{body['deal_memo_id']}", headers=creator.headers
    )
    mine = client.get(f"{MEMOS_URL}/mine", headers=creator.headers).json()["items"]
    listed = client.get(f"{OFFERS_URL}/{offer['id']}", headers=creator.headers).json()

    assert as_brand.status_code == 200, as_brand.text
    assert as_creator.status_code == 200
    assert as_brand.json()["status"] == "accepted"
    assert [m["id"] for m in mine] == [body["deal_memo_id"]]
    assert (
        listed["status"] == "accepted" and listed["deal_memo_id"] == body["deal_memo_id"]
    )
    gone = client.get(LINK_URL, headers=link(offer["link_token"]))
    assert (
        gone.status_code == 409 and gone.json()["code"] == "direct_offer_already_accepted"
    )
    assert client.post(STOP_URL, headers=link(offer["link_token"])).status_code == 409


def nothing_made(db, phone: str, offer_id) -> None:
    assert accounts_on(db, phone) == []
    assert offer_row(db, offer_id).status == "sent"


def test_a_wrong_code_makes_nothing_and_uses_an_attempt(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    code = code_for(client, sender, offer["link_token"], phone)
    wrong = "000000" if code != "000000" else "111111"

    response = client.post(
        ACCEPT_URL,
        json=accept_body(wrong, offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "otp_invalid"
    nothing_made(db, phone, offer["id"])
    right = client.post(
        ACCEPT_URL,
        json=accept_body(code, offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )
    assert right.status_code == 200


def test_only_the_terms_shown_are_accepted_and_the_code_stays_unused(
    client, db, clock, on, sender
):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    code = code_for(client, sender, offer["link_token"], phone)

    refused = client.post(
        ACCEPT_URL,
        json=accept_body(code, "0" * 64),
        headers=link(offer["link_token"]),
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "direct_offer_terms_mismatch"
    nothing_made(db, phone, offer["id"])
    again = client.post(
        ACCEPT_URL,
        json=accept_body(code, offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )
    assert again.status_code == 200


def test_a_successful_acceptance_uses_the_code_up(client, db, clock, on, sender):
    """Else the code would still sign the number in for the rest of its
    5 minutes."""
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)

    assert accept(client, sender, offer, phone).status_code == 200

    assert not code_unused(db, phone)


def test_a_number_with_a_brand_account_cannot_accept(client, db, clock, on, sender):
    brand = brand_user(db, clock)
    phone = phone_of(db, brand)
    offer = sent(client, creator_user(db, clock), phone)

    response = accept(client, sender, offer, phone)

    assert response.status_code == 409
    assert response.json()["code"] == "brand_account_exists"
    assert offer_row(db, offer["id"]).status == "sent"
    assert accounts_on(db, phone) == ["brand"]


def test_a_creator_s_number_takes_a_brand_as_its_second_side(
    client, db, clock, on, sender
):
    other_creator = creator_user(db, clock)
    phone = phone_of(db, other_creator)
    offer = sent(client, creator_user(db, clock), phone)

    response = accept(client, sender, offer, phone)

    assert response.status_code == 200, response.text
    assert accounts_on(db, phone) == ["brand", "creator"]


def test_an_admin_s_number_reads_as_a_mismatch(client, db, clock, on, sender):
    admin = Account(phone=fake_phone(), role="admin")
    db.add(admin)
    db.flush()
    offer = sent(client, creator_user(db, clock), admin.phone)

    response = accept(client, sender, offer, admin.phone)

    assert response.status_code == 409
    assert response.json()["code"] == "role_mismatch"


def test_a_memo_that_drifts_from_the_accepted_terms_is_never_committed(
    client, db, clock, on, sender, monkeypatch
):
    """The memo is held to the fingerprint the brand accepted before anything
    is sealed: a fault that wrote other terms makes nothing at all."""
    from app.modules.deal_memo import direct_offer_service

    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    real = direct_offer_service.memos.replace_deliverables

    def drifted(session, memo_id, items, now):
        changed = [{**item, "quantity": item["quantity"] + 1} for item in items]
        return real(session, memo_id, changed, now)

    monkeypatch.setattr(direct_offer_service.memos, "replace_deliverables", drifted)

    response = accept(client, sender, offer, phone)

    # A bug, never a person's mistake: the generic 500, nothing made.
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert accounts_on(db, phone) == []
    assert offer_row(db, offer["id"]).status == "sent"


def code_unused(db, phone: str) -> bool:
    """Whether the number's newest code is still unused."""
    from app.modules.auth.models.otp_challenge import OtpChallenge

    newest = db.scalars(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone)
        .order_by(OtpChallenge.created_at.desc())
        .execution_options(populate_existing=True)
    ).first()
    return newest is not None and newest.consumed_at is None


def test_a_suspended_side_on_the_number_takes_no_brand(client, db, clock, on, sender):
    """A suspended creator cannot step round their suspension with a brand
    made at a link, as at login (D-126); told only after the code was right."""
    suspended = creator_user(db, clock)
    account = db.get_one(Account, suspended.account_id)
    phone = account.phone
    offer = sent(client, creator_user(db, clock), phone)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.flush()

    response = accept(client, sender, offer, phone)

    assert response.status_code == 403
    assert response.json()["code"] == "account_suspended"
    assert accounts_on(db, phone) == ["creator"]
    assert offer_row(db, offer["id"]).status == "sent"
    assert code_unused(db, phone)


def test_a_number_an_account_waits_to_move_onto_takes_no_brand(
    client, db, clock, on, sender
):
    """Else the moving account would land on a number a brand was just made
    on, as login refuses (D-108)."""
    from app.modules.auth.models.account_phone_change import (
        PHONE_CHANGE_WAIT,
        AccountPhoneChange,
    )

    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    mover = brand_user(db, clock)
    db.add(
        AccountPhoneChange(
            account_id=mover.account_id,
            new_phone=phone,
            requested_at=clock.now,
            takes_effect_at=clock.now + PHONE_CHANGE_WAIT,
        )
    )
    db.flush()

    response = accept(client, sender, offer, phone)

    assert response.status_code == 409
    assert response.json()["code"] == "phone_change_waiting"
    assert accounts_on(db, phone) == []
    assert offer_row(db, offer["id"]).status == "sent"
    assert code_unused(db, phone)


def test_the_creator_s_own_number_never_accepts(client, db, clock, on, sender):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    # The creator moves onto the number after sending.
    db.get_one(Account, creator.account_id).phone = phone
    db.flush()

    response = accept(client, sender, offer, phone)

    assert response.status_code == 409
    assert response.json()["code"] == "direct_offer_own_number"


def test_only_an_adult_accepts(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)

    code = code_for(client, sender, offer["link_token"], phone)

    def accept_born(born: str):
        return client.post(
            ACCEPT_URL,
            json=accept_body(code, offer["terms_sha256"], date_of_birth=born),
            headers=link(offer["link_token"]),
        )

    response = accept_born("2008-09-18")

    assert response.status_code == 422
    assert response.json()["code"] == "must_be_18_or_over"
    nothing_made(db, phone, offer["id"])
    # The refusal left the code unused: eighteen today accepts with it.
    assert accept_born("2008-09-17").status_code == 200


def test_an_email_another_brand_uses_is_refused(client, db, clock, on, sender):
    taken = db.scalars(
        select(Brand.email).where(Brand.account_id == brand_user(db, clock).account_id)
    ).one()
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)

    response = accept(client, sender, offer, phone, email=taken.upper())

    assert response.status_code == 409
    assert response.json()["code"] == "email_taken"
    nothing_made(db, phone, offer["id"])


def test_a_look_alike_of_a_protected_brand_cannot_be_made_at_a_link(
    client, db, clock, on, sender
):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)

    response = accept(client, sender, offer, phone, brand_name="Nykaa Official")

    assert response.status_code == 409
    assert response.json()["code"] == "brand_name_needs_domain"
    nothing_made(db, phone, offer["id"])
    assert (
        db.scalar(select(func.count(Brand.id)).where(Brand.name == "Nykaa Official")) == 0
    )


def test_a_due_date_that_passed_while_it_waited_is_refused(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone, content_due_on="2026-09-20")
    clock.advance(timedelta(days=4))

    response = accept(client, sender, offer, phone)

    assert response.status_code == 409
    assert response.json()["code"] == "due_date_has_passed"
    nothing_made(db, phone, offer["id"])


@pytest.mark.parametrize("ending", ["withdraw", "expire", "stop"])
def test_an_ended_offer_cannot_be_accepted(client, db, clock, on, sender, ending):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    code = code_for(client, sender, offer["link_token"], phone)
    if ending == "withdraw":
        client.post(f"{OFFERS_URL}/{offer['id']}/withdraw", headers=creator.headers)
    elif ending == "expire":
        clock.advance(timedelta(days=14))
    else:
        client.post(STOP_URL, headers=link(offer["link_token"]))

    response = client.post(
        ACCEPT_URL,
        json=accept_body(code, offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )

    assert response.status_code == 409
    assert (
        response.json()["code"]
        == {
            "withdraw": "direct_offer_withdrawn",
            "expire": "direct_offer_expired",
            "stop": "direct_offer_stopped",
        }[ending]
    )
    assert accounts_on(db, phone) == []


def test_an_offer_is_accepted_once(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    assert accept(client, sender, offer, phone).status_code == 200

    again = client.post(
        ACCEPT_URL,
        json=accept_body("123456", offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )

    assert again.status_code == 409
    assert again.json()["code"] == "direct_offer_already_accepted"


def test_a_creator_who_left_or_was_suspended_cannot_be_dealt_with(
    client, db, clock, on, sender
):
    creator = creator_user(db, clock)
    phone = fake_phone()
    offer = sent(client, creator, phone)
    code = code_for(client, sender, offer["link_token"], phone)
    account = db.get_one(Account, creator.account_id)
    account.suspended_at = clock.now
    account.suspension_reason = "fake_profile"
    db.flush()

    response = client.post(
        ACCEPT_URL,
        json=accept_body(code, offer["terms_sha256"]),
        headers=link(offer["link_token"]),
    )

    assert response.status_code == 404
    assert accounts_on(db, phone) == []


def test_accepting_validates_its_body_and_its_link(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    good = accept_body("123456", offer["terms_sha256"])
    bad = [
        {**good, "code": "12345"},
        {**good, "terms_sha256": "xyz"},
        {**good, "email": "not-an-email"},
        {**good, "brand_name": ""},
        {**good, "role": "admin"},
    ]
    for body in bad:
        response = client.post(ACCEPT_URL, json=body, headers=link(offer["link_token"]))
        assert response.status_code == 422, body
    assert client.post(ACCEPT_URL, json=good).status_code == 422
    unknown = client.post(ACCEPT_URL, json=good, headers=link("e" * 64))
    assert unknown.status_code == 404


def test_accepting_has_a_rate_limit_by_address(client, db, clock, on, sender):
    offer = sent(client, creator_user(db, clock))
    answers = [
        client.post(
            ACCEPT_URL,
            json=accept_body("123456", "0" * 64),
            headers=link("f" * 64),
        ).status_code
        for _ in range(11)
    ]

    assert answers[:10] == [404] * 10
    assert answers[10] == 429
    assert offer["status"] == "sent"


def test_the_brand_signs_in_with_its_tokens(client, db, clock, on, sender):
    phone = fake_phone()
    offer = sent(client, creator_user(db, clock), phone)
    body = accept(client, sender, offer, phone).json()

    me = client.get("/api/v1/auth/me", headers=bearer(body["access_token"]))
    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )

    assert me.status_code == 200 and me.json()["role"] == "brand"
    assert refreshed.status_code == 200


def user_of(body: dict, clock) -> User:
    return User(body["account"]["id"], "brand", clock)

"""Direct offers and the people in them: export and erasure (D-189, the
privacy impact assessment).

The creator's offers are in the creator's export, and the one that became
its deal in the brand's; the brand's number, and every keyed hash, are in
nobody's. A departing creator's offers that never became a deal are
erased with the account; one that did stays, as the deal's history, its
number and name already gone; nobody else's offer is touched.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.sender import FakeOtpSender, get_otp_sender
from app.modules.deal_memo import direct_offer_service as offers
from app.modules.deal_memo.direct_offer_models import DirectOffer
from app.modules.me import export_service
from app.modules.me.account_deletion_registry import KEPT
from tests.deal_flow import creator_user
from tests.direct_offers import OFFERS_URL, accept, sent, switch_on
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


def section(db, account_id, clock) -> list[dict]:
    account = db.get_one(Account, account_id)
    for found in export_service.collect_sections(db, account, clock.now):
        if found.name == "direct_offers":
            return found.records
    raise AssertionError("no direct_offers section")


def creator_id_of(db, user) -> object:
    return db.scalars(
        select(Creator.id).where(Creator.account_id == user.account_id)
    ).one()


def test_the_creator_exports_every_offer_and_never_a_number(
    client, db, clock, on, sender
):
    creator, bystander = creator_user(db, clock), creator_user(db, clock)
    phone = fake_phone()
    waiting = sent(client, creator)
    accepted_offer = sent(client, creator, phone)
    accept(client, sender, accepted_offer, phone)
    sent(client, bystander)
    stored = db.get_one(DirectOffer, waiting["id"])

    rows = section(db, creator.account_id, clock)

    assert {row["id"] for row in rows} == {waiting["id"], accepted_offer["id"]}
    by_id = {row["id"]: row for row in rows}
    assert by_id[waiting["id"]]["brand_name"] == "Amma Sweets"
    assert by_id[accepted_offer["id"]]["status"] == "accepted"
    text = repr(rows)
    assert stored.recipient_phone is not None
    assert stored.recipient_phone not in text and phone not in text
    assert stored.recipient_phone_hash not in text and stored.token_hash not in text
    assert all(
        not ({"recipient_phone", "recipient_phone_hash", "token_hash"} & set(row))
        for row in rows
    )


def test_the_brand_exports_the_offer_that_became_its_deal(client, db, clock, on, sender):
    """Two brands, each made by accepting an offer (testing.md section 2: two
    of every kind), so a missing brand condition cannot pass by luck."""
    creator = creator_user(db, clock)
    phone, other_phone = fake_phone(), fake_phone()
    offer = sent(client, creator, phone)
    other_offer = sent(client, creator, other_phone)
    sent(client, creator)
    brand_account = accept(client, sender, offer, phone).json()["account"]["id"]
    other_account = accept(client, sender, other_offer, other_phone).json()["account"][
        "id"
    ]

    rows = section(db, brand_account, clock)
    other_rows = section(db, other_account, clock)

    assert [row["id"] for row in rows] == [offer["id"]]
    assert [row["id"] for row in other_rows] == [other_offer["id"]]


def test_erasing_a_creator_erases_offers_that_never_became_deals(
    client, db, clock, on, sender
):
    creator, bystander = creator_user(db, clock), creator_user(db, clock)
    phone = fake_phone()
    waiting = sent(client, creator)
    withdrawn = sent(client, creator)
    client.post(f"{OFFERS_URL}/{withdrawn['id']}/withdraw", headers=creator.headers)
    deal = sent(client, creator, phone)
    accept(client, sender, deal, phone)
    others = sent(client, bystander)

    offers.erase_for_creator(db, creator_id_of(db, creator))
    db.flush()

    left = set(
        db.scalars(
            select(DirectOffer.id).where(
                DirectOffer.id.in_(
                    [waiting["id"], withdrawn["id"], deal["id"], others["id"]]
                )
            )
        ).all()
    )
    assert {str(offer_id) for offer_id in left} == {deal["id"], others["id"]}


def test_the_whole_erasure_takes_a_creator_s_offers_with_it(client, db, clock, on):
    from tests.modules.me.test_account_deletion_erasure import due, person, run

    creator, bystander = creator_user(db, clock), creator_user(db, clock)
    mine = sent(client, creator)
    theirs = sent(client, bystander)
    due(db, person(db, creator), clock)

    assert run(db, clock).erased == 1

    ids = {mine["id"], theirs["id"]}
    left = {
        str(found)
        for found in db.scalars(select(DirectOffer.id).where(DirectOffer.id.in_(ids)))
    }
    assert left == {theirs["id"]}


def test_the_registry_keeps_only_offers_that_became_deals():
    kept = {table for kind in KEPT for table in kind.tables}

    assert "direct_offer" in kept
    assert frozenset({"direct_offer"}) == offers.EXPORTED_TABLES

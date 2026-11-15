"""Direct offers' hourly job: expiry and erasure (D-189, the privacy impact
assessment).

An offer whose 14 days ran out is marked expired and its number and name
erased; one that ended without a deal is deleted 30 days after it ended; a
stopped one stays, as the block its number's holder asked for; one that
became a deal stays, as the deal's history. Running it twice changes nothing
more, and an offer an acceptance holds is skipped, never waited on.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.deal_memo import direct_offer_jobs
from app.modules.deal_memo import direct_offer_service as offers
from app.modules.deal_memo.direct_offer_models import (
    DIRECT_OFFER_LIFETIME,
    ENDED_OFFER_KEPT_FOR,
    DirectOffer,
)
from tests.deal_flow import creator_user
from tests.direct_offers import LINK_URL, OFFERS_URL, STOP_URL, link, sent, switch_on


@pytest.fixture
def on(monkeypatch) -> None:
    switch_on(monkeypatch)


def stored(db, offer_id) -> DirectOffer | None:
    return db.scalars(
        select(DirectOffer)
        .where(DirectOffer.id == uuid.UUID(str(offer_id)))
        .execution_options(populate_existing=True)
    ).first()


def test_an_offer_whose_days_ran_out_is_expired_and_emptied(client, db, clock, on):
    creator = creator_user(db, clock)
    running_out = sent(client, creator)
    clock.advance(timedelta(days=1))
    still_waiting = sent(client, creator)
    ran_out_at = clock.now - timedelta(days=1) + DIRECT_OFFER_LIFETIME

    run = offers.expire_and_erase(db, ran_out_at)

    assert run.expired >= 1
    expired = stored(db, running_out["id"])
    assert expired is not None
    assert (expired.status, expired.ended_at) == ("expired", ran_out_at)
    assert (expired.recipient_phone, expired.brand_name) == (None, None)
    waiting = stored(db, still_waiting["id"])
    assert waiting is not None and waiting.status == "sent"
    assert waiting.recipient_phone is not None and waiting.brand_name is not None


def test_one_moment_before_its_last_it_still_waits(client, db, clock, on):
    offer = sent(client, creator_user(db, clock))

    offers.expire_and_erase(db, clock.now + DIRECT_OFFER_LIFETIME - timedelta(seconds=1))

    found = stored(db, offer["id"])
    assert found is not None and found.status == "sent"


def test_an_offer_ended_without_a_deal_is_deleted_after_30_days(client, db, clock, on):
    creator = creator_user(db, clock)
    withdrawn = sent(client, creator)
    expired = sent(client, creator)
    stopped = sent(client, creator)
    assert (
        client.post(
            f"{OFFERS_URL}/{withdrawn['id']}/withdraw", headers=creator.headers
        ).status_code
        == 200
    )
    assert client.post(STOP_URL, headers=link(stopped["link_token"])).status_code == 204
    offers.expire_and_erase(db, clock.now + DIRECT_OFFER_LIFETIME)
    withdrawn_at = clock.now
    expired_at = clock.now + DIRECT_OFFER_LIFETIME

    offers.expire_and_erase(
        db, withdrawn_at + ENDED_OFFER_KEPT_FOR - timedelta(seconds=1)
    )
    assert stored(db, withdrawn["id"]) is not None

    offers.expire_and_erase(db, withdrawn_at + ENDED_OFFER_KEPT_FOR)
    assert stored(db, withdrawn["id"]) is None
    assert stored(db, expired["id"]) is not None

    offers.expire_and_erase(db, expired_at + ENDED_OFFER_KEPT_FOR)
    assert stored(db, expired["id"]) is None
    # "Stop these" is the number's block: it stays.
    kept = stored(db, stopped["id"])
    assert kept is not None and kept.status == "stopped"
    assert kept.recipient_phone_hash is not None and kept.recipient_phone is None


def test_running_it_twice_changes_nothing_more(client, db, clock, on):
    offer = sent(client, creator_user(db, clock))
    ran_out = clock.now + DIRECT_OFFER_LIFETIME

    offers.expire_and_erase(db, ran_out)
    first = stored(db, offer["id"])
    assert first is not None
    once = (first.status, first.ended_at, first.updated_at)
    offers.expire_and_erase(db, ran_out + timedelta(hours=1))
    second = stored(db, offer["id"])

    assert second is not None
    assert (second.status, second.ended_at, second.updated_at) == once


def test_an_expired_link_answers_clearly_before_and_after_the_job(client, db, clock, on):
    offer = sent(client, creator_user(db, clock))
    clock.advance(DIRECT_OFFER_LIFETIME)

    before = client.get(LINK_URL, headers=link(offer["link_token"]))
    offers.expire_and_erase(db, clock.now)
    after = client.get(LINK_URL, headers=link(offer["link_token"]))

    assert before.json()["code"] == after.json()["code"] == "direct_offer_expired"


def test_the_scheduled_run_does_the_work_once_per_call(monkeypatch):
    seen = []

    def work(db, now):
        seen.append(now)
        return offers.JobRun(expired=0, deleted=0)

    monkeypatch.setattr(offers, "expire_and_erase", work)
    at = datetime(2020, 1, 1, tzinfo=UTC)

    assert direct_offer_jobs.run(at) == offers.JobRun(expired=0, deleted=0)
    assert seen == [at]


def test_the_run_logs_counts_never_a_number(client, db, clock, on, caplog):
    offer = sent(client, creator_user(db, clock))
    phone = stored(db, offer["id"]).recipient_phone

    with caplog.at_level("INFO", logger=offers.__name__):
        offers.expire_and_erase(db, clock.now + DIRECT_OFFER_LIFETIME)

    assert any("direct_offers.run expired=" in r.getMessage() for r in caplog.records)
    assert phone is not None
    assert all(phone not in r.getMessage() for r in caplog.records)

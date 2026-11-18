"""Direct offers' "only one wins" rules, raced on real committed connections (D-189).

testing.md section 4: several requests released together on a barrier, the
moment between check and write held open (`slow_writes`), exactly one
success, the rest clean domain errors, and a consistent final state.

- two acceptances of one link make one brand and one deal: the number's
  lock and its single-use code;
- an acceptance racing a withdrawal, or a "stop these": the offer's lock,
  so one lands wholly before the other, never both;
- a creator's 10 offers a Tamil Nadu day: the creator's row lock;
- one number's 3 offers a week, from different creators: the number's
  advisory lock.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select, text

from app.core.config import settings
from app.core.errors import DomainError
from app.db.session import SessionLocal
from app.modules.auth import service as login
from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.deal_memo import direct_offer_notices as notices
from app.modules.deal_memo import direct_offer_rules as rules
from app.modules.deal_memo import direct_offer_service as offers
from app.modules.deal_memo.direct_offer_models import DIRECT_OFFER_LIFETIME, DirectOffer
from app.modules.deal_memo.exceptions import (
    DirectOfferAlreadyAccepted,
    DirectOfferDailyLimit,
    DirectOfferNotFound,
    DirectOfferNumberLimit,
    DirectOfferStopped,
    DirectOfferWithdrawn,
)
from tests.factories import build_creator, create_account, unique_test_phone
from tests.modules.conftest import CONCURRENCY_NOW
from tests.owner import owner_engine
from tests.record_cleanup import remove_deal_records

NOW = CONCURRENCY_NOW


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "direct_offers_enabled", True)
    monkeypatch.setattr(notices, "LINK_PAGE_NOTICE", "Test wording, not a notice.")
    monkeypatch.setattr(notices, "CODE_MESSAGE", "Test wording, not a notice.")


def run_together(*works: Callable[[Any], Any]) -> list[Any]:
    """Run each `work(session)` in its own thread, released together."""
    barrier = threading.Barrier(len(works))
    results: list[Any] = [None] * len(works)

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = works[index](session)
            except Exception as exc:  # collected and asserted by the test
                session.rollback()
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(works))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


@dataclass
class World:
    """What a test committed, so it can all be removed afterwards."""

    creators: list[uuid.UUID] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)

    def creator(self) -> Creator:
        with SessionLocal() as session:
            phone = unique_test_phone()
            account = create_account(session, "creator", phone=phone)
            creator = build_creator(
                session, handle=f"do{uuid.uuid4().hex[:12]}", account_id=account.id
            )
            session.add(creator)
            session.commit()
            session.refresh(creator)
            session.expunge(creator)
            self.creators.append(creator.id)
            self.phones.append(phone)
            return creator

    def number(self) -> str:
        phone = unique_test_phone()
        self.phones.append(phone)
        return phone

    def remove(self) -> None:
        with SessionLocal() as session:
            memo_ids = list(
                session.scalars(
                    select(DirectOffer.deal_memo_id).where(
                        DirectOffer.creator_id.in_(self.creators),
                        DirectOffer.deal_memo_id.is_not(None),
                    )
                ).all()
            )
        remove_deal_records(memo_ids)
        # Everything an acceptance made, removed with triggers and foreign
        # keys set aside for this one transaction (tests/record_cleanup.py).
        with owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            params = {"creators": self.creators, "phones": self.phones, "memos": memo_ids}
            for statement in (
                "DELETE FROM direct_offer WHERE creator_id = ANY(:creators)",
                "DELETE FROM memo_deliverable WHERE deal_memo_id = ANY(:memos)",
                "DELETE FROM notification WHERE account_id IN"
                " (SELECT id FROM account WHERE phone = ANY(:phones))",
                "DELETE FROM deal_memo WHERE id = ANY(:memos)",
                "DELETE FROM application WHERE creator_id = ANY(:creators)",
                "DELETE FROM campaign WHERE brand_id IN (SELECT b.id FROM brand b"
                " JOIN account a ON a.id = b.account_id WHERE a.phone = ANY(:phones))",
                "DELETE FROM brand WHERE account_id IN"
                " (SELECT id FROM account WHERE phone = ANY(:phones))",
                "DELETE FROM account_attribution WHERE account_id IN"
                " (SELECT id FROM account WHERE phone = ANY(:phones))",
                "DELETE FROM auth_session WHERE account_id IN"
                " (SELECT id FROM account WHERE phone = ANY(:phones))",
                "DELETE FROM creator WHERE id = ANY(:creators)",
                "DELETE FROM account WHERE phone = ANY(:phones)",
                "DELETE FROM otp_challenge WHERE phone = ANY(:phones)",
            ):
                connection.execute(text(statement), params)


@pytest.fixture
def world() -> Iterator[World]:
    made = World()
    try:
        yield made
    finally:
        made.remove()


def terms(phone: str) -> dict[str, Any]:
    return {
        "brand_name": "Amma Sweets",
        "brand_phone": phone,
        "deliverables": "2 Instagram reels about the Diwali sweet box",
        "deliverable_items": [],
        "fee_amount_paise": 900_000,
        "cancellation_fee_paise": 0,
        "approval_window_days": 7,
        "payment_due_days": 7,
        "usage_rights_days": None,
        "content_due_on": (NOW + timedelta(days=20)).date(),
        "disclosure_required": True,
        "draft_review": False,
        "extra_terms": None,
    }


def send(creator: Creator, phone: str, at=NOW) -> offers.SentOffer:
    with SessionLocal() as session:
        return offers.send(session, creator, terms(phone), at)


def code_for(phone: str) -> str:
    with SessionLocal() as session:
        pending = login.request_otp(session, phone, NOW)
        session.commit()
        return pending.code


def accept_with(token: str, code: str, sha: str) -> Callable[[Any], Any]:
    def work(session: Any) -> offers.Acceptance:
        return offers.accept(
            session,
            token,
            {
                "brand_name": "Amma Sweets",
                "email": f"owner-{uuid.uuid4().hex[:12]}@example.com",
                "date_of_birth": NOW.date().replace(year=1990),
                "code": code,
                "terms_sha256": sha,
            },
            NOW + timedelta(minutes=1),
        )

    return work


def brands_on(phone: str) -> int:
    with SessionLocal() as session:
        return len(
            session.scalars(
                select(Account.id).where(Account.phone == phone, Account.role == "brand")
            ).all()
        )


def offer_status(offer_id: uuid.UUID) -> str:
    with SessionLocal() as session:
        return session.scalars(
            select(DirectOffer.status).where(DirectOffer.id == offer_id)
        ).one()


def test_two_acceptances_of_one_link_make_one_brand_and_one_deal(world, slow_writes):
    creator, phone = world.creator(), world.number()
    sent = send(creator, phone)
    code = code_for(phone)
    accept = accept_with(sent.link_token, code, sent.offer.terms_sha256)

    results = run_together(accept, accept, accept)

    assert sum(isinstance(r, offers.Acceptance) for r in results) == 1, results
    assert all(isinstance(r, (offers.Acceptance, DomainError)) for r in results), results
    assert brands_on(phone) == 1
    assert offer_status(sent.offer.id) == "accepted"


def withdrawal(sent: offers.SentOffer) -> Callable[[Any], Any]:
    def work(session: Any) -> DirectOffer:
        offer = session.get_one(DirectOffer, sent.offer.id)
        return offers.withdraw(session, offer, NOW + timedelta(minutes=1))

    return work


def stopping(sent: offers.SentOffer) -> Callable[[Any], Any]:
    def work(session: Any) -> str:
        offers.stop(session, sent.link_token, NOW + timedelta(minutes=1))
        return "stopped"

    return work


ENDINGS = {
    "withdrawal": (withdrawal, "withdrawn", DirectOfferWithdrawn),
    "stop": (stopping, "stopped", DirectOfferStopped),
}


@pytest.mark.parametrize("ending", ENDINGS)
def test_an_acceptance_and_an_ending_never_both_land(world, slow_writes, ending):
    make_ending, ended_status, refused_acceptance = ENDINGS[ending]
    for _ in range(3):
        creator, phone = world.creator(), world.number()
        sent = send(creator, phone)
        code = code_for(phone)

        results = run_together(
            accept_with(sent.link_token, code, sent.offer.terms_sha256),
            make_ending(sent),
        )

        accepted = isinstance(results[0], offers.Acceptance)
        ended = not isinstance(results[1], Exception)
        assert accepted != ended, results
        if accepted:
            assert isinstance(results[1], DirectOfferAlreadyAccepted), results
            assert offer_status(sent.offer.id) == "accepted"
            assert brands_on(phone) == 1
        else:
            assert isinstance(results[0], refused_acceptance), results
            assert offer_status(sent.offer.id) == ended_status
            assert brands_on(phone) == 0


def test_a_creator_s_tenth_offer_of_the_day_is_sent_once(world, slow_writes):
    creator = world.creator()
    for _ in range(rules.DAILY_OFFERS_PER_CREATOR - 1):
        send(creator, world.number())
    numbers = [world.number() for _ in range(4)]

    results = run_together(
        *(
            lambda session, phone=phone: offers.send(session, creator, terms(phone), NOW)
            for phone in numbers
        )
    )

    assert sum(isinstance(r, offers.SentOffer) for r in results) == 1, results
    assert sum(isinstance(r, DirectOfferDailyLimit) for r in results) == 3, results
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(DirectOffer)
                .where(DirectOffer.creator_id == creator.id)
            )
            == rules.DAILY_OFFERS_PER_CREATOR
        )


def test_a_number_s_third_offer_of_the_week_is_sent_once(world, slow_writes):
    phone = world.number()
    for _ in range(rules.WEEKLY_OFFERS_PER_NUMBER - 1):
        send(world.creator(), phone)
    senders = [world.creator() for _ in range(4)]

    results = run_together(
        *(
            lambda session, creator=creator: offers.send(
                session, creator, terms(phone), NOW
            )
            for creator in senders
        )
    )

    assert sum(isinstance(r, offers.SentOffer) for r in results) == 1, results
    assert sum(isinstance(r, DirectOfferNumberLimit) for r in results) == 3, results
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(DirectOffer)
                .where(
                    DirectOffer.recipient_phone_hash == rules.hash_recipient_phone(phone)
                )
            )
            == rules.WEEKLY_OFFERS_PER_NUMBER
        )


def test_the_hourly_job_skips_an_offer_held_by_an_acceptance(world):
    """The job never waits on an offer an acceptance holds (SKIP LOCKED): it
    leaves it, and the next run finds it accepted or still due."""
    creator, phone = world.creator(), world.number()
    sent = send(creator, phone)
    ran_out = NOW + DIRECT_OFFER_LIFETIME
    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        with SessionLocal() as session:
            session.execute(
                select(DirectOffer.id)
                .where(DirectOffer.id == sent.offer.id)
                .with_for_update()
            )
            holding.set()
            release.wait(timeout=10)
            session.rollback()

    holder = threading.Thread(target=hold)
    holder.start()
    holding.wait(timeout=10)
    try:
        started = time.monotonic()
        with SessionLocal() as session:
            offers.expire_and_erase(session, ran_out)
        waited = time.monotonic() - started
    finally:
        release.set()
        holder.join(timeout=10)

    assert waited < 2, waited
    assert offer_status(sent.offer.id) == "sent"
    with SessionLocal() as session:
        offers.expire_and_erase(session, ran_out)
    assert offer_status(sent.offer.id) == "expired"


def test_an_offer_erased_while_an_acceptance_waits_is_not_found(world, monkeypatch):
    """A creator's erasure deletes their waiting offers while holding the
    creator's row, which an acceptance waits on; the acceptance then finds
    the offer gone and answers not found, never a raw error."""
    creator, phone = world.creator(), world.number()
    sent = send(creator, phone)
    code = code_for(phone)
    real_check = login.check_phone_code

    def check_then_erase(db, *args, **kwargs):
        challenge = real_check(db, *args, **kwargs)
        with SessionLocal() as other:
            other.execute(delete(DirectOffer).where(DirectOffer.id == sent.offer.id))
            other.commit()
        return challenge

    monkeypatch.setattr(login, "check_phone_code", check_then_erase)

    (result,) = run_together(accept_with(sent.link_token, code, sent.offer.terms_sha256))

    assert isinstance(result, DirectOfferNotFound), result
    assert brands_on(phone) == 0


def test_a_creator_suspended_while_an_acceptance_waits_is_not_found(world, monkeypatch):
    """The link was read while the creator stood; their suspension lands
    before the acceptance locks their row, which it reads again under that
    lock, so no deal is made with a suspended creator."""
    creator, phone = world.creator(), world.number()
    sent = send(creator, phone)
    code = code_for(phone)
    real_check = login.check_phone_code

    def check_then_suspend(db, *args, **kwargs):
        challenge = real_check(db, *args, **kwargs)
        with SessionLocal() as other:
            account = other.get_one(Account, creator.account_id)
            account.suspended_at = NOW
            account.suspension_reason = "fake_profile"
            other.commit()
        return challenge

    monkeypatch.setattr(login, "check_phone_code", check_then_suspend)

    (result,) = run_together(accept_with(sent.link_token, code, sent.offer.terms_sha256))

    assert isinstance(result, DirectOfferNotFound), result
    assert brands_on(phone) == 0
    assert offer_status(sent.offer.id) == "sent"


def test_the_cleanup_leaves_nothing(world):
    """The fixture's removal is itself checked, so a race test never leaves
    rows that would change another test's counts."""
    creator, phone = world.creator(), world.number()
    send(creator, phone)
    world.remove()

    with SessionLocal() as session:
        assert (
            session.scalars(
                select(DirectOffer.id).where(DirectOffer.creator_id == creator.id)
            ).all()
            == []
        )
        assert (
            session.scalars(
                select(OtpChallenge.id).where(OtpChallenge.phone == phone)
            ).all()
            == []
        )
        assert (
            session.scalars(select(Creator.id).where(Creator.id == creator.id)).all()
            == []
        )
    world.creators.clear()
    world.phones.clear()

"""Two taps arriving at once on a money record.

A creator on patchy mobile data taps twice. Both requests reach the server
together, both read the row before either writes, and both write. These tests
exist because that is not a thought experiment: before the row lock, four
simultaneous mark-paid calls had three of them win, and the last write
silently replaced the method and reference of the first — the record could
say cash when the brand had sent UPI.

Like the OTP concurrency tests, these need separate, really-committing
connections, so they cannot use the rollback fixture. They build their own
rows and delete them again.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401 — registers every table, as the app does
from app.db.session import SessionLocal
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import record_service as deal_record
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.disputes import service as disputes
from app.modules.disputes.event_models import DisputeEvent
from app.modules.disputes.exceptions import DisputeAlreadyClosed, DisputeAlreadyOpen
from app.modules.disputes.models import Dispute
from app.modules.payment_status import service as payments
from app.modules.payment_status.exceptions import (
    PaymentAlreadyConfirmed,
    PaymentAlreadyMarkedPaid,
)
from app.modules.payment_status.models import PaymentStatus
from tests.factories import build_brand, build_campaign, build_creator, create_account
from tests.record_cleanup import remove_deal_records

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
APPROVED_ON = date(2026, 9, 21)
RRN = "412345678901"


def unique_phone() -> str:
    """A valid Indian mobile nobody else in this database is using."""
    return f"+9199{uuid.uuid4().int % 10**8:08d}"


AT_ONCE = 4


def run_at_once(work: Callable[[Any], Any], count: int) -> list[Any]:
    """Run `work(session)` in `count` threads released together."""
    barrier = threading.Barrier(count)
    results: list[Any] = [None] * count

    def worker(index: int) -> None:
        with SessionLocal() as session:
            barrier.wait()
            try:
                results[index] = work(session)
                session.commit()
            except Exception as exc:  # collected and asserted by the test
                results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def run_staggered(*jobs: tuple[float, Callable[[Session], Any]]) -> list[Any]:
    """Run each `(delay, work)` on its own connection, released together, each
    starting `delay` seconds after the others are released: the order the
    race is meant to take, every run."""
    barrier = threading.Barrier(len(jobs))
    results: list[Any] = [None] * len(jobs)

    def worker(index: int, delay: float, work: Callable[[Session], Any]) -> None:
        with SessionLocal() as session:
            barrier.wait()
            time.sleep(delay)
            try:
                results[index] = work(session)
                session.commit()
            except Exception as exc:  # collected and asserted by the test
                results[index] = exc

    threads = [
        threading.Thread(target=worker, args=(i, delay, work))
        for i, (delay, work) in enumerate(jobs)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.fixture
def payment() -> Iterator[PaymentStatus]:
    """A real, committed payment record, removed again afterwards.

    Every row it needs is built here. It used to borrow whatever `application`
    happened to be in the database and skip when there was none, which meant
    these tests never ran in CI at all: CI starts from an empty database and
    has no seed step, so the skip was silent and permanent. They are the only
    tests proving two simultaneous taps cannot corrupt a money record, so
    silently not running them was the worst way to have them.
    """
    with SessionLocal() as session:
        # Phones come from a counter that restarts with the process, and these
        # rows are committed rather than rolled back, so a second run would
        # collide on uq_account_phone. Unique per run instead.
        brand_account = create_account(session, "brand", phone=unique_phone())
        creator_account = create_account(session, "creator", phone=unique_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"conc-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        creator = build_creator(
            session,
            handle=f"conc{uuid.uuid4().hex[:12]}",
            account_id=creator_account.id,
        )
        session.add(creator)
        session.flush()
        application = Application(
            campaign_id=campaign.id,
            creator_id=creator.id,
            pitch="I run a Madurai street-food page, for a concurrency test.",
            status="accepted",
            status_changed_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(application)
        session.flush()
        memo = DealMemo(
            application_id=application.id,
            deliverables="Three reels, for a concurrency test.",
            fee_amount_paise=800_000,
            status="accepted",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        record = payments.create_for_memo(session, memo, approved_on=APPROVED_ON, now=NOW)
        session.commit()
        memo_id, payment_id = memo.id, record.id
        application_id, campaign_id = application.id, campaign.id
        creator_id, brand_id = creator.id, brand.id
        account_ids = [brand_account.id, creator_account.id]

    try:
        yield payment_id
    finally:
        with SessionLocal() as session:
            # The deal record and dispute events refuse deletion (D-057,
            # item 99), so they go first, through the one test-only bypass.
            remove_deal_records([memo_id])
            session.execute(
                delete(Dispute).where(Dispute.payment_status_id == payment_id)
            )
            session.execute(delete(PaymentStatus).where(PaymentStatus.id == payment_id))
            session.execute(delete(DealMemo).where(DealMemo.id == memo_id))
            # Built by this fixture, so removed by it, innermost first.
            session.execute(delete(Application).where(Application.id == application_id))
            session.execute(delete(Campaign).where(Campaign.id == campaign_id))
            session.execute(delete(Creator).where(Creator.id == creator_id))
            session.execute(delete(Brand).where(Brand.id == brand_id))
            # The accounts behind them too, or the next run collides on the
            # phone number.
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
            session.commit()


def split(results, expected_refusal) -> tuple[int, int, list]:
    won = sum(1 for r in results if not isinstance(r, Exception))
    refused = sum(1 for r in results if isinstance(r, expected_refusal))
    unexpected = [
        r
        for r in results
        if isinstance(r, Exception) and not isinstance(r, expected_refusal)
    ]
    return won, refused, unexpected


# --- marking a payment sent -----------------------------------------------


def test_only_one_of_four_simultaneous_marks_wins(payment):
    """Without the row lock, three of these won and the last write silently
    replaced the method and reference of the first."""
    results = run_at_once(
        lambda s: payments.mark_paid(
            s, s.get(PaymentStatus, payment), method="upi", reference=RRN, now=NOW
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, PaymentAlreadyMarkedPaid)

    assert unexpected == []
    assert won == 1
    assert refused == AT_ONCE - 1


def test_the_record_keeps_one_method_and_one_reference(payment):
    """A payment record that says cash when UPI was sent is worse than no
    record at all."""
    run_at_once(
        lambda s: payments.mark_paid(
            s,
            s.get(PaymentStatus, payment),
            method="cash",
            reference="handed over at the shop",
            now=NOW,
        ),
        AT_ONCE,
    )

    with SessionLocal() as session:
        row = session.get(PaymentStatus, payment)

    assert row.method == "cash"
    assert row.reference == "handed over at the shop"
    assert row.marked_paid_at is not None


def test_only_one_of_four_simultaneous_confirmations_wins(payment):
    with SessionLocal() as session:
        payments.mark_paid(
            session,
            session.get(PaymentStatus, payment),
            method="upi",
            reference=RRN,
            now=NOW,
        )

    results = run_at_once(
        lambda s: payments.confirm_received(s, s.get(PaymentStatus, payment), now=NOW),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, PaymentAlreadyConfirmed)

    assert unexpected == []
    assert won == 1
    assert refused == AT_ONCE - 1


# --- raising a dispute ----------------------------------------------------


def test_only_one_of_four_simultaneous_disputes_is_created(payment):
    """Before the unique index's error was translated, three of these came
    back as HTTP 500 saying something went wrong on our side — which was
    untrue, and is exactly what makes a client retry."""
    results = run_at_once(
        lambda s: disputes.open_for_payment(
            s, payment, opened_by="creator", reason="x" * 40, now=NOW
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, DisputeAlreadyOpen)

    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert won == 1
    assert refused == AT_ONCE - 1


def test_a_race_never_leaves_two_disputes_on_one_payment(payment):
    run_at_once(
        lambda s: disputes.open_for_payment(
            s, payment, opened_by="creator", reason="x" * 40, now=NOW
        ),
        AT_ONCE,
    )

    with SessionLocal() as session:
        rows = session.scalars(
            select(Dispute).where(Dispute.payment_status_id == payment)
        ).all()

    assert len(rows) == 1


# --- closing a dispute, and adding to one (review finding, PR #11) ---------------


@pytest.fixture
def slow_record(monkeypatch):
    """Hold each request between its check and its commit for a moment.

    Without it the race window is a few milliseconds, threads rarely overlap,
    and a test of an unsafe service passes by luck. A busy database or a slow
    network holds that window open in production; this does the same here,
    so the test fails every time the code is unsafe.
    """
    import time

    original = disputes.record.append_for_payment

    def slow(*args, **kwargs):
        # Entries are held longer than the close, so a close commits first
        # while entries that already passed their check are still in flight:
        # the case the review describes, made certain rather than likely.
        time.sleep(0.4 if kwargs.get("kind") == "dispute_entry_added" else 0.1)
        return original(*args, **kwargs)

    monkeypatch.setattr(disputes.record, "append_for_payment", slow)


def open_dispute(payment_id) -> None:
    with SessionLocal() as session:
        disputes.open_for_payment(
            session, payment_id, opened_by="creator", reason="x" * 40, now=NOW
        )
        session.commit()


def closed_events(payment_id) -> list[DisputeEvent]:
    with SessionLocal() as session:
        return list(
            session.scalars(
                select(DisputeEvent)
                .join(Dispute, Dispute.id == DisputeEvent.dispute_id)
                .where(Dispute.payment_status_id == payment_id)
                .order_by(DisputeEvent.id)
            ).all()
        )


def test_only_one_of_four_simultaneous_closes_wins(payment, slow_record):
    """Each close read "still open" before any of them committed, so all four
    won: four contradictory closed events, and the last outcome silently
    replaced the first."""
    open_dispute(payment)
    outcomes = [
        "resolved_paid",
        "resolved_withdrawn",
        "resolved_informally",
        "resolved_paid",
    ]

    results = run_at_once(
        lambda s: disputes.close(
            s,
            disputes.get_for_payment(s, payment),
            outcome=outcomes.pop(),
            actor_role="brand",
            now=NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, DisputeAlreadyClosed)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert won == 1
    assert refused == AT_ONCE - 1
    events = closed_events(payment)
    assert [e.kind for e in events].count("closed") == 1


def test_nothing_is_added_to_a_dispute_after_it_closes(payment, slow_record):
    """An entry that read "still open" just before a close committed used to
    land after it, so the finished record grew a new entry."""
    open_dispute(payment)
    jobs = ["close", "entry", "entry", "entry"]

    def one(s):
        dispute = disputes.get_for_payment(s, payment)
        if jobs.pop() == "close":
            return disputes.close(
                s, dispute, outcome="resolved_paid", actor_role="brand", now=NOW
            )
        return disputes.add_entry(
            s,
            dispute,
            actor_role="creator",
            now=NOW,
            note="One more thing, on the record.",
        )

    results = run_at_once(one, AT_ONCE)

    _, _, unexpected = split(results, DisputeAlreadyClosed)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    # The deal record numbers every step in the order it committed, so it
    # is the referee: nothing may follow the close.
    with SessionLocal() as session:
        memo_id = session.get(PaymentStatus, payment).deal_memo_id
        kinds = list(
            session.scalars(
                select(DealRecordEntry.kind)
                .where(DealRecordEntry.deal_memo_id == memo_id)
                .order_by(DealRecordEntry.sequence)
            ).all()
        )
    after_close = kinds[kinds.index("dispute_closed") + 1 :]
    assert after_close == []


def test_entries_added_at_once_each_land_once_and_the_record_still_verifies(
    payment, slow_record
):
    """Both sides may add to an open dispute, so every one of these wins
    (audit C17, D-184). What must hold is the record: each entry sealed once,
    in an unbroken chain. Each locks the dispute and then the deal, as a
    close does, so none can claim a place in the chain another holds.

    Two locks guard this together, so removing either alone leaves it
    passing (seen, 11 November): the dispute's is proven by the close races
    above, the deal's by the batch racing an entry below."""
    open_dispute(payment)
    notes = [f"Entry {n}, on the record at the same moment." for n in range(AT_ONCE)]

    results = run_at_once(
        lambda s: disputes.add_entry(
            s,
            disputes.get_for_payment(s, payment),
            actor_role="creator",
            now=NOW,
            note=notes.pop(),
        ),
        AT_ONCE,
    )

    won, _, unexpected = split(results, DisputeAlreadyClosed)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert won == AT_ONCE
    with SessionLocal() as session:
        memo = session.get_one(
            DealMemo, session.get_one(PaymentStatus, payment).deal_memo_id
        )
        entries = deal_record.entries_for(session, memo.id)
        assert deal_record.verify(memo, entries).intact
    assert [e.kind for e in entries].count("dispute_entry_added") == AT_ONCE
    events = [e.kind for e in closed_events(payment)]
    assert events.count("evidence") == AT_ONCE


# --- marking many at once (audit C16, D-184) ---------------------------------------
#
# The bulk mark-paid locks every listed payment in one statement, in id order.
# Before, it locked them one row at a time in the order the brand listed them,
# so two batches listing the same deals in different orders each held a
# payment the other was waiting for: PostgreSQL broke the deadlock by failing
# one of them, a raw error and a 500.

BATCH = 3


@pytest.fixture
def batch() -> Iterator[tuple[uuid.UUID, list[uuid.UUID]]]:
    """One brand with BATCH approved, unpaid deals, each with its own creator,
    committed; removed again afterwards. Yields the brand and its memos."""
    with SessionLocal() as session:
        brand_account = create_account(session, "brand", phone=unique_phone())
        brand = build_brand(
            session,
            account_id=brand_account.id,
            email=f"batch-{uuid.uuid4().hex[:12]}@example.com",
        )
        session.add(brand)
        session.flush()
        campaign = build_campaign(session, status="open", brand_id=brand.id)
        session.add(campaign)
        session.flush()
        account_ids = [brand_account.id]
        creator_ids, application_ids, memos = [], [], []
        for _ in range(BATCH):
            creator_account = create_account(session, "creator", phone=unique_phone())
            account_ids.append(creator_account.id)
            creator = build_creator(
                session,
                handle=f"batch{uuid.uuid4().hex[:12]}",
                account_id=creator_account.id,
            )
            session.add(creator)
            session.flush()
            application = Application(
                campaign_id=campaign.id,
                creator_id=creator.id,
                pitch="I run a Salem food page, for a batch concurrency test.",
                status="accepted",
                status_changed_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
            session.add(application)
            session.flush()
            memo = DealMemo(
                application_id=application.id,
                deliverables="Three reels, for a batch concurrency test.",
                fee_amount_paise=800_000,
                status="accepted",
                created_at=NOW,
                updated_at=NOW,
            )
            session.add(memo)
            session.flush()
            creator_ids.append(creator.id)
            application_ids.append(application.id)
            memos.append(memo)
        session.commit()
        for memo in memos:
            payments.create_for_memo(session, memo, approved_on=APPROVED_ON, now=NOW)
        session.commit()
        memo_ids = [memo.id for memo in memos]
        brand_id, campaign_id = brand.id, campaign.id

    try:
        yield brand_id, memo_ids
    finally:
        with SessionLocal() as session:
            remove_deal_records(memo_ids)
            paid = select(PaymentStatus.id).where(
                PaymentStatus.deal_memo_id.in_(memo_ids)
            )
            session.execute(delete(Dispute).where(Dispute.payment_status_id.in_(paid)))
            session.execute(
                delete(PaymentStatus).where(PaymentStatus.deal_memo_id.in_(memo_ids))
            )
            session.execute(delete(DealMemo).where(DealMemo.id.in_(memo_ids)))
            session.execute(
                delete(Application).where(Application.id.in_(application_ids))
            )
            session.execute(delete(Campaign).where(Campaign.id == campaign_id))
            session.execute(delete(Creator).where(Creator.id.in_(creator_ids)))
            session.execute(delete(Brand).where(Brand.id == brand_id))
            session.execute(delete(Account).where(Account.id.in_(account_ids)))
            session.commit()


def mark_in_bulk(brand_id: uuid.UUID, memo_ids: list[uuid.UUID]) -> Callable[[Any], Any]:
    return lambda s: payments.mark_paid_in_bulk(
        s,
        brand_id,
        [payments.BulkMarkPaidRow(memo_id, "upi", RRN) for memo_id in memo_ids],
        now=NOW,
    )


def marked_entries(memo_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """How many `payment_marked_paid` entries each deal's record holds."""
    with SessionLocal() as session:
        kinds = session.execute(
            select(DealRecordEntry.deal_memo_id).where(
                DealRecordEntry.deal_memo_id.in_(memo_ids),
                DealRecordEntry.kind == "payment_marked_paid",
            )
        ).scalars()
        counted = dict.fromkeys(memo_ids, 0)
        for memo_id in kinds:
            counted[memo_id] += 1
        return counted


def test_two_batches_listing_the_same_deals_in_opposite_orders_never_deadlock(
    batch, slow_writes
):
    """Each payment is marked once, by whichever batch reached it first; the
    other batch's row for it is refused cleanly, and neither fails."""
    brand_id, memo_ids = batch
    jobs = [memo_ids, list(reversed(memo_ids))]

    results = run_at_once(lambda s: mark_in_bulk(brand_id, jobs.pop())(s), 2)

    errors = [r for r in results if isinstance(r, Exception)]
    assert errors == [], f"a raw database error reached the caller: {errors}"
    outcomes = [outcome for result in results for outcome in result]
    recorded = [o.memo_id for o in outcomes if o.payment is not None]
    refused = [o.refusal for o in outcomes if o.refusal is not None]
    assert sorted(recorded) == sorted(memo_ids)
    assert len(refused) == BATCH
    assert all(isinstance(r, PaymentAlreadyMarkedPaid) for r in refused)
    assert marked_entries(memo_ids) == dict.fromkeys(memo_ids, 1)


def test_a_batch_and_a_single_mark_at_once_mark_the_payment_once(batch, slow_writes):
    """The single path locks the payment, then its deal; the batch takes the
    same two in the same order, so they wait for each other, never deadlock."""
    brand_id, memo_ids = batch
    contested = memo_ids[-1]

    def single(s):
        payment = payments.get_for_memo(s, contested)
        return payments.mark_paid(s, payment, method="upi", reference=RRN, now=NOW)

    jobs = [("bulk", mark_in_bulk(brand_id, memo_ids)), ("single", single)]

    def tagged(s):  # which thread takes which job is the scheduler's choice
        name, job = jobs.pop()
        try:
            return name, job(s)
        except Exception as exc:  # collected and asserted below
            return name, exc

    results = dict(run_at_once(tagged, 2))

    bulk_result, single_result = results["bulk"], results["single"]
    single_lost = isinstance(single_result, PaymentAlreadyMarkedPaid)
    assert single_lost or not isinstance(single_result, Exception), single_result
    assert not isinstance(bulk_result, Exception), bulk_result
    bulk_won = {o.memo_id for o in bulk_result if o.payment is not None}
    # Exactly one of them marked the contested payment.
    assert (contested in bulk_won) == single_lost
    assert marked_entries(memo_ids) == dict.fromkeys(memo_ids, 1)


def test_a_batch_and_a_dispute_entry_on_one_deal_both_land_in_one_chain(
    batch, slow_writes
):
    """Both append to the deal's record. The entry locks the dispute and then
    the deal, and holds the deal while its write is held open; the batch,
    holding the payments, must wait for the deal before reading the record's
    last entry, or both would claim the same place in the chain."""
    brand_id, memo_ids = batch
    disputed = memo_ids[0]
    with SessionLocal() as session:
        payment_id = payments.get_for_memo(session, disputed).id
    open_dispute(payment_id)

    def entry(s):
        return disputes.add_entry(
            s,
            disputes.get_for_payment(s, payment_id),
            actor_role="creator",
            now=NOW,
            note="Said on the record while the batch runs.",
        )

    bulk_result, entry_result = run_staggered(
        (0.0, mark_in_bulk(brand_id, memo_ids)), (0.1, entry)
    )

    assert not isinstance(bulk_result, Exception), bulk_result
    assert not isinstance(entry_result, Exception), entry_result
    assert all(outcome.payment is not None for outcome in bulk_result)
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, disputed)
        entries = deal_record.entries_for(session, disputed)
        assert deal_record.verify(memo, entries).intact
    kinds = [e.kind for e in entries]
    assert kinds.count("payment_marked_paid") == 1
    assert kinds.count("dispute_entry_added") == 1

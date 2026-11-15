"""Two requests at once on one deal: never a 500, always one clear answer.

Review findings, PR #9: creating a memo and submitting proof both checked
"does one exist already?" and then wrote. Two requests together both passed
the check, the database's unique rule refused the second write, and the
error nobody caught reached the caller as a 500 instead of the conflict the
API documents.

Like the payment concurrency tests, these need separate, really-committing
connections, so they build their own rows and remove them afterwards. The
gap between each check and its write is held open on purpose, so the race
happens every run rather than by luck.
"""

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
from app.modules.campaigns.models import Application
from app.modules.deal_memo import proof_service
from app.modules.deal_memo import record_service as record
from app.modules.deal_memo import service as memos
from app.modules.deal_memo.deliverable_models import MemoDeliverable
from app.modules.deal_memo.exceptions import (
    MemoAlreadyExists,
    MemoNotEditable,
    MemoStatusConflict,
    PaidMemoNeedsFee,
    ProofAlreadyDecided,
)
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.record_models import DealRecordEntry
from tests.modules.payment_status.test_payment_concurrency import (
    AT_ONCE,
    run_at_once,
    run_staggered,
    split,
)

NOW = datetime(2026, 9, 21, 9, 0, tzinfo=UTC)
LINK = "https://www.instagram.com/reel/concurrency/"


def test_two_simultaneous_memos_for_one_application_give_one_memo_and_conflicts(
    committed_application, monkeypatch
):
    original = memos._campaign_of

    def slow(*args, **kwargs):  # between the existence check and the write
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(memos, "_campaign_of", slow)

    results = run_at_once(
        lambda s: memos.create_memo(
            s,
            s.get(Application, committed_application),
            {"deliverables": "Three reels.", "fee_amount_paise": 800_000},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, MemoAlreadyExists)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)


def test_two_simultaneous_proof_submissions_give_one_proof_and_conflicts(
    committed_memo, monkeypatch
):
    original = proof_service.record.append

    def slow(*args, **kwargs):  # between the open-submission check and the commit
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(proof_service.record, "append", slow)

    results = run_at_once(
        lambda s: proof_service.submit_proof(
            s,
            s.get(DealMemo, committed_memo),
            {"content_url": LINK, "format": "reel"},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, ProofAlreadyDecided)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)


# --- terms against a send, and the creator's answers (audit C13, D-184) -----------
#
# Each "only if" here is checked after locking the memo (backend.md section
# 5). `slow_writes` holds every flush open, and the jobs start in a fixed
# order, so without the lock the bad interleaving is the one that happens,
# every run, not one that might.

DUE_ON = date(2026, 10, 15)
NEW_FEE = 950_000
NEW_ITEMS = [{"platform": "instagram", "format": "reel", "quantity": 2, "note": None}]


@pytest.fixture
def draft_memo(committed_application) -> Iterator[uuid.UUID]:
    """A committed draft memo on a paid campaign, due well after NOW."""
    with SessionLocal() as session:
        memo = DealMemo(
            application_id=committed_application,
            deliverables="Three reels, for a concurrency test.",
            fee_amount_paise=800_000,
            content_due_on=DUE_ON,
            status="draft",
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(memo)
        session.commit()
        memo_id = memo.id
    try:
        yield memo_id
    finally:
        # Deliverables hold their memo by RESTRICT; the application's own
        # cleanup removes the memo and its record after this.
        with SessionLocal() as session:
            session.execute(
                delete(MemoDeliverable).where(MemoDeliverable.deal_memo_id == memo_id)
            )
            session.commit()


@pytest.fixture
def sent_memo(draft_memo) -> uuid.UUID:
    with SessionLocal() as session:
        memos.change_status(
            session, session.get_one(DealMemo, draft_memo), "sent", NOW, actor="brand"
        )
    return draft_memo


def memo_entries(memo_id: uuid.UUID) -> list[DealRecordEntry]:
    with SessionLocal() as session:
        return record.entries_for(session, memo_id)


def edit(memo_id: uuid.UUID) -> Callable[[Session], Any]:
    return lambda s: memos.update_memo(
        s,
        s.get_one(DealMemo, memo_id),
        {"fee_amount_paise": NEW_FEE, "deliverable_items": list(NEW_ITEMS)},
        NOW,
    )


def move(memo_id: uuid.UUID, status: str, actor: str) -> Callable[[Session], Any]:
    message = "Make it two reels." if status == "change_requested" else None
    return lambda s: memos.change_status(
        s, s.get_one(DealMemo, memo_id), status, NOW, actor=actor, message=message
    )


@pytest.mark.parametrize("first", ["send", "edit"])
def test_an_edit_racing_the_send_never_lands_on_terms_the_record_did_not_seal(
    draft_memo, slow_writes, first
):
    """Bait and switch (legal.md section 3.5). Read unlocked, an edit that
    started after the send passed its check on the draft, waited for the
    send's lock, then wrote a new fee onto the sent memo; and a send that
    read the memo before an edit committed sealed the fee the edit replaced.
    Either way the creator could accept terms the record never sealed at
    sending. Now it is edit then send, or send then the edit refused (409).

    The stagger stages the bad interleaving; the assertions hold for either
    order, so a slow machine that lets the later job win the lock first
    proves the same rule rather than failing for the wrong reason."""
    later = 0.1
    send_job = move(draft_memo, "sent", "brand")
    edit_job = edit(draft_memo)
    if first == "send":
        sent, edited = run_staggered((0.0, send_job), (later, edit_job))
    else:
        sent, edited = run_staggered((later, send_job), (0.0, edit_job))

    assert not isinstance(sent, Exception), f"the send failed: {sent!r}"
    # The edit landed before the send, or found the memo sent: nothing else.
    edit_landed = not isinstance(edited, Exception)
    assert edit_landed or isinstance(edited, MemoNotEditable), repr(edited)
    expected_fee = NEW_FEE if edit_landed else 800_000
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, draft_memo)
        assert memo.status == "sent"
        assert memo.fee_amount_paise == expected_fee
        terms_now = record.terms_fingerprint(memo)
    sealed = [e for e in memo_entries(draft_memo) if e.kind == "memo_sent"]
    assert len(sealed) == 1
    # What the creator was sent is exactly what the record sealed at sending.
    assert sealed[0].facts["fee_amount_paise"] == expected_fee
    assert sealed[0].facts["terms_sha256"] == terms_now


def test_of_four_accepts_at_once_exactly_one_wins(sent_memo, slow_writes):
    results = run_at_once(move(sent_memo, "accepted", "creator"), AT_ONCE)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    assert [e.kind for e in memo_entries(sent_memo)] == ["memo_sent", "memo_accepted"]


def test_the_creator_s_three_answers_at_once_leave_one(sent_memo, slow_writes):
    """Accept, ask for a change, decline: one answer stands, and its marks
    alone are on the memo, never a mix of two."""
    jobs = ["accepted", "change_requested", "declined", "accepted"]

    results = run_at_once(lambda s: move(sent_memo, jobs.pop(), "creator")(s), AT_ONCE)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    answers = [e.kind for e in memo_entries(sent_memo)][1:]
    assert len(answers) == 1
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, sent_memo)
        assert f"memo_{memo.status}" == answers[0]
        # A lost update would count two requests, or accept a questioned memo.
        assert memo.revision_count == (1 if memo.status == "change_requested" else 0)
        assert (memo.accepted_at is not None) == (memo.status == "accepted")
        assert (memo.declined_at is not None) == (memo.status == "declined")


def test_of_four_sends_of_one_draft_at_once_exactly_one_wins(draft_memo, slow_writes):
    """One send, sealed once: a second would seal the same terms again and
    tell the creator twice."""
    results = run_at_once(move(draft_memo, "sent", "brand"), AT_ONCE)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    assert [e.kind for e in memo_entries(draft_memo)] == ["memo_sent"]


def test_both_sides_cancelling_an_accepted_memo_at_once_cancel_it_once(
    sent_memo, slow_writes
):
    """Either side may cancel an accepted memo; only the first cancellation
    happened, and the record says so once."""
    with SessionLocal() as session:
        memos.change_status(
            session,
            session.get_one(DealMemo, sent_memo),
            "accepted",
            NOW,
            actor="creator",
        )
    jobs = [("cancelled", "brand"), ("cancelled", "creator")] * (AT_ONCE // 2)

    results = run_at_once(lambda s: move(sent_memo, *jobs.pop())(s), AT_ONCE)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert (won, refused) == (1, AT_ONCE - 1)
    cancels = [e for e in memo_entries(sent_memo) if e.kind == "memo_cancelled"]
    assert len(cancels) == 1
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, sent_memo)
        assert memo.status == "cancelled"
        # Nothing was submitted, so it cost nothing, whoever cancelled (D-026).
        assert memo.cancellation_kind == "withdrawn_early"
        assert cancels[0].facts == {"cancellation_kind": "withdrawn_early"}


def test_an_accept_and_a_cancel_at_once_leave_a_sequence_the_rules_allow(
    sent_memo, slow_writes
):
    """A brand may cancel a sent memo and an accepted one, so both may win,
    but only in that order: accepted, then cancelled. A cancelled memo is
    never accepted, and the record says exactly what happened."""
    jobs = [
        ("accepted", "creator"),
        ("cancelled", "brand"),
        ("accepted", "creator"),
        ("cancelled", "brand"),
    ]

    results = run_at_once(lambda s: move(sent_memo, *jobs.pop())(s), AT_ONCE)

    won, refused, unexpected = split(results, MemoStatusConflict)
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    answers = [e.kind for e in memo_entries(sent_memo)][1:]
    assert answers in (["memo_cancelled"], ["memo_accepted", "memo_cancelled"])
    assert (won, refused) == (len(answers), AT_ONCE - len(answers))
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, sent_memo)
        assert memo.status == "cancelled"
        assert (memo.accepted_at is not None) == ("memo_accepted" in answers)
        # No work was submitted, so the cancellation cost nothing (D-026).
        assert memo.cancellation_kind == "withdrawn_early"


@pytest.fixture
def change_requested_memo(sent_memo) -> uuid.UUID:
    """A sent memo the creator asked to change: the brand's to edit and send again."""
    with SessionLocal() as session:
        move(sent_memo, "change_requested", "creator")(session)
    return sent_memo


def test_four_re_sends_and_an_edit_at_once_seal_the_terms_once(
    change_requested_memo, slow_writes
):
    """The re-send after a change request (audit C13, D-184, the independent
    review of 12 November): four sends and an edit at once. One send wins
    and is sealed once; the edit lands before it, and is sealed with it, or
    finds the memo sent and is refused. Never two sends on the record, and
    never terms on the memo that the last send did not seal."""
    jobs = [edit(change_requested_memo)] + [
        move(change_requested_memo, "sent", "brand")
    ] * AT_ONCE

    results = run_at_once(lambda s: jobs.pop()(s), AT_ONCE + 1)

    lost_sends = [r for r in results if isinstance(r, MemoStatusConflict)]
    refused_edits = [r for r in results if isinstance(r, MemoNotEditable)]
    unexpected = [
        r
        for r in results
        if isinstance(r, Exception)
        and not isinstance(r, (MemoStatusConflict, MemoNotEditable))
    ]
    assert unexpected == [], f"a raw error reached the caller: {unexpected}"
    assert len(lost_sends) == AT_ONCE - 1
    assert len(refused_edits) in (0, 1)
    edit_landed = not refused_edits
    entries = memo_entries(change_requested_memo)
    assert [e.kind for e in entries] == [
        "memo_sent",
        "memo_change_requested",
        "memo_sent",
    ]
    with SessionLocal() as session:
        memo = session.get_one(DealMemo, change_requested_memo)
        assert memo.status == "sent"
        assert memo.fee_amount_paise == (NEW_FEE if edit_landed else 800_000)
        terms_now = record.terms_fingerprint(memo)
    # What the creator was sent again is exactly what the record sealed.
    assert entries[-1].facts["fee_amount_paise"] == memo.fee_amount_paise
    assert entries[-1].facts["terms_sha256"] == terms_now


def deliverables_of(quantity: int) -> list[dict[str, Any]]:
    """Two deliverables, both of `quantity`, so a mix of two edits shows."""
    return [
        {"platform": "instagram", "format": "reel", "quantity": quantity, "note": None},
        {
            "platform": "instagram",
            "format": "reel",
            "quantity": quantity,
            "note": "Second",
        },
    ]


def test_four_edits_replacing_the_deliverables_at_once_never_collide(
    draft_memo, slow_writes
):
    """The independent review of 12 November (D-184). Each edit deletes the
    memo's deliverables and inserts its own from place 0. Unlocked, under
    READ COMMITTED, four at once each deleted what it saw and inserted place
    0, and every edit after the first hit `uq_memo_deliverable_place`: a raw
    database error, a 500 through the API. The memo's lock in `update_memo`
    queues them: every edit lands, one after another, and the list left is
    one edit's whole list, never a mix.

    Only the deliverables change: a fee in the same edit would lock the
    memo's row by its UPDATE first, and hide the race this test is for."""
    quantities = list(range(1, AT_ONCE + 1))

    results = run_at_once(
        lambda s: memos.update_memo(
            s,
            s.get_one(DealMemo, draft_memo),
            {"deliverable_items": deliverables_of(quantities.pop())},
            NOW,
        ),
        AT_ONCE,
    )

    won, refused, unexpected = split(results, MemoNotEditable)
    assert unexpected == [], f"a raw database error reached the caller: {unexpected}"
    # A draft stays editable, so every edit wins in turn.
    assert (won, refused) == (AT_ONCE, 0)
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(MemoDeliverable)
                .where(MemoDeliverable.deal_memo_id == draft_memo)
                .order_by(MemoDeliverable.position)
            )
        )
    assert [row.position for row in rows] == [0, 1]
    assert len({row.quantity for row in rows}) == 1
    assert [row.note for row in rows] == [None, "Second"]


def test_a_refused_fee_lets_go_of_the_memo_at_once(draft_memo):
    """A paid memo's edit that clears the fee is refused while it holds the
    memo's lock. It rolls back before raising, as every other refusal in
    the service does (the independent review of 12 November, D-184), so
    the lock goes with the refusal, not when the session is finally closed:
    another request can take the memo straight away."""
    with SessionLocal() as editing:
        with pytest.raises(PaidMemoNeedsFee):
            memos.update_memo(
                editing,
                editing.get_one(DealMemo, draft_memo),
                {"fee_amount_paise": None},
                NOW,
            )
        # The refused session is still open, as a request's is while its
        # error is answered. NOWAIT fails at once if the lock is still held.
        with SessionLocal() as other:
            locked = other.scalars(
                select(DealMemo.id)
                .where(DealMemo.id == draft_memo)
                .with_for_update(nowait=True)
            ).one()
            other.rollback()
    assert locked == draft_memo

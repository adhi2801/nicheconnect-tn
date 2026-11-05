"""Where a deal stands, and whose move it is: every rule, without a database (D-076)."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.deal_memo.draft_models import ContentDraft
from app.modules.deal_memo.draft_rules import delivery_due_on
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.stage import (
    DEAL_STAGES,
    MAIN_STAGES,
    DealStage,
    stage_of,
)
from app.modules.payment_status.models import PaymentStatus

NOW = datetime(2026, 10, 4, 9, 0, tzinfo=UTC)


def memo(
    status: str = "accepted", *, fee: int | None = 800_000, **fields: object
) -> DealMemo:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "status": status,
        "fee_amount_paise": fee,
        "approval_window_days": 7,
        "payment_due_days": 7,
        "work_started_at": None,
    }
    values.update(fields)
    return DealMemo(**values)


def proof(status: str, *, days_ago: float = 1) -> DeliverableProof:
    return DeliverableProof(
        id=uuid.uuid4(), status=status, created_at=NOW - timedelta(days=days_ago)
    )


def payment(*, marked: bool = False, confirmed: bool = False) -> PaymentStatus:
    return PaymentStatus(
        id=uuid.uuid4(),
        amount_paise=800_000,
        due_on=date(2026, 10, 11),
        marked_paid_at=NOW if marked or confirmed else None,
        confirmed_at=NOW if confirmed else None,
    )


def at(stage: str, waiting_on: str | None) -> DealStage:
    return DealStage(stage, waiting_on, has_open_dispute=False)


# --- before the deal is agreed ---------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("draft", at("draft", "brand")),
        ("sent", at("memo_sent", "creator")),
        ("change_requested", at("memo_sent", "brand")),
        ("declined", at("declined", None)),
        ("cancelled", at("cancelled", None)),
    ],
)
def test_a_memo_not_yet_agreed_stands_where_its_status_says(status, expected):
    assert stage_of(memo(status), [], None, NOW) == expected


# --- the work ------------------------------------------------------------------------------


def test_agreed_and_nothing_started_waits_on_the_creator():
    assert stage_of(memo(), [], None, NOW) == at("agreed", "creator")


def test_work_started_is_in_progress():
    started = memo(work_started_at=NOW - timedelta(days=2))

    assert stage_of(started, [], None, NOW) == at("in_progress", "creator")


def test_work_sent_for_review_waits_on_the_brand():
    assert stage_of(memo(), [proof("submitted")], None, NOW) == at("in_progress", "brand")


def test_changes_asked_for_wait_on_the_creator():
    history = [proof("revision_requested", days_ago=3)]

    assert stage_of(memo(), history, None, NOW) == at("in_progress", "creator")


def test_a_resubmission_waits_on_the_brand_again():
    history = [proof("revision_requested", days_ago=3), proof("submitted", days_ago=1)]

    assert stage_of(memo(), history, None, NOW) == at("in_progress", "brand")


def test_work_the_clock_approved_is_at_payment_before_anyone_looks():
    """D-025: the row still says submitted, but the window ran out."""
    unreviewed = [proof("submitted", days_ago=10)]

    assert stage_of(memo(), unreviewed, None, NOW) == at("payment", "brand")


# --- the money -----------------------------------------------------------------------------


def test_approved_work_with_no_payment_said_waits_on_the_brand():
    assert stage_of(memo(), [proof("approved")], None, NOW) == at("payment", "brand")


def test_money_said_to_be_sent_waits_on_the_creator_to_confirm():
    found = stage_of(memo(), [proof("approved")], payment(marked=True), NOW)

    assert found == at("payment", "creator")


def test_a_paid_deal_finishes_only_when_the_creator_confirms():
    found = stage_of(memo(), [proof("approved")], payment(confirmed=True), NOW)

    assert found == at("finished", None)


@pytest.mark.parametrize(
    "history", [[proof("approved")], [proof("submitted", days_ago=10)]]
)
def test_a_barter_deal_finishes_when_its_work_is_approved(history):
    assert stage_of(memo(fee=None), history, None, NOW) == at("finished", None)


def test_an_open_dispute_is_carried_through():
    found = stage_of(
        memo(), [proof("approved")], payment(marked=True), NOW, has_open_dispute=True
    )

    assert found == DealStage("payment", "creator", has_open_dispute=True)


# --- the set of stages ---------------------------------------------------------------------


def test_the_main_stages_are_in_order_and_all_known():
    # Draft review only on a deal agreed with one (item 27).
    assert MAIN_STAGES == (
        "memo_sent",
        "agreed",
        "draft_review",
        "in_progress",
        "payment",
        "finished",
    )
    assert set(MAIN_STAGES) <= set(DEAL_STAGES)


def test_an_ended_deal_waits_on_nobody():
    ended = [
        stage_of(memo("declined"), [], None, NOW),
        stage_of(memo("cancelled"), [], None, NOW),
        stage_of(memo(), [proof("approved")], payment(confirmed=True), NOW),
    ]

    assert all(found.waiting_on is None for found in ended)


# --- the due date, money owed on a cancelled deal, and the draft review (item 27) ---------
# Each rule below was reached only through the API until the nightly mutation
# run found 19 changes to stage_of that no test of it noticed (item 93).

DUE = date(2026, 10, 20)


def draft(status: str, *, days_ago: float = 2) -> ContentDraft:
    """A draft the database would accept: an answered one carries its answer's moment."""
    shown = NOW - timedelta(days=days_ago)
    answered = status != "submitted"
    return ContentDraft(
        id=uuid.uuid4(),
        round=1,
        body="The caption.",
        status=status,
        created_at=shown,
        images_ready_at=shown,
        approved_at=shown + timedelta(hours=3) if status == "approved" else None,
        answered_at=shown + timedelta(hours=3) if answered else None,
        changes_note="Add the ad label." if status == "changes_requested" else None,
        auto_approved=False,
    )


@pytest.mark.parametrize("status", ["draft", "sent", "declined", "cancelled", "accepted"])
def test_every_stage_carries_the_date_the_work_is_due(status):
    assert stage_of(memo(status, content_due_on=DUE), [], None, NOW).work_due_on == DUE


def test_the_due_date_moves_by_the_days_the_brand_held_a_draft_in_time():
    reviewed = memo(content_due_on=DUE, draft_review=True)
    drafts = [draft("approved")]

    found = stage_of(reviewed, [], None, NOW, drafts=drafts)

    assert found.work_due_on == delivery_due_on(reviewed, drafts, NOW)
    assert found.work_due_on > DUE


@pytest.mark.parametrize(
    ("fee", "paid", "owed"),
    [
        (800_000, None, True),
        (800_000, "marked", True),
        (800_000, "confirmed", False),
        (None, None, False),
    ],
)
def test_a_deal_cancelled_after_approved_work_still_owes_its_fee_until_confirmed(
    fee, paid, owed
):
    found = stage_of(
        memo("cancelled", fee=fee),
        [proof("approved")],
        None if paid is None else payment(marked=True, confirmed=paid == "confirmed"),
        NOW,
    )

    assert (found.stage, found.money_owed) == ("cancelled", owed)


def test_a_deal_cancelled_before_any_approved_work_owes_nothing():
    assert (
        stage_of(memo("cancelled"), [proof("submitted")], None, NOW).money_owed is False
    )


def test_a_submitted_draft_waits_on_the_brand_and_an_approved_one_moves_the_deal_on():
    reviewed = memo(content_due_on=DUE, draft_review=True)

    waiting = stage_of(reviewed, [], None, NOW, drafts=[draft("submitted", days_ago=0.1)])
    changes = stage_of(reviewed, [], None, NOW, drafts=[draft("changes_requested")])
    approved = stage_of(reviewed, [], None, NOW, drafts=[draft("approved")])

    assert (waiting.stage, waiting.waiting_on) == ("draft_review", "brand")
    assert (changes.stage, changes.waiting_on) == ("draft_review", "creator")
    assert (approved.stage, approved.waiting_on) == ("agreed", "creator")


def test_a_deal_agreed_with_a_draft_review_and_no_draft_yet_waits_on_the_creator():
    reviewed = memo(content_due_on=DUE, draft_review=True)

    found = stage_of(reviewed, [], None, NOW, drafts=[])

    assert (found.stage, found.waiting_on) == ("agreed", "creator")


def test_the_newest_draft_decides_whose_move_it_is_in_whatever_order_drafts_come():
    reviewed = memo(content_due_on=DUE, draft_review=True)
    older = draft("changes_requested", days_ago=3)
    newer = draft("submitted", days_ago=0.1)

    for drafts in ([older, newer], [newer, older]):
        found = stage_of(reviewed, [], None, NOW, drafts=drafts)
        assert (found.stage, found.waiting_on) == ("draft_review", "brand")
    reworked = draft("changes_requested", days_ago=0.5)
    found = stage_of(
        reviewed, [], None, NOW, drafts=[reworked, draft("submitted", days_ago=3)]
    )
    assert (found.stage, found.waiting_on) == ("draft_review", "creator")

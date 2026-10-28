"""The approval clock and a deal's stage, for any history (D-025, D-076, D-090).

The approval clock decides when a payment falls due, and the stage decides
what every screen shows. These try any submission time, any window, and any
mix of memo status, submissions and payment.
"""

import uuid
from datetime import UTC, datetime, time, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import IST, india_date
from app.modules.deal_memo.models import MAX_WINDOW_DAYS, MEMO_STATUSES, DealMemo
from app.modules.deal_memo.proof_models import PROOF_STATUSES, DeliverableProof
from app.modules.deal_memo.review_clock import approval_deadline
from app.modules.deal_memo.stage import DEAL_STAGES, ENDED, FINISHED, PAYMENT, stage_of
from app.modules.payment_status.models import PaymentStatus

START = datetime(2026, 9, 1, tzinfo=UTC)
moments = st.integers(min_value=0, max_value=200 * 24 * 60).map(
    lambda minutes: START + timedelta(minutes=minutes)
)
windows = st.integers(min_value=1, max_value=MAX_WINDOW_DAYS)


def memo(status="accepted", window=7, fee=800_000) -> DealMemo:
    return DealMemo(
        id=uuid.uuid4(),
        status=status,
        approval_window_days=window,
        payment_due_days=7,
        fee_amount_paise=fee,
        deliverables="2 reels.",
    )


def proof(at: datetime, status="submitted") -> DeliverableProof:
    return DeliverableProof(
        id=uuid.uuid4(), created_at=at, status=status, format="reel", approved_at=None
    )


# --- the approval clock ------------------------------------------------------------------


@given(at=moments, window=windows)
def test_the_deadline_is_always_midnight_in_tamil_nadu(at, window):
    first = proof(at)
    deadline = approval_deadline(memo(window=window), first, [first])

    assert deadline.astimezone(IST).time() == time(0, 0)


@given(at=moments, window=windows)
def test_the_brand_gets_every_whole_day_of_its_window(at, window):
    first = proof(at)
    deadline = approval_deadline(memo(window=window), first, [first])

    assert timedelta(days=window) < deadline - at <= timedelta(days=window + 1)


@given(day=moments, early=st.integers(0, 24 * 60 - 1), late=st.integers(0, 24 * 60 - 1))
def test_two_submissions_on_one_tamil_nadu_day_share_a_deadline(day, early, late):
    midnight = datetime.combine(india_date(day), time(0, 0), tzinfo=IST)
    a = proof(midnight + timedelta(minutes=early))
    b = proof(midnight + timedelta(minutes=late))
    terms = memo()

    assert approval_deadline(terms, a, [a]) == approval_deadline(terms, b, [b])


@given(first=moments, gaps=st.lists(st.integers(1, 20 * 24 * 60), min_size=2, max_size=5))
def test_asking_again_never_buys_the_brand_more_time(first, gaps):
    """Only the first request for changes restarts the clock (D-025)."""
    times = [first]
    for gap in gaps:
        times.append(times[-1] + timedelta(minutes=gap))
    history = [proof(at) for at in times]
    terms = memo()

    second, later = history[1], history[2:]
    for resubmission in later:
        assert approval_deadline(terms, resubmission, history) == approval_deadline(
            terms, second, history
        )


# --- the stage ---------------------------------------------------------------------------


@st.composite
def deals(draw):
    status = draw(st.sampled_from(MEMO_STATUSES))
    fee = draw(st.sampled_from([None, 800_000]))
    times = sorted(draw(st.lists(moments, max_size=4)))
    proofs = [proof(at, draw(st.sampled_from(PROOF_STATUSES))) for at in times]
    for found in proofs:
        if found.status == "approved":
            found.approved_at = found.created_at
    kind = draw(st.sampled_from(["none", "open", "marked", "confirmed"]))
    payment = None
    if fee and kind != "none":
        marked = START + timedelta(days=210) if kind != "open" else None
        payment = PaymentStatus(
            amount_paise=fee,
            due_on=START.date(),
            marked_paid_at=marked,
            confirmed_at=marked if kind == "confirmed" else None,
        )
    terms = memo(status=status, fee=fee)
    if status == "cancelled":
        terms.cancellation_kind = "withdrawn_early"
    return terms, proofs, payment, draw(moments)


@given(deals(), st.booleans())
def test_nobody_owes_an_ended_deal_anything_and_someone_owes_every_other(deal, dispute):
    terms, proofs, payment, now = deal
    found = stage_of(terms, proofs, payment, now, has_open_dispute=dispute)

    assert found.stage in DEAL_STAGES
    assert (found.waiting_on is None) == (found.stage in ENDED)
    assert found.has_open_dispute is dispute


@given(deals())
def test_a_barter_deal_never_waits_on_a_payment(deal):
    terms, proofs, _, now = deal
    terms.fee_amount_paise = None

    assert stage_of(terms, proofs, None, now).stage != PAYMENT


@given(deals())
def test_a_paid_deal_finishes_only_when_the_creator_confirms(deal):
    terms, proofs, payment, now = deal
    found = stage_of(terms, proofs, payment, now)

    if found.stage == FINISHED and terms.fee_amount_paise:
        assert payment is not None and payment.confirmed_at is not None

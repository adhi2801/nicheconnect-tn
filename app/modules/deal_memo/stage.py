"""Where a deal stands, and whose move it is (D-076).

The website's deal pass and campaign board show every deal as one of five
stages, Memo sent, Agreed, In progress, Payment, Finished, with the side
whose move it is. Without this the screen would read the memo, its proof
and its payment and work the stage out itself, once per card, and the web
and both apps would each be free to work it out differently.

A stage is never stored. It is worked out from the memo, its proof and its
payment as of `now`, with the same rules the rest of the backend uses:

- approval counts the clock (D-025), through `is_approved`, so a deal whose
  review window ran out is at Payment even before anybody reads its proof;
- a barter deal has no payment, so it is Finished once its work is approved
  (D-026);
- a paid deal is Finished only when the creator confirms the money arrived,
  never when the brand says it sent it (D-027).

`draft`, `declined` and `cancelled` sit outside the five: a draft has not
started, and the other two ended without finishing.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.modules.deal_memo.delivery_record import is_approved
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.disputes import service as disputes
from app.modules.payment_status.models import PaymentStatus

DRAFT = "draft"
MEMO_SENT = "memo_sent"
AGREED = "agreed"
IN_PROGRESS = "in_progress"
PAYMENT = "payment"
FINISHED = "finished"
DECLINED = "declined"
CANCELLED = "cancelled"
DEAL_STAGES: tuple[str, ...] = (
    DRAFT,
    MEMO_SENT,
    AGREED,
    IN_PROGRESS,
    PAYMENT,
    FINISHED,
    DECLINED,
    CANCELLED,
)
# The five a deal passes through on the way to done, in order.
MAIN_STAGES: tuple[str, ...] = (MEMO_SENT, AGREED, IN_PROGRESS, PAYMENT, FINISHED)
# Nothing more will happen to a deal at one of these.
ENDED: frozenset[str] = frozenset({FINISHED, DECLINED, CANCELLED})

BRAND = "brand"
CREATOR = "creator"
DEAL_SIDES: tuple[str, ...] = (BRAND, CREATOR)


@dataclass(frozen=True)
class DealStage:
    stage: str
    # The side whose move it is, or None when nobody owes the deal anything.
    waiting_on: str | None
    has_open_dispute: bool


def _latest(proofs: list[DeliverableProof]) -> DeliverableProof | None:
    return max(proofs, key=lambda proof: (proof.created_at, proof.id), default=None)


def stage_of(
    memo: DealMemo,
    proofs: list[DeliverableProof],
    payment: PaymentStatus | None,
    now: datetime,
    *,
    has_open_dispute: bool = False,
) -> DealStage:
    """The stage of one deal as of `now`. Pure: everything is passed in."""

    def at(stage: str, waiting_on: str | None) -> DealStage:
        return DealStage(stage, waiting_on, has_open_dispute)

    if memo.status == "draft":
        return at(DRAFT, BRAND)
    if memo.status == "sent":
        return at(MEMO_SENT, CREATOR)
    if memo.status == "change_requested":
        return at(MEMO_SENT, BRAND)
    if memo.status == "declined":
        return at(DECLINED, None)
    if memo.status == "cancelled":
        return at(CANCELLED, None)

    # Accepted from here on.
    if any(is_approved(memo, proof, proofs, now) for proof in proofs):
        if not memo.fee_amount_paise:
            return at(FINISHED, None)  # barter: nothing to pay (D-026)
        if payment is not None and payment.confirmed_at is not None:
            return at(FINISHED, None)
        if payment is not None and payment.marked_paid_at is not None:
            return at(PAYMENT, CREATOR)  # said to be sent; is it there?
        return at(PAYMENT, BRAND)

    latest = _latest(proofs)
    if latest is not None and latest.status == "submitted":
        return at(IN_PROGRESS, BRAND)  # inside the review window
    if latest is not None or memo.work_started_at is not None:
        return at(IN_PROGRESS, CREATOR)  # making it, or making the change
    return at(AGREED, CREATOR)


def stages_for(
    db: Session, memos: list[DealMemo], now: datetime
) -> dict[uuid.UUID, DealStage]:
    """The stage of every memo given, in three queries whatever their number."""
    ids = [memo.id for memo in memos]
    if not ids:
        return {}
    proofs: dict[uuid.UUID, list[DeliverableProof]] = defaultdict(list)
    for proof in db.scalars(
        select(DeliverableProof).where(DeliverableProof.deal_memo_id.in_(ids))
    ):
        proofs[proof.deal_memo_id].append(proof)
    payments = {
        payment.deal_memo_id: payment
        for payment in db.scalars(
            select(PaymentStatus).where(PaymentStatus.deal_memo_id.in_(ids))
        )
    }
    disputed = disputes.open_payment_ids(
        db, {payment.id for payment in payments.values()}, india_date(now)
    )
    return {
        memo.id: stage_of(
            memo,
            proofs[memo.id],
            payments.get(memo.id),
            now,
            has_open_dispute=(memo.id in payments and payments[memo.id].id in disputed),
        )
        for memo in memos
    }

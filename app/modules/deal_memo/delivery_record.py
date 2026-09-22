"""A creator's delivery record: did they deliver, on time, as they said?

The mirror of a brand's payment record (D-034), built to the same three
rules, for the same reasons (D-038):

1. **Silence must not launder a bad record.** A creator who accepts a deal
   and then simply never delivers is the least likely person to report it,
   and a brand that was let down usually just leaves. So once the agreed
   date is 14 days past with nothing delivered, the deal counts as not
   delivered whether or not anybody complained: the calendar reports it.
2. **"New" must not be a hiding place.** `currently_overdue` is reported
   always, below the three-deal floor as well as above it.
3. **Nothing is smoothed.** The counts travel with the figures, and below
   three completed deals the figures are withheld rather than dressed up.

Only what the creator did is counted. A cancellation by the brand, a
cancellation before any work was submitted (`withdrawn_early`, D-026), and
the brand asking for changes are not the creator's failures and are left
out. Barter is never scored (D-026): its outcomes are shown as their own
counts, so a free-product trial that fell through is not weighed like a
broken paid deal, and a creator cannot hide behind barter either.

Every date is read on Tamil Nadu's calendar (D-030 point 1).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.proof_models import DeliverableProof
from app.modules.deal_memo.proof_service import approval_deadline

# Below this, the figures are withheld (the same floor as D-027).
MIN_DEALS_FOR_HISTORY = 3
# How long past the agreed date before silence counts as not delivering.
# The same 14 days a brand gets before a late payment becomes unpaid (D-027).
NOT_DELIVERED_AFTER_DUE_DAYS = 14

NO_HISTORY_YET = "new_creator_no_history_yet"
HAS_HISTORY = "has_delivery_history"


class Outcome(StrEnum):
    """Where one accepted deal stands, from the creator's side."""

    DELIVERED = "delivered"
    NOT_DELIVERED = "not_delivered"
    # Past the agreed date with nothing delivered, but inside the 14 days.
    OVERDUE = "overdue"
    IN_PROGRESS = "in_progress"
    # Not the creator's doing: withdrawn before work, or cancelled by the brand.
    NOT_COUNTED = "not_counted"


@dataclass(frozen=True)
class DeliveryRecord:
    """What we can honestly say about how a creator delivers."""

    creator_id: uuid.UUID
    status: str
    # Scored deals (not barter) that reached an outcome. The denominator.
    deals_completed: int
    deals_delivered: int
    # Walked away after starting, or silent 14 days past the agreed date.
    deals_not_delivered: int
    # Owed right now and past its date. Always reported.
    currently_overdue: int
    # Withheld below the floor: None means "not enough to say", never zero.
    delivered_on_time_share: float | None
    # Of delivered deals that required an ad disclosure, the share where the
    # creator confirmed it was on the post. Their statement, not our judgement
    # of compliance (D-024). None below the floor, or if none required one.
    disclosure_confirmed_share: float | None
    # Barter, shown and never scored (D-026).
    barter_deals_delivered: int
    barter_deals_not_delivered: int


def is_approved(memo: DealMemo, proof: DeliverableProof, now: datetime) -> bool:
    """Approved, including by the clock (D-025).

    Auto-approval is written lazily, when somebody next reads the proof, so a
    submission whose window has passed is approved here even if the row
    still says `submitted`. Otherwise the record would depend on whether
    anyone happened to look.
    """
    if proof.status == "approved":
        return True
    return proof.status == "submitted" and now >= approval_deadline(memo, proof)


def classify(memo: DealMemo, proofs: list[DeliverableProof], now: datetime) -> Outcome:
    """Where this accepted deal stands for the creator, as of `now`."""
    if memo.status == "cancelled":
        if memo.cancellation_kind == "cancelled_by_creator":
            return Outcome.NOT_DELIVERED
        return Outcome.NOT_COUNTED

    if any(is_approved(memo, proof, now) for proof in proofs):
        return Outcome.DELIVERED
    if any(proof.status == "submitted" for proof in proofs):
        # Waiting on the brand's review, not on the creator.
        return Outcome.IN_PROGRESS

    today = india_date(now)
    due_on = memo.content_due_on
    if due_on is None or today <= due_on:
        return Outcome.IN_PROGRESS
    if today >= due_on + timedelta(days=NOT_DELIVERED_AFTER_DUE_DAYS):
        return Outcome.NOT_DELIVERED
    return Outcome.OVERDUE


def _on_time(memo: DealMemo, proofs: list[DeliverableProof]) -> bool:
    """Delivered by the agreed date, judged by when the creator first submitted.

    The brand's review time is the brand's, not the creator's. A deal with
    no agreed date cannot have been late. Only called for delivered deals,
    which always have at least one submission.
    """
    if memo.content_due_on is None:
        return True
    first_submitted_on = india_date(min(proof.created_at for proof in proofs))
    return first_submitted_on <= memo.content_due_on


def _disclosure_confirmed(
    memo: DealMemo, proofs: list[DeliverableProof], now: datetime
) -> bool:
    approved = [proof for proof in proofs if is_approved(memo, proof, now)]
    return all(proof.disclosure_confirmed for proof in approved)


def build_record(
    deals: list[tuple[DealMemo, str]],
    proofs_by_memo: dict[uuid.UUID, list[DeliverableProof]],
    creator_id: uuid.UUID,
    now: datetime,
) -> DeliveryRecord:
    """Work the record out from rows. Pure, so it is easy to trust.

    `deals` holds each accepted memo with its campaign type.
    """
    delivered: list[DealMemo] = []
    not_delivered = 0
    overdue_now = 0
    barter_delivered = 0
    barter_not_delivered = 0
    for memo, campaign_type in deals:
        proofs = proofs_by_memo.get(memo.id, [])
        outcome = classify(memo, proofs, now)
        if campaign_type == "barter":
            if outcome is Outcome.DELIVERED:
                barter_delivered += 1
            elif outcome is Outcome.NOT_DELIVERED:
                barter_not_delivered += 1
            continue
        if outcome is Outcome.DELIVERED:
            delivered.append(memo)
        elif outcome is Outcome.NOT_DELIVERED:
            not_delivered += 1
            # A silent no-show still owes the work; a cancelled deal does not.
            if memo.status != "cancelled":
                overdue_now += 1
        elif outcome is Outcome.OVERDUE:
            overdue_now += 1

    completed = len(delivered) + not_delivered
    enough = completed >= MIN_DEALS_FOR_HISTORY
    on_time_share: float | None = None
    disclosure_share: float | None = None
    if enough:
        # Over every completed deal, not just the delivered ones: a creator
        # who delivered none of three reads 0.0, not "no figure".
        on_time_share = (
            sum(
                1 for memo in delivered if _on_time(memo, proofs_by_memo.get(memo.id, []))
            )
            / completed
        )
        required = [memo for memo in delivered if memo.disclosure_required]
        if required:
            disclosure_share = sum(
                1
                for memo in required
                if _disclosure_confirmed(memo, proofs_by_memo.get(memo.id, []), now)
            ) / len(required)

    return DeliveryRecord(
        creator_id=creator_id,
        status=HAS_HISTORY if enough else NO_HISTORY_YET,
        deals_completed=completed,
        deals_delivered=len(delivered),
        deals_not_delivered=not_delivered,
        currently_overdue=overdue_now,
        delivered_on_time_share=on_time_share,
        disclosure_confirmed_share=disclosure_share,
        barter_deals_delivered=barter_delivered,
        barter_deals_not_delivered=barter_not_delivered,
    )


def creator_exists(db: Session, creator_id: uuid.UUID) -> bool:
    return db.scalar(select(Creator.id).where(Creator.id == creator_id)) is not None


def creator_id_for_account(db: Session, account_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(Creator.id).where(Creator.account_id == account_id))


def for_creator(db: Session, creator_id: uuid.UUID, now: datetime) -> DeliveryRecord:
    """This creator's delivery record as of `now`, in two queries."""
    deals = [
        (memo, campaign_type)
        for memo, campaign_type in db.execute(
            select(DealMemo, Campaign.campaign_type)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(
                Application.creator_id == creator_id,
                # Only deals the creator agreed to: a memo they declined, or
                # one withdrawn before they answered, promised nothing.
                DealMemo.accepted_at.is_not(None),
            )
            .order_by(DealMemo.accepted_at, DealMemo.id)
        ).tuples()
    ]
    proofs_by_memo: dict[uuid.UUID, list[DeliverableProof]] = defaultdict(list)
    if deals:
        for proof in db.scalars(
            select(DeliverableProof)
            .where(DeliverableProof.deal_memo_id.in_([memo.id for memo, _ in deals]))
            .order_by(DeliverableProof.created_at, DeliverableProof.id)
        ):
            proofs_by_memo[proof.deal_memo_id].append(proof)
    return build_record(deals, proofs_by_memo, creator_id, now)

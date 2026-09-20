"""A brand's payment record, as a fact rather than a rating (D-027).

A creator deciding whether to spend a week filming for someone has one
question: does this brand actually pay? This answers it from what happened,
never from an opinion.

Three things shape the design, and all three are about not misleading
somebody who is about to risk a week of work.

**1. Silence must not launder a bad record.** The strongest finding in the
marketplace reputation literature is that people who have a bad experience
leave and never report it, so bad actors' reputations go unharmed. Here that
bites hardest: a creator who was never paid is exactly the person least
likely to come back and tick a box. So a brand's record is not built only
from deals that ended happily. A payment that ran past its deadline and
stayed there counts against the record whether or not anybody complained,
because the calendar reports it and nobody has to.

**2. "New brand" must not be a hiding place.** Reputation systems get gamed
by starting again, and a floor of three deals is exactly the kind of rule
somebody can sit behind. So `currently_overdue` is reported *always* — below
the floor, above it, and for a brand with no completed deals at all. A brand
owing two creators right now can never read as simply "new".

**3. No smoothing, no shrinkage.** The usual fix for small samples is to
pull an average toward the global mean. That is right for star ratings,
where the number is an opinion, and wrong here, where it is a record of
what happened: shrinking would report a number that is not true of this
brand. Instead the count is always published beside the figures, and below
three completed deals the figures are withheld rather than dressed up
(D-027). People do ignore sample size when it is not in front of them, so
it is put in front of them.
"""

import statistics
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth.models.brand import Brand
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.disputes import service as disputes
from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.service import (
    CONFIRMED,
    LATE,
    PAID,
    UNCONFIRMED,
    UNPAID,
    derive_state,
    india_date,
)

# Below this, the figures are withheld rather than shown with a caveat
# nobody reads (D-027).
MIN_DEALS_FOR_HISTORY = 3

# A record that has reached a settled outcome. `late` is missing on purpose:
# it is still live, and counting a payment that is four days overdue as a
# failure would be as unfair as pretending it is fine. It shows up in
# `currently_overdue` instead, which is reported separately and always.
SETTLED_PAID = frozenset({PAID, UNCONFIRMED, CONFIRMED})
SETTLED_STATES = SETTLED_PAID | {UNPAID}

# What the caller should say when there is not enough to report. The words
# themselves belong to the frontend, which has to say them in Tamil as well
# as English (ux.md section 6).
NO_HISTORY_YET = "new_brand_no_history_yet"
HAS_HISTORY = "has_payment_history"


@dataclass(frozen=True)
class ReliabilityRecord:
    """What we can honestly say about how a brand pays."""

    brand_id: uuid.UUID
    status: str
    # Deals that reached a settled outcome, paid or not. The denominator.
    deals_completed: int
    # Of those, how many the brand actually paid.
    deals_paid: int
    # Of those, how many it never paid. The number that matters most.
    deals_unpaid: int
    # Payments owed right now and past their date. Always reported, even
    # when there is no history to speak of.
    currently_overdue: int
    # Withheld below the floor: None means "not enough to say", which is not
    # the same as zero and must never be rendered as zero.
    paid_on_time_share: float | None
    median_days_to_pay: float | None

    @property
    def has_history(self) -> bool:
        return self.status == HAS_HISTORY


def _payments_for_brand(db: Session, brand_id: uuid.UUID) -> list[PaymentStatus]:
    """Every payment record on this brand's own deals, in one query."""
    return list(
        db.scalars(
            select(PaymentStatus)
            .join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(Campaign.brand_id == brand_id)
            .order_by(PaymentStatus.due_on, PaymentStatus.id)
        ).all()
    )


def _days_to_pay(payment: PaymentStatus) -> int:
    """Days from the work being approved to the brand saying it paid.

    Counted from when the record was opened, which is the moment approval
    started the clock, so it answers the question a creator actually asks:
    how long does this brand take?
    """
    return (india_date(payment.marked_paid_at) - india_date(payment.created_at)).days


def _paid_on_time(payment: PaymentStatus) -> bool:
    return india_date(payment.marked_paid_at) <= payment.due_on


def build_record(
    payments: list[PaymentStatus],
    brand_id: uuid.UUID,
    today: date,
    disputed: set[uuid.UUID] | None = None,
) -> ReliabilityRecord:
    """Work the record out from payment rows. Pure, so it is easy to trust.

    `disputed` holds the payments somebody is actively arguing about. They
    are held short of `unpaid`, because a payment under dispute is not the
    same as a payment nobody will discuss, and marking a brand as a
    non-payer while the matter is live would be us taking a side (D-028).
    """
    argued_about = disputed or set()
    states = [
        (
            payment,
            derive_state(
                payment, today, has_open_dispute=payment.id in argued_about
            ),
        )
        for payment in payments
    ]

    settled = [payment for payment, state in states if state in SETTLED_STATES]
    paid = [payment for payment, state in states if state in SETTLED_PAID]
    unpaid = [payment for payment, state in states if state == UNPAID]
    # Both count as owed right now: `late` is running out of time, `unpaid`
    # has run out. Neither is hidden by the floor below.
    overdue_now = [payment for payment, state in states if state in (LATE, UNPAID)]

    enough = len(settled) >= MIN_DEALS_FOR_HISTORY
    on_time_share: float | None = None
    median_days: float | None = None
    if enough:
        # Deliberately over every settled deal, not just the paid ones. A
        # brand that paid none of three gets 0.0, loudly — dividing by the
        # paid ones would have let it report no figure at all, and the brand
        # that pays nobody is the one this record exists to show.
        on_time_share = sum(1 for payment in paid if _paid_on_time(payment)) / len(
            settled
        )
        # Undefined rather than zero when they have never paid: "pays in 0
        # days" would be a lie in the brand's favour.
        median_days = (
            statistics.median(_days_to_pay(payment) for payment in paid)
            if paid
            else None
        )

    return ReliabilityRecord(
        brand_id=brand_id,
        status=HAS_HISTORY if enough else NO_HISTORY_YET,
        deals_completed=len(settled),
        deals_paid=len(paid),
        deals_unpaid=len(unpaid),
        currently_overdue=len(overdue_now),
        paid_on_time_share=on_time_share,
        median_days_to_pay=median_days,
    )


def for_brand(db: Session, brand_id: uuid.UUID, today: date) -> ReliabilityRecord:
    """This brand's payment record as of today."""
    payments = _payments_for_brand(db, brand_id)
    disputed = disputes.open_payment_ids(db, {p.id for p in payments}, today)
    return build_record(payments, brand_id, today, disputed)


def brand_exists(db: Session, brand_id: uuid.UUID) -> bool:
    return db.scalar(select(Brand.id).where(Brand.id == brand_id)) is not None

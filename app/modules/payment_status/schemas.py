"""Request and response shapes for payment records."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.taxonomy import CURRENCY
from app.modules.payment_status.models import (
    PAYMENT_METHODS,
    REFERENCE_MAX_LENGTH,
    PaymentStatus,
)
from app.modules.payment_status.reliability import (
    HAS_HISTORY,
    NO_HISTORY_YET,
    ReliabilityRecord,
)
from app.modules.payment_status.service import (
    PAYMENT_STATES,
    REFERENCE_MIN_LENGTH,
    days_overdue,
    derive_state,
    is_auto_matchable,
)

PaymentMethod = Literal["upi", "bank_transfer", "cash"]
PaymentState = Literal["due", "late", "unpaid", "paid", "unconfirmed", "confirmed"]

# Keeps these lists honest against the database's own allow-lists.
assert set(PAYMENT_METHODS) == set(PaymentMethod.__args__)
assert set(PAYMENT_STATES) == set(PaymentState.__args__)


class MarkPaidRequest(BaseModel):
    """What the brand says when it has sent the money."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    method: Annotated[
        PaymentMethod,
        Field(description="How the money was sent"),
    ]
    reference: Annotated[
        str,
        Field(
            min_length=REFERENCE_MIN_LENGTH,
            max_length=REFERENCE_MAX_LENGTH,
            description=(
                "The UPI reference number, the bank UTR, or a note saying how "
                "cash was handed over. A UPI reference is 12 digits, a NEFT "
                "UTR 16 characters, an RTGS UTR 22."
            ),
            examples=["412345678901"],
        ),
    ]


class PaymentRead(BaseModel):
    """A payment record, with its state read from the dates.

    `state` is not a stored column. It is worked out from `due_on`,
    `marked_paid_at` and `confirmed_at` against today, so it can never be
    stale (see models.py).
    """

    id: uuid.UUID
    deal_memo_id: uuid.UUID
    amount_paise: int
    currency: str = CURRENCY
    due_on: date
    state: PaymentState
    days_overdue: int
    method: PaymentMethod | None
    reference: str | None
    # Whether this reference could ever be checked against a bank feed. Only
    # a real 12-digit UPI reference can (D-027).
    reference_auto_matchable: bool
    marked_paid_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


def to_read(payment: PaymentStatus, today: date) -> PaymentRead:
    """Build the response, including the parts that are worked out."""
    return PaymentRead(
        id=payment.id,
        deal_memo_id=payment.deal_memo_id,
        amount_paise=payment.amount_paise,
        currency=payment.currency,
        due_on=payment.due_on,
        state=derive_state(payment, today),
        days_overdue=days_overdue(payment, today),
        method=payment.method,
        reference=payment.reference,
        reference_auto_matchable=is_auto_matchable(payment),
        marked_paid_at=payment.marked_paid_at,
        confirmed_at=payment.confirmed_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


ReliabilityStatus = Literal["new_brand_no_history_yet", "has_payment_history"]

assert {NO_HISTORY_YET, HAS_HISTORY} == set(ReliabilityStatus.__args__)


class BrandReliabilityRead(BaseModel):
    """How a brand pays, from what happened rather than from opinions.

    `paid_on_time_share` and `median_days_to_pay` are `null` until the brand
    has three completed deals (D-027). **Null means "not enough to say" and
    must never be shown as zero** — the two mean opposite things here.

    `currently_overdue` is reported whatever the status, including for a
    brand with no completed deals at all, so that "new" can never be a place
    to hide an unpaid creator.
    """

    brand_id: uuid.UUID
    status: ReliabilityStatus
    deals_completed: int
    deals_paid: int
    deals_unpaid: int
    currently_overdue: int
    paid_on_time_share: float | None
    median_days_to_pay: float | None


def to_reliability_read(record: ReliabilityRecord) -> BrandReliabilityRead:
    return BrandReliabilityRead(
        brand_id=record.brand_id,
        status=record.status,
        deals_completed=record.deals_completed,
        deals_paid=record.deals_paid,
        deals_unpaid=record.deals_unpaid,
        currently_overdue=record.currently_overdue,
        paid_on_time_share=record.paid_on_time_share,
        median_days_to_pay=record.median_days_to_pay,
    )

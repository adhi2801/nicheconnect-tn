"""Request and response shapes for payment records."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
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
    MAX_BULK_MARK_PAID,
    PAYMENT_STATES,
    REFERENCE_MIN_LENGTH,
    days_overdue,
    derive_state,
    is_auto_matchable,
)

PaymentMethod = Literal["upi", "bank_transfer", "cash"]
PaymentState = Literal["due", "late", "unpaid", "paid", "unconfirmed", "confirmed"]

# Keeps these lists honest against the database's own allow-lists.
ensure_same_values("PaymentMethod", PaymentMethod, PAYMENT_METHODS)
ensure_same_values("PaymentState", PaymentState, PAYMENT_STATES)


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
    # A payment being argued about is held at `late` rather than hardening
    # into `unpaid` (D-027), so the UI can say why.
    has_open_dispute: bool
    created_at: datetime
    updated_at: datetime


def to_read(
    payment: PaymentStatus, today: date, *, has_open_dispute: bool = False
) -> PaymentRead:
    """Build the response, including the parts that are worked out."""
    return PaymentRead(
        id=payment.id,
        deal_memo_id=payment.deal_memo_id,
        amount_paise=payment.amount_paise,
        currency=payment.currency,
        due_on=payment.due_on,
        state=derive_state(payment, today, has_open_dispute=has_open_dispute),
        days_overdue=days_overdue(payment, today),
        method=payment.method,
        reference=payment.reference,
        reference_auto_matchable=is_auto_matchable(payment),
        marked_paid_at=payment.marked_paid_at,
        confirmed_at=payment.confirmed_at,
        has_open_dispute=has_open_dispute,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


ReliabilityStatus = Literal["new_brand_no_history_yet", "has_payment_history"]

ensure_same_values("ReliabilityStatus", ReliabilityStatus, (NO_HISTORY_YET, HAS_HISTORY))


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


# --- many at once --------------------------------------------------------------


class BulkMarkPaidRow(MarkPaidRequest):
    """One row of a bank bulk transfer: which deal, how it was sent, its reference."""

    memo_id: uuid.UUID


class BulkMarkPaidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payments: list[BulkMarkPaidRow] = Field(
        min_length=1,
        max_length=MAX_BULK_MARK_PAID,
        description=f"1 to {MAX_BULK_MARK_PAID} rows, each deal memo at most once",
    )

    @model_validator(mode="after")
    def each_deal_once(self) -> "BulkMarkPaidRequest":
        # Two rows for one deal would make "which reference is the real one"
        # a question the order of the list answers. Refuse it instead.
        memo_ids = [row.memo_id for row in self.payments]
        if len(set(memo_ids)) != len(memo_ids):
            raise PydanticCustomError(
                "duplicate_memo", "Each deal memo can appear only once in a request"
            )
        return self


class RowProblem(BaseModel):
    """Why one row was refused, in the same terms a single request would get."""

    status: int
    code: str
    title: str
    detail: str | None = None


class BulkMarkPaidResult(BaseModel):
    index: int = Field(description="The row's position in the request, from 0")
    memo_id: uuid.UUID
    outcome: Literal["recorded", "refused"]
    payment: PaymentRead | None = Field(description="Set when recorded")
    problem: RowProblem | None = Field(description="Set when refused")


class BulkMarkPaidRead(BaseModel):
    """Every row's result, in the order the rows were sent."""

    recorded: int
    refused: int
    results: list[BulkMarkPaidResult]

"""Payment endpoints: the brand says it paid, the creator says it arrived.

The handshake is deliberately two-sided and asymmetric, because the two
statements are different in kind. "I sent it" is a claim only the brand can
make; "it arrived" is a fact only the creator can confirm. Neither side can
make the other's statement, and the record shows which of the two has
happened (security.md section 2).

NicheConnect TN never receives or holds this money. These endpoints record
what the two sides say happened.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo.dependencies import (
    BrandMemo,
    CreatorMemo,
    visible_memo_for_account,
)
from app.modules.payment_status import service
from app.modules.payment_status.exceptions import PaymentRecordNotFound
from app.modules.payment_status.schemas import MarkPaidRequest, PaymentRead, to_read

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

# route_class: marking a payment is exactly what backend.md section 2 means
# by a POST that must accept an Idempotency-Key. A creator's phone losing
# signal mid-request must never turn one payment into two records.
router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["payment"], route_class=IdempotentRoute
)

MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]

_COMMON_ERRORS = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    404: problem_doc("No such memo, or it is not yours, or it has no payment record"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _payment_or_404(db: Session, memo_id: uuid.UUID):
    payment = service.get_for_memo(db, memo_id)
    if payment is None:
        raise PaymentRecordNotFound(
            "A payment record is opened when the work is approved. "
            "This deal has no approved work yet, or it is a barter deal."
        )
    return payment


@router.get(
    "/{memo_id}/payment",
    response_model=PaymentRead,
    summary="Read the payment record for a deal",
    description=(
        "Both sides of a deal see the same record: what is owed, by when, "
        "what the brand says it sent and whether the creator confirmed it "
        "arrived. `state` is worked out from the dates, so it is never stale."
    ),
    responses=_COMMON_ERRORS,
)
@limiter.limit(READ_LIMIT)
def read_payment(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> PaymentRead:
    """Either party may read it. Nobody else can."""
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    payment = _payment_or_404(db, memo.id)
    return to_read(payment, service.india_date(now))


@router.post(
    "/{memo_id}/payment/mark-paid",
    response_model=PaymentRead,
    summary="Mark this payment as sent",
    description=(
        "The brand records that it has paid the creator directly, and how. "
        "NicheConnect TN never handles the money; this is the record of it. "
        "Only the brand on the deal can do this, and only once."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This payment is already marked as sent"),
        422: problem_doc("The method or reference is not usable"),
    },
)
@limiter.limit(WRITE_LIMIT)
def mark_paid(
    request: Request,
    memo_id: MemoId,
    body: MarkPaidRequest,
    memo: BrandMemo,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> PaymentRead:
    """Only the brand can say it sent the money."""
    payment = _payment_or_404(db, memo.id)
    service.mark_paid(
        db, payment, method=body.method, reference=body.reference, now=now
    )
    return to_read(payment, service.india_date(now))


@router.post(
    "/{memo_id}/payment/confirm",
    response_model=PaymentRead,
    summary="Confirm the payment arrived",
    description=(
        "The creator confirms the money reached them. Only the creator on "
        "the deal can do this, and only after the brand has marked it sent."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc(
            "Already confirmed, or the brand has not marked it as sent yet"
        ),
    },
)
@limiter.limit(WRITE_LIMIT)
def confirm_received(
    request: Request,
    memo_id: MemoId,
    memo: CreatorMemo,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> PaymentRead:
    """Only the creator can say the money arrived."""
    payment = _payment_or_404(db, memo.id)
    service.confirm_received(db, payment, now=now)
    return to_read(payment, service.india_date(now))

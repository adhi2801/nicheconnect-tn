"""Marking many payments as sent at once, for a brand paying several creators.

A brand that pays creators through its bank's bulk transfer gets one
reference per row back, and some rows may have been rejected by the bank.
It sends the rows that went through; each is recorded or refused on its
own, and the answer lists every row in the order it was sent. A retry with
the same Idempotency-Key gets that same answer back (D-040).

NicheConnect TN never moves the money (constraint 1). This is the record
that the brand says it did, exactly as for a single payment.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns.dependencies import CurrentBrandProfile
from app.modules.disputes import service as disputes
from app.modules.payment_status import service
from app.modules.payment_status.schemas import (
    BulkMarkPaidRead,
    BulkMarkPaidRequest,
    BulkMarkPaidResult,
    RowProblem,
    to_read,
)

# Each request can record up to 25 payments, so it is limited more tightly
# than a single write.
BULK_LIMIT = "10 per minute"

router = APIRouter(
    prefix="/api/v1/brands/me/payments", tags=["payment"], route_class=IdempotentRoute
)

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brand accounts can do this"),
    409: problem_doc("The brand profile has not been created yet"),
    422: problem_doc(
        "Not 1 to 25 rows, a deal memo listed twice, or a method or reference "
        "that is not usable"
    ),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.post(
    "/mark-paid",
    response_model=BulkMarkPaidRead,
    summary="Mark several payments as sent",
    description=(
        "For a brand that paid several creators at once, typically through its "
        "bank's bulk transfer: one row per deal, with the method and the "
        "reference the bank gave for that row. Each row is recorded or refused "
        "on its own, with exactly the rules of the single endpoint, and one "
        "refused row never holds back the others. The answer lists every row in "
        "the order sent: `recorded` with the payment, or `refused` with the "
        "same problem code a single request would get. Another brand's deal is "
        "refused as not found. Always 200 once the request itself is valid."
    ),
    responses=_ERRORS,
)
@rate_limit(BULK_LIMIT)
def mark_paid_in_bulk(
    request: Request,
    body: BulkMarkPaidRequest,
    brand: CurrentBrandProfile,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BulkMarkPaidRead:
    outcomes = service.mark_paid_in_bulk(
        db,
        brand.id,
        [
            service.BulkMarkPaidRow(row.memo_id, row.method, row.reference)
            for row in body.payments
        ],
        now=now,
    )
    today = india_date(now)
    recorded_ids = {o.payment.id for o in outcomes if o.payment is not None}
    disputed = (
        disputes.open_payment_ids(db, recorded_ids, today) if recorded_ids else set()
    )

    results = [
        _result(index, outcome, today, disputed) for index, outcome in enumerate(outcomes)
    ]
    recorded = sum(1 for r in results if r.outcome == "recorded")
    return BulkMarkPaidRead(
        recorded=recorded, refused=len(results) - recorded, results=results
    )


def _result(
    index: int,
    outcome: service.BulkMarkPaidOutcome,
    today: date,
    disputed: set[uuid.UUID],
) -> BulkMarkPaidResult:
    """One row of the answer: recorded with its payment, or refused with why."""
    if outcome.payment is not None:
        return BulkMarkPaidResult(
            index=index,
            memo_id=outcome.memo_id,
            outcome="recorded",
            payment=to_read(
                outcome.payment, today, has_open_dispute=outcome.payment.id in disputed
            ),
            problem=None,
        )
    if outcome.refusal is None:
        raise RuntimeError("A bulk outcome always carries a payment or a refusal")
    return BulkMarkPaidResult(
        index=index,
        memo_id=outcome.memo_id,
        outcome="refused",
        payment=None,
        problem=RowProblem(
            status=int(outcome.refusal.status_code),
            code=outcome.refusal.code,
            title=outcome.refusal.title,
            detail=outcome.refusal.detail,
        ),
    )

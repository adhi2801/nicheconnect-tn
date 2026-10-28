"""My payments: every payment across my deals, and the totals (D-075).

For a brand, the payments it owes or has made on its own campaigns. For a
creator, the payments owed to it. A row is only ever one of the caller's
own deals; nobody else's appears, and there is no id to guess.

NicheConnect TN never handles this money. These are the records of what the
two sides said happened.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.service import get_brand_for_account, get_creator_for_account
from app.modules.disputes import service as disputes
from app.modules.payment_status import listing
from app.modules.payment_status.exceptions import NotAPaymentParty
from app.modules.payment_status.schemas import (
    PaymentListItem,
    PaymentTotalsRead,
    PaymentView,
    to_list_item,
    to_totals_read,
)

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/payments", tags=["payment"])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
ViewFilter = Annotated[
    PaymentView | None,
    Query(
        alias="view",
        description=(
            "`to_pay`: not yet marked as sent. `awaiting_confirmation`: marked as "
            "sent, not yet confirmed as arrived. `finished`: confirmed. Leave out "
            "for all of them."
        ),
    ),
]

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brand and creator accounts have payments"),
    409: problem_doc("The profile has not been created yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _party(db: Session, account: Account) -> Brand | Creator:
    if account.role == "brand":
        return get_brand_for_account(db, account.id)
    if account.role == "creator":
        return get_creator_for_account(db, account.id)
    raise NotAPaymentParty()


@router.get(
    "/mine",
    response_model=Page[PaymentListItem],
    summary="List my payments",
    description=(
        "Every payment across the caller's deals, newest first, each with its "
        "campaign, creator and brand, so a screen needs no call per row. "
        "`state` is worked out from the dates, as for a single payment."
    ),
    responses={**_ERRORS, 422: problem_doc("A query parameter or the cursor is invalid")},
)
@rate_limit(READ_LIMIT)
def list_my_payments(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    view: ViewFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Page[PaymentListItem]:
    result = listing.list_payments(
        db, _party(db, account), view=view, limit=limit, cursor=cursor
    )
    today = india_date(now)
    disputed = disputes.open_payment_ids(
        db, {row.payment.id for row in result.rows}, today
    )
    return Page[PaymentListItem](
        items=[
            to_list_item(row, today, has_open_dispute=row.payment.id in disputed)
            for row in result.rows
        ],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/mine/totals",
    response_model=PaymentTotalsRead,
    summary="Totals of my payments",
    description=(
        "How many payments, and how much, are to pay, overdue, awaiting "
        "confirmation and finished, across all the caller's deals. Overdue is "
        "always returned, zero included."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def my_payment_totals(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> PaymentTotalsRead:
    today = india_date(now)
    return to_totals_read(listing.totals(db, _party(db, account), today), today)

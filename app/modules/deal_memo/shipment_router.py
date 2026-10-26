"""A barter deal's shipment (HTTP, item 68, D-131). The rules: shipment_service."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.deal_memo import shipment_service as service
from app.modules.deal_memo.dependencies import (
    BrandMemo,
    CreatorMemo,
    MemoId,
    visible_memo_for_account,
)
from app.modules.deal_memo.schemas import ShipmentIn, ShipmentRead

READ_LIMIT = "60 per minute"
# A ceiling per day as well as per minute: each step tells the other side
# (trust-and-safety.md rule 2).
WRITE_LIMIT = "30 per minute;100 per day"

# route_class: a retry with the same Idempotency-Key gets the first answer.
router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["deal memos"], route_class=IdempotentRoute
)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/{memo_id}/shipment",
    response_model=ShipmentRead,
    summary="A barter deal's shipment",
    description=(
        "How the brand sent the goods, and when the creator said they arrived. "
        "Show the tracking number as text, never as a link. The brand and the "
        "creator of this deal only."
    ),
    responses={
        **_COMMON,
        404: problem_doc(
            "No such deal of yours, or no shipment recorded yet (`shipment_not_found`)"
        ),
    },
)
@rate_limit(READ_LIMIT)
def read_shipment(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Session = Depends(get_db),
) -> ShipmentRead:
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    return ShipmentRead.model_validate(service.of(db, memo))


@router.put(
    "/{memo_id}/shipment",
    response_model=ShipmentRead,
    summary="Record how a barter deal's goods were sent",
    description=(
        "The courier and the tracking number, once the deal is agreed; never an "
        "address. It is sealed onto the deal's record and the creator is told. "
        "Until the creator says the goods arrived, a mistyped number may be "
        "corrected, and each version stays on the record; the same courier and "
        "number again changes nothing. The deal's brand only."
    ),
    responses={
        **_COMMON,
        403: problem_doc("Only the deal's brand records the shipment"),
        404: problem_doc("No such deal of yours"),
        409: problem_doc(
            "`shipment_closed`: not an agreed barter deal; "
            "`shipment_already_received`: the creator has said it arrived"
        ),
        422: problem_doc("An unknown courier, or a tracking number of the wrong shape"),
    },
)
@rate_limit(WRITE_LIMIT)
def record_shipment(
    request: Request,
    body: ShipmentIn,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ShipmentRead:
    shipment = service.ship(
        db, memo, carrier=body.carrier, tracking_number=body.tracking_number, now=now
    )
    return ShipmentRead.model_validate(shipment)


@router.post(
    "/{memo_id}/shipment/received",
    response_model=ShipmentRead,
    summary="Say a barter deal's goods arrived",
    description=(
        "Only the creator says so, once, the way only the creator confirms a "
        "payment arrived. It is sealed onto the deal's record and the brand is "
        "told. The deal's creator only."
    ),
    responses={
        **_COMMON,
        403: problem_doc("Only the deal's creator says the goods arrived"),
        404: problem_doc(
            "No such deal of yours, or no shipment recorded yet (`shipment_not_found`)"
        ),
        409: problem_doc("`shipment_already_received`: already said"),
    },
)
@rate_limit(WRITE_LIMIT)
def receive_shipment(
    request: Request,
    memo: CreatorMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ShipmentRead:
    return ShipmentRead.model_validate(service.receive(db, memo, now))

"""The UPI pay link over HTTP (D-085). The rules and the threat model: upi_service."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import profiles
from app.modules.auth.dependencies import CurrentCreator, get_now
from app.modules.auth.models.creator import Creator
from app.modules.deal_memo.dependencies import BrandMemo
from app.modules.payment_status import upi_service as service
from app.modules.payment_status.exceptions import PaymentRecordNotFound
from app.modules.payment_status.service import get_for_memo
from app.modules.payment_status.upi_schemas import PayDetailsRead, UpiRead, UpiSet

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"
# Lower than other reads: each answer holds another person's UPI ID.
PAY_DETAILS_LIMIT = "20 per minute;200 per day"

# PUT replaces the whole setting and DELETE removes it, so both are
# idempotent by nature and need no Idempotency-Key (backend.md section 2).
router = APIRouter(prefix="/api/v1", tags=["upi pay link"])

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_MINE: ResponseDocs = {
    **_COMMON,
    403: problem_doc("Only a creator may use this endpoint"),
    404: problem_doc("You have not created a creator profile yet"),
}


def _read(row: object | None) -> UpiRead:
    if row is None:
        return UpiRead(
            upi_id=None, consented_at=None, notice_version=None, updated_at=None
        )
    return UpiRead.model_validate(row, from_attributes=True)


@router.get(
    "/creators/me/upi",
    response_model=UpiRead,
    summary="My UPI ID",
    description=(
        "The UPI ID you gave so brands on your deals can pay you directly, and "
        "the notice version you agreed to. All null when you have not added one."
    ),
    responses=_MINE,
)
@rate_limit(READ_LIMIT)
def read_my_upi(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> UpiRead:
    creator = profiles.get_profile(db, Creator, account.id)
    return _read(service.get_for_creator(db, creator))


@router.put(
    "/creators/me/upi",
    response_model=UpiRead,
    summary="Give or change my UPI ID",
    description=(
        "Stores your UPI ID, with your consent to the notice you were shown. "
        "`consent` must be true, and `notice_version` the version you read; "
        "consent is given again with every change. Brands see the ID only while "
        "a payment to you on their deal is open. A UPI ID made of a phone "
        "number is refused, because brands would see the number. Money still "
        "goes from the brand's bank straight to yours."
    ),
    responses={
        **_MINE,
        409: problem_doc("The notice changed since you read it"),
        422: problem_doc("Consent is missing, or the UPI ID is not usable"),
        503: problem_doc("Adding a UPI ID is not open yet: its notice is not ready"),
    },
)
@rate_limit(WRITE_LIMIT)
def set_my_upi(
    request: Request,
    body: UpiSet,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> UpiRead:
    creator = profiles.get_profile(db, Creator, account.id)
    return _read(
        service.set_for_creator(db, creator, body.upi_id, body.notice_version, now)
    )


@router.delete(
    "/creators/me/upi",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove my UPI ID",
    description=(
        "Deletes your UPI ID and withdraws the consent you gave for it. Brands "
        "then pay you by bank transfer. Always allowed, and safe to repeat."
    ),
    responses=_MINE,
)
@rate_limit(WRITE_LIMIT)
def remove_my_upi(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> Response:
    service.remove_for_creator(db, profiles.get_profile(db, Creator, account.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/deal-memos/{memo_id}/payment/pay-details",
    response_model=PayDetailsRead,
    summary="How to pay the creator by UPI",
    description=(
        "For the brand on this deal, while its payment is open: the creator's "
        "UPI ID, the amount and a `upi://pay` link that opens the brand's own "
        "UPI app with everything filled in. Before entering the PIN, check that "
        "the name the UPI app shows is the creator's. NicheConnect TN never "
        "receives the money. `pay_link` is null when the creator has added no "
        "UPI ID or the amount is above UPI's limit between people, and "
        "`unavailable_reason` says which. Then mark the payment sent with the "
        "UPI reference, as usual."
    ),
    responses={
        **_COMMON,
        403: problem_doc("Only the brand on the deal may see this"),
        404: problem_doc(
            "No such memo, it is not yours, or it has no payment record yet"
        ),
        409: problem_doc("This payment is already marked as sent"),
    },
)
@rate_limit(PAY_DETAILS_LIMIT)
def read_pay_details(
    request: Request,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> PayDetailsRead:
    payment = get_for_memo(db, memo.id)
    if payment is None:
        raise PaymentRecordNotFound(
            "A payment record is opened when the work is approved. "
            "This deal has no approved work yet, or it is a barter deal."
        )
    details = service.pay_details(db, memo, payment, now)
    return PayDetailsRead.model_validate(details, from_attributes=True)

"""Dispute endpoints. Either side may raise one; neither side wins one here.

Everything hangs off the payment record, because that is what a dispute is
about. Both parties read the same timeline, including the words the other one
wrote — a one-sided record would be no use to anybody trying to show what
happened, which is the only thing this is for.

There is no endpoint that decides who was right, and there is not going to
be one (D-028).
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.models.account import Account
from app.modules.deal_memo.dependencies import visible_memo_for_account
from app.modules.deal_memo.models import DealMemo
from app.modules.disputes import service
from app.modules.disputes.exceptions import NothingToRecord
from app.modules.disputes.models import Dispute
from app.modules.disputes.schemas import (
    DisputeClose,
    DisputeEntryCreate,
    DisputeEventRead,
    DisputeOpen,
    DisputeRead,
    to_event_read,
    to_read,
)
from app.modules.payment_status import service as payments
from app.modules.payment_status.exceptions import PaymentRecordNotFound
from app.modules.payment_status.models import PaymentStatus

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

# Raising a dispute is a POST that must not fire twice from one tap.
router = APIRouter(
    prefix="/api/v1/deal-memos", tags=["disputes"], route_class=IdempotentRoute
)

MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("You are not a party to this deal"),
    404: problem_doc("No such memo, no payment record, or no dispute"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _memo_and_payment(
    db: Session, memo_id: uuid.UUID, account: Account
) -> tuple[DealMemo, PaymentStatus]:
    """The deal and its payment record, seen from whichever side is asking."""
    memo = visible_memo_for_account(db, memo_id, account.id, account.role)
    payment = payments.get_for_memo(db, memo.id)
    if payment is None:
        raise PaymentRecordNotFound(
            "There is nothing to dispute yet: a payment record opens when "
            "the work is approved."
        )
    return memo, payment


def _rendered(db: Session, dispute: Dispute, today: date) -> DisputeRead:
    return to_read(
        dispute, service.derive_state(dispute, today), service.timeline(db, dispute)
    )


@router.post(
    "/{memo_id}/payment/dispute",
    status_code=status.HTTP_201_CREATED,
    response_model=DisputeRead,
    summary="Raise a dispute about this payment",
    description=(
        "Either side may raise one: a creator saying the money never came, "
        "or a brand saying the work was not what was agreed. Your reason "
        "becomes the first entry on the timeline. The other side has seven "
        "days to put their account on the record, and after thirty days with "
        "nothing agreed it is recorded as unresolved — which is a fact about "
        "the dispute, not a finding about either of you. "
        "NicheConnect TN does not decide who is right."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This payment already has a dispute"),
        422: problem_doc("The reason is missing or too short"),
    },
)
@rate_limit(WRITE_LIMIT)
def open_dispute(
    request: Request,
    memo_id: MemoId,
    body: DisputeOpen,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DisputeRead:
    """Raise it. Either party, once per payment."""
    _, payment = _memo_and_payment(db, memo_id, account)
    dispute = service.open_for_payment(
        db, payment.id, opened_by=account.role, reason=body.reason, now=now
    )
    db.commit()
    db.refresh(dispute)
    return _rendered(db, dispute, india_date(now))


@router.get(
    "/{memo_id}/payment/dispute",
    response_model=DisputeRead,
    summary="Read the dispute and its timeline",
    description=(
        "Both sides see the same record, including what the other one wrote. "
        "The order entries were made in is usually the only thing two people "
        "afterwards agree on, so it is preserved exactly."
    ),
    responses=_COMMON_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_dispute(
    request: Request,
    memo_id: MemoId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DisputeRead:
    """Either party may read it. Nobody else can."""
    _, payment = _memo_and_payment(db, memo_id, account)
    dispute = service.get_or_404(db, payment.id)
    return _rendered(db, dispute, india_date(now))


@router.post(
    "/{memo_id}/payment/dispute/entries",
    status_code=status.HTTP_201_CREATED,
    response_model=DisputeEventRead,
    summary="Put something on the record",
    description=(
        "Add your account of what happened, a link that supports it, or "
        "both. Late entries are accepted, including after the seven days and "
        "after the thirty: a late account is still an account. Nothing can "
        "be added once an outcome has been agreed."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This dispute has already been closed"),
        422: problem_doc("An entry must carry a note, a link, or both"),
    },
)
@rate_limit(WRITE_LIMIT)
def add_entry(
    request: Request,
    memo_id: MemoId,
    body: DisputeEntryCreate,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DisputeEventRead:
    """Either party adds to their own record."""
    if body.note is None and body.evidence_url is None:
        raise NothingToRecord()

    _, payment = _memo_and_payment(db, memo_id, account)
    dispute = service.get_or_404(db, payment.id)
    # The side that did not raise it is answering; the side that did is
    # adding to what they already said.
    kind = "response" if account.role != dispute.opened_by else "evidence"
    event = service.add_entry(
        db,
        dispute,
        actor_role=account.role,
        note=body.note,
        evidence_url=body.evidence_url,
        kind=kind,
        now=now,
    )
    return to_event_read(event)


@router.post(
    "/{memo_id}/payment/dispute/close",
    response_model=DisputeRead,
    summary="Record how the dispute ended",
    description=(
        "Either side may close it, at any point, including long after the "
        "thirty days. Most of these end with a phone call, and the record "
        "should be allowed to catch up with what really happened. None of "
        "the outcomes says who was right."
    ),
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("This dispute has already been closed"),
        422: problem_doc("That is not an outcome we record"),
    },
)
@rate_limit(WRITE_LIMIT)
def close_dispute(
    request: Request,
    memo_id: MemoId,
    body: DisputeClose,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> DisputeRead:
    """Either party may close it."""
    _, payment = _memo_and_payment(db, memo_id, account)
    dispute = service.get_or_404(db, payment.id)
    service.close(
        db,
        dispute,
        outcome=body.outcome,
        actor_role=account.role,
        note=body.note,
        now=now,
    )
    return _rendered(db, dispute, india_date(now))

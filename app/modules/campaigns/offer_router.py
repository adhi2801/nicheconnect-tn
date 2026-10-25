"""Counter-offers on a quote (HTTP, item 44, D-123). The rules: offer_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.campaigns import offer_service as service
from app.modules.campaigns.dependencies import VisibleApplication
from app.modules.campaigns.schemas import OfferCreate, OfferRead

READ_LIMIT = "60 per minute"
# A ceiling per day as well as per minute: an offer reaches the other side
# (trust-and-safety.md rule 2), as many as an invitation (D-084).
OFFER_LIMIT = "30 per minute;100 per day"
ANSWER_LIMIT = "30 per minute"

# route_class: a retry with the same Idempotency-Key gets the first answer,
# and no second offer is made (backend.md section 2).
router = APIRouter(prefix="/api/v1", tags=["applications"], route_class=IdempotentRoute)

OfferId = Annotated[uuid.UUID, Path(description="The offer's id")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    404: problem_doc("No such application or offer, or it is not yours"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_CLOSED = (
    "`offers_closed`: the application is no longer waiting, the campaign is "
    "barter, or the other side has gone; `campaign_not_open`; "
    "`offer_already_agreed`: a figure is agreed, so changes go through the memo"
)


@router.get(
    "/applications/{application_id}/offers",
    response_model=list[OfferRead],
    summary="The offers on an application",
    description=(
        "Every figure either side named on this application, oldest first, "
        "with how each was answered. Whole, not paged: at most 6, since each "
        "side makes at most 3. For the creator who applied and the brand whose "
        "campaign it is."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_offers(
    request: Request, application: VisibleApplication, db: Session = Depends(get_db)
) -> list[OfferRead]:
    return [OfferRead.model_validate(offer) for offer in service.history(db, application)]


@router.post(
    "/applications/{application_id}/offers",
    status_code=status.HTTP_201_CREATED,
    response_model=OfferRead,
    summary="Offer a figure on an application",
    description=(
        "Names a figure, in paise, on an application still waiting (submitted, "
        "shortlisted, or an invitation not yet answered), with an optional "
        "note. The other side is told, and accepts, declines or answers with "
        "an offer of its own, which replaces this one. Each side makes at most "
        "3 on one application, and one is open at a time: withdraw your own "
        "before making another. While an offer is open the application cannot "
        "be accepted, so the figure is settled first. Limits: 30 a minute and "
        "100 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            f"{_CLOSED}; `offer_limit_reached`: you have made 3; `offer_open`: "
            "your own offer still waits; `own_content_withheld`"
        ),
        422: problem_doc("The amount or the note is not valid"),
        451: problem_doc("The other side is withheld for legal reasons (item 52)"),
    },
)
@rate_limit(OFFER_LIMIT)
def make_offer(
    request: Request,
    response: Response,
    body: OfferCreate,
    application: VisibleApplication,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> OfferRead:
    offer = service.make_offer(
        db, application, account.role, body.amount_paise, body.note, now
    )
    response.headers["Location"] = f"/api/v1/applications/{application.id}/offers"
    return OfferRead.model_validate(offer)


@router.post(
    "/applications/{application_id}/offers/{offer_id}/accept",
    response_model=OfferRead,
    summary="Accept the other side's offer",
    description=(
        "Agrees the figure. It pre-fills the deal memo's fee; the memo is still "
        "the contract, and a different fee there is shown beside this one. "
        "Negotiation then closes."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            f"{_CLOSED}; `offer_already_answered`; `offer_not_yours_to_answer`: "
            "it is your own offer; `own_content_withheld`"
        ),
        451: problem_doc("The other side is withheld for legal reasons (item 52)"),
    },
)
@rate_limit(ANSWER_LIMIT)
def accept_offer(
    request: Request,
    offer_id: OfferId,
    application: VisibleApplication,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> OfferRead:
    return OfferRead.model_validate(
        service.accept(db, application, offer_id, account.role, now)
    )


@router.post(
    "/applications/{application_id}/offers/{offer_id}/decline",
    response_model=OfferRead,
    summary="Decline the other side's offer",
    description=(
        "Says no to the figure. The application waits on as it was, and either "
        "side may still make another offer while it can."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`offer_already_answered`; `offer_not_yours_to_answer`: it is your own offer"
        ),
    },
)
@rate_limit(ANSWER_LIMIT)
def decline_offer(
    request: Request,
    offer_id: OfferId,
    application: VisibleApplication,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> OfferRead:
    return OfferRead.model_validate(
        service.decline(db, application, offer_id, account.role, now)
    )


@router.delete(
    "/applications/{application_id}/offers/{offer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw my offer",
    description="Takes back your own offer while it waits. The other side is told.",
    responses={
        **_COMMON,
        409: problem_doc(
            "`offer_already_answered`; `offer_not_yours_to_answer`: it is the "
            "other side's offer, theirs to withdraw"
        ),
    },
)
@rate_limit(ANSWER_LIMIT)
def withdraw_offer(
    request: Request,
    offer_id: OfferId,
    application: VisibleApplication,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    service.withdraw(db, application, offer_id, account.role, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

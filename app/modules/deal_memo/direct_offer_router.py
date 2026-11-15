"""Direct offer endpoints (D-189). HTTP only: rules live in direct_offer_service.py.

Three groups:

- the creator's own: send, list, read one, withdraw (`/api/v1/direct-offers`);
- the link, public, for whoever holds it: read the offer, and "stop these"
  (`/api/v1/direct-offer-link`);
- the link's login: ask for the code, and accept with it
  (`/api/v1/auth/direct-offer-link`). Under `/auth/` because accepting
  makes an account and answers with its tokens, which, as login's, are
  never kept in the idempotency store.

The link's token travels in the `Offer-Token` header, never a path or a
query string, which the access log would keep (backend.md section 9).
Every route answers 503 `direct_offers_unavailable` while the feature is off.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    Path,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import service as login
from app.modules.auth.dependencies import get_now
from app.modules.auth.schemas import AccountSummary, OtpRequestAccepted
from app.modules.auth.sender import OtpSender, get_otp_sender
from app.modules.campaigns.dependencies import CurrentCreatorProfile
from app.modules.deal_memo import direct_offer_service as offers
from app.modules.deal_memo.direct_offer_models import DirectOffer
from app.modules.deal_memo.direct_offer_rules import shown_status
from app.modules.deal_memo.direct_offer_schemas import (
    DirectOfferAccepted,
    DirectOfferAcceptIn,
    DirectOfferCreate,
    DirectOfferLinkRead,
    DirectOfferRead,
    DirectOfferSent,
    OfferingCreator,
)

# A ceiling per day as well as per minute (trust-and-safety.md rule 2): the
# send reaches a person. The Tamil Nadu day's 10, and a number's 3 a week,
# are counted in the database (direct_offer_service.send).
SEND_LIMIT = "5 per minute;10 per day"
WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"
# The link is public: limited by address, as public pages are (security.md
# section 5); its code and acceptance as login's own (auth.router).
LINK_READ_LIMIT = "60 per minute"
LINK_STOP_LIMIT = "10 per 10 minutes"
CODE_LIMIT = "3 per 10 minutes"
ACCEPT_LIMIT = "10 per 10 minutes"

router = APIRouter(
    prefix="/api/v1/direct-offers", tags=["direct offers"], route_class=IdempotentRoute
)
# Sending is never replayed for an `Idempotency-Key`: its answer carries the
# link's token, which must never be kept in the idempotency store (as making
# an assistant's token, D-138). A retry sends a second offer, which the
# creator sees in their list and can withdraw.
send_router = APIRouter(prefix="/api/v1/direct-offers", tags=["direct offers"])
link_router = APIRouter(
    prefix="/api/v1/direct-offer-link",
    tags=["direct offers"],
    route_class=IdempotentRoute,
)
link_login_router = APIRouter(
    prefix="/api/v1/auth/direct-offer-link", tags=["direct offers"]
)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
DirectOfferId = Annotated[uuid.UUID, Path(description="The offer's id")]
OfferToken = Annotated[
    str,
    Header(
        alias="Offer-Token",
        min_length=1,
        max_length=128,
        description="The token from the offer's link (after its `#`)",
    ),
]

_OFF = problem_doc(
    "`direct_offers_unavailable`: direct offers are off until the notice wording exists"
)
_CREATOR_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only a creator sends direct offers"),
    409: problem_doc("The creator profile has not been created yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
    503: _OFF,
}
_ENDED = (
    "`direct_offer_expired` (its 14 days ran out), `direct_offer_withdrawn`, "
    "`direct_offer_stopped` or `direct_offer_already_accepted`"
)
_LINK_ERRORS: ResponseDocs = {
    404: problem_doc(
        "`direct_offer_not_found`: no offer has this token, or its creator is "
        "suspended or left"
    ),
    422: problem_doc("The `Offer-Token` header is missing or too long"),
    429: problem_doc("Too many requests; see the Retry-After header"),
    503: _OFF,
}


def _terms(offer: DirectOffer) -> dict[str, Any]:
    """The terms both views show, field by field: a column added later never leaks."""
    return {
        "deliverables": offer.deliverables,
        "deliverable_items": offer.deliverable_items,
        "fee_amount_paise": offer.fee_amount_paise,
        "currency": offer.currency,
        "cancellation_fee_paise": offer.cancellation_fee_paise,
        "approval_window_days": offer.approval_window_days,
        "payment_due_days": offer.payment_due_days,
        "usage_rights_days": offer.usage_rights_days,
        "content_due_on": offer.content_due_on,
        "disclosure_required": offer.disclosure_required,
        "draft_review": offer.draft_review,
        "extra_terms": offer.extra_terms,
        "terms_sha256": offer.terms_sha256,
    }


def to_read(offer: DirectOffer, now: datetime) -> DirectOfferRead:
    """An offer as its creator sees it."""
    shown = shown_status(offer.status, offer.expires_at, now)
    return DirectOfferRead.model_validate(
        {
            **_terms(offer),
            "id": offer.id,
            "status": shown,
            # Erased once it ended; an offer whose days ran out before the
            # job reached it shows none either.
            "brand_name": offer.brand_name if shown == "sent" else None,
            "sent_at": offer.created_at,
            "expires_at": offer.expires_at,
            "opened_at": offer.opened_at,
            "ended_at": offer.ended_at,
            "deal_memo_id": offer.deal_memo_id,
        }
    )


@send_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DirectOfferSent,
    summary="Send a direct offer to a brand not on the platform",
    description=(
        "Writes the terms a memo carries, for a brand named by its WhatsApp "
        "number, and answers with the link's token, shown this once: send the "
        "brand the link. It works for 14 days, until you withdraw it, or until "
        "the number's holder stops your offers. Only that number can accept, "
        "with a code we send it when they ask. Limits: 10 offers a Tamil Nadu "
        "day, and 3 in any 7 days to one number from anyone; 5 a minute. Never "
        "replayed for an `Idempotency-Key`: the answer carries the token, which "
        "is never kept."
    ),
    responses={
        **_CREATOR_ERRORS,
        409: problem_doc(
            "The creator profile has not been created yet; `due_date_has_passed`; "
            "`direct_offer_own_number` (your own number); "
            "`direct_offer_stopped_by_recipient` (the number stopped your offers); "
            "`creator_left`"
        ),
        422: problem_doc(
            "A field is missing or invalid; `due_date_too_far` (more than a year ahead)"
        ),
        429: problem_doc(
            "`direct_offer_daily_limit` (10 today), `direct_offer_number_limit` "
            "(3 this week to that number), or too many requests; see Retry-After"
        ),
    },
)
@rate_limit(SEND_LIMIT)
def send_direct_offer(
    request: Request,
    response: Response,
    body: DirectOfferCreate,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DirectOfferSent:
    sent = offers.send(db, creator, body.model_dump(), now)
    response.headers["Location"] = f"/api/v1/direct-offers/{sent.offer.id}"
    # The token is shown once: never cached by a browser or a proxy.
    response.headers["Cache-Control"] = "no-store"
    return DirectOfferSent(
        **to_read(sent.offer, now).model_dump(), link_token=sent.link_token
    )


@router.get(
    "",
    response_model=Page[DirectOfferRead],
    summary="List my direct offers",
    description=(
        "Your offers, newest first: sent, opened, accepted (with the deal), "
        "withdrawn, stopped or expired. An offer that ended without a deal is "
        "deleted 30 days after it ended, except a stopped one."
    ),
    responses={
        **_CREATOR_ERRORS,
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@rate_limit(READ_LIMIT)
def list_my_direct_offers(
    request: Request,
    creator: CurrentCreatorProfile,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Page[DirectOfferRead]:
    offers.ensure_on()
    result = offers.list_mine(db, creator, limit=limit, cursor=cursor)
    return Page[DirectOfferRead](
        items=[to_read(row, now) for row in result.rows], next_cursor=result.next_cursor
    )


@router.get(
    "/{direct_offer_id}",
    response_model=DirectOfferRead,
    summary="Read one of my direct offers",
    description="One of your own offers. Anyone else's, or none, is 404.",
    responses={
        **_CREATOR_ERRORS,
        404: problem_doc("`direct_offer_not_found`: no such offer of yours"),
        422: problem_doc("The offer id is not a UUID"),
    },
)
@rate_limit(READ_LIMIT)
def read_my_direct_offer(
    request: Request,
    direct_offer_id: DirectOfferId,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DirectOfferRead:
    offers.ensure_on()
    return to_read(offers.get_mine(db, creator, direct_offer_id), now)


@router.post(
    "/{direct_offer_id}/withdraw",
    response_model=DirectOfferRead,
    summary="Withdraw a direct offer",
    description=(
        "Takes back an offer still waiting: its link stops working at once, and "
        "the brand's number and name are erased."
    ),
    responses={
        **_CREATOR_ERRORS,
        404: problem_doc("`direct_offer_not_found`: no such offer of yours"),
        409: problem_doc(
            f"The creator profile has not been created yet, or the offer ended: {_ENDED}"
        ),
        422: problem_doc("The offer id is not a UUID"),
    },
)
@rate_limit(WRITE_LIMIT)
def withdraw_direct_offer(
    request: Request,
    direct_offer_id: DirectOfferId,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DirectOfferRead:
    offers.ensure_on()
    offer = offers.get_mine(db, creator, direct_offer_id)
    return to_read(offers.withdraw(db, offer, now), now)


@link_router.get(
    "",
    response_model=DirectOfferLinkRead,
    summary="Read the offer a link carries",
    description=(
        "Public: whoever holds the link reads who it is from (the creator's "
        "public name), the terms, and the notice to read before accepting. "
        "Nothing else: no number, no other deal. The first reading is shown "
        "to the creator as opened. The `terms_sha256` is what accepting names. "
        "Never cached. Limit: 60 a minute per address."
    ),
    responses={
        **_LINK_ERRORS,
        409: problem_doc(f"The offer no longer waits: {_ENDED}"),
    },
)
@rate_limit(LINK_READ_LIMIT)
def read_offer_link(
    request: Request,
    response: Response,
    offer_token: OfferToken,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DirectOfferLinkRead:
    view = offers.open_link(db, offer_token, now)
    offer = view.offer
    response.headers["Cache-Control"] = "no-store"
    return DirectOfferLinkRead.model_validate(
        {
            **_terms(offer),
            "creator": OfferingCreator(
                display_name=view.creator.display_name, handle=view.creator.handle
            ),
            "brand_name": offer.brand_name,
            "expires_at": offer.expires_at,
            "notice": offers.link_notice(),
        }
    )


@link_router.post(
    "/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop offers from this creator to my number",
    description=(
        "Public, no account needed: the link proves its holder received it. "
        "This creator can send this number no more direct offers, and this "
        "offer ends, its number and name erased. Works on a waiting, withdrawn "
        "or expired offer; a second tap changes nothing. "
        "Limit: 10 in 10 minutes per address."
    ),
    responses={
        **_LINK_ERRORS,
        409: problem_doc(
            "`direct_offer_already_accepted`: it became a deal; block the "
            "creator from the brand's account instead"
        ),
    },
)
@rate_limit(LINK_STOP_LIMIT)
def stop_offers(
    request: Request,
    offer_token: OfferToken,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    offers.stop(db, offer_token, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@link_login_router.post(
    "/code",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OtpRequestAccepted,
    summary="Send the code that accepts an offer",
    description=(
        "Sends a 6-digit code to the number the creator named, never to any "
        "other: the number is not shown, and needs no typing. The same caps as "
        "a login code: 3 codes in 10 minutes and 10 a day per number, and 3 "
        "requests in 10 minutes per address."
    ),
    responses={
        **_LINK_ERRORS,
        409: problem_doc(f"The offer no longer waits: {_ENDED}"),
        429: problem_doc("Too many codes requested; see the Retry-After header"),
    },
)
@rate_limit(CODE_LIMIT)
def request_offer_code(
    request: Request,
    offer_token: OfferToken,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    sender: OtpSender = Depends(get_otp_sender),
    now: datetime = Depends(get_now),
) -> OtpRequestAccepted:
    pending = offers.request_code(db, offer_token, now)
    background_tasks.add_task(login.deliver_otp, sender, pending)
    return OtpRequestAccepted(
        expires_in_seconds=int((pending.expires_at - now).total_seconds())
    )


@link_login_router.post(
    "/accept",
    response_model=DirectOfferAccepted,
    summary="Accept an offer: become a brand here, and agree the deal",
    description=(
        "The brand's one step: confirm its name, give an email and a date of "
        "birth (adults only, D-086; only the confirmation's time is kept), the "
        "code sent to the offer's number, and the `terms_sha256` it was shown. "
        "In one transaction this makes the brand's account and profile and the "
        "deal, agreed by both, its record sealed with the creator's proposal "
        "and this acceptance; then signs the brand in. "
        "Limit: 10 in 10 minutes per address; each code allows 5 attempts."
    ),
    responses={
        **_LINK_ERRORS,
        400: problem_doc("The code is wrong, expired, already used, or was never sent"),
        403: problem_doc("`account_suspended`: the number's other account is suspended"),
        409: problem_doc(
            f"The offer no longer waits: {_ENDED}; `direct_offer_terms_mismatch` "
            "(not the terms shown); `due_date_has_passed`; `brand_account_exists`; "
            "`direct_offer_own_number`; `email_taken`; `brand_name_needs_domain` "
            "(item 75); `role_mismatch`; `phone_change_waiting`. Each said only "
            "after the code was right, which stays unused"
        ),
        422: problem_doc("A field is missing or invalid; `must_be_18_or_over`"),
        429: problem_doc("Too many attempts; see the Retry-After header"),
    },
)
@rate_limit(ACCEPT_LIMIT)
def accept_offer(
    request: Request,
    response: Response,
    body: DirectOfferAcceptIn,
    offer_token: OfferToken,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> DirectOfferAccepted:
    accepted = offers.accept(db, offer_token, body.model_dump(), now)
    result = accepted.login
    # Tokens must never be cached by browsers or proxies.
    response.headers["Cache-Control"] = "no-store"
    return DirectOfferAccepted(
        access_token=result.access_token,
        expires_in=int((result.access_token_expires_at - now).total_seconds()),
        refresh_token=result.refresh_token,
        refresh_expires_in=int((result.refresh_token_expires_at - now).total_seconds()),
        account=AccountSummary(id=result.account_id, role=result.role, is_new=True),
        deal_memo_id=accepted.memo.id,
    )

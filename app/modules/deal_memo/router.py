"""Deal memo endpoints (D-024 to D-027). HTTP only: rules live in service.py."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.campaigns.dependencies import BrandApplication, CurrentCreatorProfile
from app.modules.campaigns.service import get_brand_for_account, get_creator_for_account
from app.modules.deal_memo import service
from app.modules.deal_memo.dependencies import BrandMemo, CreatorMemo, visible_memo_for_account
from app.modules.deal_memo.schemas import ChangeRequest, MemoCreate, MemoRead, MemoStatus, MemoUpdate

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/deal-memos", tags=["deal memos"])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
StatusFilter = Annotated[MemoStatus | None, Query(alias="status")]

_COMMON_ERRORS = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _page(result) -> Page[MemoRead]:
    return Page[MemoRead](
        items=[MemoRead.model_validate(row) for row in result.rows],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/for-application/{application_id}",
    status_code=status.HTTP_201_CREATED,
    response_model=MemoRead,
    summary="Draft a deal memo for an accepted application",
    description=(
        "Creates the memo as a draft, visible only to the brand until it is sent. "
        "Paid and local-business campaigns need a fee; barter campaigns must not "
        "have one. One memo per application."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such application, or it is not for your campaign"),
        409: problem_doc(
            "The application is not accepted, already has a memo, or the fee does "
            "not match the campaign type"
        ),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def create_memo(
    request: Request,
    response: Response,
    body: MemoCreate,
    application: BrandApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> MemoRead:
    memo = service.create_memo(db, application, body.model_dump(), now)
    response.headers["Location"] = f"/api/v1/deal-memos/{memo.id}"
    return MemoRead.model_validate(memo)


@router.get(
    "/mine",
    response_model=Page[MemoRead],
    summary="List my deal memos",
    description=(
        "For a brand, memos on its own campaigns, drafts included. For a creator, "
        "memos sent to them; drafts are not theirs to see."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        409: problem_doc("The profile has not been created yet"),
        422: problem_doc("A query parameter or the cursor is invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(READ_LIMIT)
def list_my_memos(
    request: Request,
    account: CurrentAccount,
    memo_status: StatusFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[MemoRead]:
    if account.role == "brand":
        brand = get_brand_for_account(db, account.id)
        result = service.list_for_brand(db, brand, limit=limit, cursor=cursor, status=memo_status)
    else:
        creator = get_creator_for_account(db, account.id)
        result = service.list_for_creator(
            db, creator, limit=limit, cursor=cursor, status=memo_status
        )
    return _page(result)


@router.get(
    "/{memo_id}",
    response_model=MemoRead,
    summary="Read one deal memo",
    description=(
        "The owning brand sees it in any status; the creator sees it once it has "
        "been sent. Anyone else gets 404."
    ),
    responses={**_COMMON_ERRORS, 404: problem_doc("No such memo, or not yours")},
)
@limiter.limit(READ_LIMIT)
def read_memo(
    request: Request,
    memo_id: uuid.UUID,
    account: CurrentAccount,
    db: Session = Depends(get_db),
) -> MemoRead:
    return MemoRead.model_validate(
        visible_memo_for_account(db, memo_id, account.id, account.role)
    )


@router.patch(
    "/{memo_id}",
    response_model=MemoRead,
    summary="Change a deal memo",
    description=(
        "Only while the brand holds it: a draft, or after the creator asked for a "
        "change. Once accepted the terms stop moving, so a creator can rely on "
        "what they agreed to."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such memo, or it is not yours"),
        409: problem_doc("The memo cannot be changed now, or the fee does not match the campaign"),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def update_memo(
    request: Request,
    body: MemoUpdate,
    memo: BrandMemo,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> MemoRead:
    changes = body.model_dump(exclude_unset=True)
    return MemoRead.model_validate(service.update_memo(db, memo, changes, now))


def _brand_move(action: str, new_status: str, summary: str, description: str):
    @router.post(
        f"/{{memo_id}}/{action}",
        response_model=MemoRead,
        summary=summary,
        description=description,
        name=f"memo_{action}",
        responses={
            **_COMMON_ERRORS,
            404: problem_doc("No such memo, or it is not yours"),
            409: problem_doc("The memo is not in a state where that is allowed"),
        },
    )
    @limiter.limit(WRITE_LIMIT)
    def endpoint(
        request: Request,
        memo: BrandMemo,
        db: Session = Depends(get_db),
        now: datetime = Depends(get_now),
    ) -> MemoRead:
        return MemoRead.model_validate(
            service.change_status(db, memo, new_status, now, actor="brand")
        )

    return endpoint


send_memo = _brand_move(
    "send",
    "sent",
    "Send the memo to the creator",
    "Moves a draft to sent, so the creator can read, accept or question it.",
)
cancel_memo_as_brand = _brand_move(
    "cancel",
    "cancelled",
    "Cancel the memo (brand)",
    (
        "Ends the deal. Before any work is submitted this is recorded as "
        "withdrawn_early and does not count against the brand; afterwards it does."
    ),
)


def _creator_move(action: str, new_status: str, summary: str, description: str):
    @router.post(
        f"/{{memo_id}}/{action}",
        response_model=MemoRead,
        summary=summary,
        description=description,
        name=f"memo_{action}",
        responses={
            **_COMMON_ERRORS,
            404: problem_doc("No such memo, or it was not sent to you"),
            409: problem_doc("The memo is not in a state where that is allowed"),
        },
    )
    @limiter.limit(WRITE_LIMIT)
    def endpoint(
        request: Request,
        memo: CreatorMemo,
        db: Session = Depends(get_db),
        now: datetime = Depends(get_now),
    ) -> MemoRead:
        return MemoRead.model_validate(
            service.change_status(db, memo, new_status, now, actor="creator")
        )

    return endpoint


accept_memo = _creator_move(
    "accept",
    "accepted",
    "Accept the memo",
    "Agrees to these terms. From here the work begins and the terms stop changing.",
)
decline_memo = _creator_move(
    "decline",
    "declined",
    "Decline the memo",
    "Says no to these terms. This is final; the brand can start a new memo.",
)
withdraw_memo_as_creator = _creator_move(
    "withdraw",
    "cancelled",
    "Withdraw from an accepted deal (creator)",
    (
        "Ends a deal the creator had accepted. Before any work is submitted this "
        "is withdrawn_early; afterwards it counts against the creator."
    ),
)


@router.post(
    "/{memo_id}/request-change",
    response_model=MemoRead,
    summary="Ask the brand to change the memo",
    description=(
        "Sends it back with a message. Only the first request restarts the "
        "approval clock (D-025), and the count says how many have been made."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such memo, or it was not sent to you"),
        409: problem_doc("The memo is not in a state where that is allowed"),
        422: problem_doc("The message is missing or too short"),
    },
)
@limiter.limit(WRITE_LIMIT)
def request_change(
    request: Request,
    body: ChangeRequest,
    memo: CreatorMemo,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> MemoRead:
    return MemoRead.model_validate(
        service.change_status(
            db, memo, "change_requested", now, actor="creator", message=body.message
        )
    )

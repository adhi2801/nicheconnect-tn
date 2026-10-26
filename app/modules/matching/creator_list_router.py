"""A brand's saved creator lists (HTTP, item 66, D-129). The rules: creator_list_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.campaigns.service import get_brand_for_account
from app.modules.deal_memo.schemas import to_delivery_read
from app.modules.matching import creator_list_service as service
from app.modules.matching import search_service
from app.modules.matching.creator_list_models import CreatorList
from app.modules.matching.schemas import CreatorListIn, CreatorListRead, ListedCreatorRead

READ_LIMIT = "60 per minute"
WRITE_LIMIT = "30 per minute"
# Reading a list reads creators' facts, as search does: search's ceiling, so
# a list is never a way round it (trust-and-safety.md rule 2).
CREATORS_LIMIT = "30 per minute;600 per day"

# route_class: a retry with the same Idempotency-Key gets the first answer.
router = APIRouter(
    prefix="/api/v1/creator-lists", tags=["creator search"], route_class=IdempotentRoute
)

ListId = Annotated[uuid.UUID, Path(description="The list's id")]
CreatorId = Annotated[uuid.UUID, Path(description="The creator's id")]
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Creators per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brands keep creator lists"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_NOT_FOUND: ResponseDocs = {404: problem_doc("No such list of yours")}


def _read(found: CreatorList, creators: int) -> CreatorListRead:
    return CreatorListRead(
        id=found.id,
        name=found.name,
        creators=creators,
        created_at=found.created_at,
        updated_at=found.updated_at,
    )


@router.get(
    "",
    response_model=list[CreatorListRead],
    summary="My creator lists",
    description=(
        "Every list you saved, newest first, each with how many of its "
        "creators you can find today. Whole, not paged: at most 50. Lists are "
        "yours alone; no creator is told they are on one."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_my_lists(
    request: Request, account: CurrentBrand, db: Session = Depends(get_db)
) -> list[CreatorListRead]:
    brand = get_brand_for_account(db, account.id)
    return [_read(found, count) for found, count in service.lists_of(db, brand)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreatorListRead,
    summary="Start a creator list",
    description="A new, empty list with a name of your own. At most 50 lists.",
    responses={
        **_COMMON,
        409: problem_doc(
            "`creator_lists_full`: you have 50; `creator_list_name_taken`: you have "
            "one by that name"
        ),
        422: problem_doc("The name is empty or too long"),
    },
)
@rate_limit(WRITE_LIMIT)
def start_a_list(
    request: Request,
    response: Response,
    body: CreatorListIn,
    account: CurrentBrand,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CreatorListRead:
    created = service.create(db, get_brand_for_account(db, account.id), body.name, now)
    response.headers["Location"] = f"/api/v1/creator-lists/{created.id}/creators"
    return _read(created, 0)


@router.patch(
    "/{list_id}",
    response_model=CreatorListRead,
    summary="Rename a creator list",
    description="A new name of your own; the creators on it stay as they are.",
    responses={
        **_COMMON,
        **_NOT_FOUND,
        409: problem_doc("`creator_list_name_taken`: you have one by that name"),
        422: problem_doc("The name is empty or too long"),
    },
)
@rate_limit(WRITE_LIMIT)
def rename_a_list(
    request: Request,
    list_id: ListId,
    body: CreatorListIn,
    account: CurrentBrand,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CreatorListRead:
    brand = get_brand_for_account(db, account.id)
    found = service.rename(db, service.own(db, brand, list_id), body.name, now)
    counts = {lst.id: n for lst, n in service.lists_of(db, brand)}
    return _read(found, counts.get(found.id, 0))


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a creator list",
    description="The list and every creator saved on it. The creators are not told.",
    responses={**_COMMON, **_NOT_FOUND},
)
@rate_limit(WRITE_LIMIT)
def remove_a_list(
    request: Request,
    list_id: ListId,
    account: CurrentBrand,
    db: Session = Depends(get_db),
) -> Response:
    service.remove(db, service.own(db, get_brand_for_account(db, account.id), list_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{list_id}/creators",
    response_model=Page[ListedCreatorRead],
    summary="The creators on a list",
    description=(
        "Each creator you can find today, latest saved first, with the same "
        "facts search shows, their delivery record (as `GET /api/v1/creators/"
        "{creator_id}/delivery-record` gives it) and when you saved them. One "
        "who has since "
        "unpublished, left, been suspended or withheld, or a block either way, "
        "is not shown. Pass `next_cursor` back as `cursor` for more."
    ),
    responses={
        **_COMMON,
        **_NOT_FOUND,
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@rate_limit(CREATORS_LIMIT)
def creators_on_a_list(
    request: Request,
    list_id: ListId,
    account: CurrentBrand,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Page[ListedCreatorRead]:
    brand = get_brand_for_account(db, account.id)
    found = service.own(db, brand, list_id)
    result = service.creators_in(db, brand, found, now, limit=limit, cursor=cursor)
    today = india_date(now)
    return Page[ListedCreatorRead](
        items=[
            ListedCreatorRead(
                **search_service.to_read(listed, today).model_dump(),
                saved_at=saved_at,
                delivery=to_delivery_read(record),
            )
            for listed, saved_at, record in result.rows
        ],
        next_cursor=result.next_cursor,
    )


@router.put(
    "/{list_id}/creators/{creator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Save a creator to a list",
    description=(
        "From search or your matches. Saving one already there changes "
        "nothing. At most 200 creators a list. The creator is not told."
    ),
    responses={
        **_COMMON,
        404: problem_doc(
            "No such list of yours, or no creator you can find (`creator_not_found`)"
        ),
        409: problem_doc("`creator_list_full`: the list holds 200"),
    },
)
@rate_limit(WRITE_LIMIT)
def save_a_creator(
    request: Request,
    list_id: ListId,
    creator_id: CreatorId,
    account: CurrentBrand,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> Response:
    brand = get_brand_for_account(db, account.id)
    service.add(db, brand, service.own(db, brand, list_id), creator_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{list_id}/creators/{creator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Take a creator off a list",
    description="One not on it is fine. The creator is not told.",
    responses={**_COMMON, **_NOT_FOUND},
)
@rate_limit(WRITE_LIMIT)
def take_a_creator_off(
    request: Request,
    list_id: ListId,
    creator_id: CreatorId,
    account: CurrentBrand,
    db: Session = Depends(get_db),
) -> Response:
    brand = get_brand_for_account(db, account.id)
    service.take_out(db, service.own(db, brand, list_id), creator_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

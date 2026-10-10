"""Blocking over HTTP (item 59). The rules: block_service and blocks.py."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import block_service as service
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.schemas import BlockCreate, BlockRead

# A ceiling per day as well as per minute (trust-and-safety.md rule 2).
WRITE_LIMIT = "30 per minute;200 per day"
READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["blocking"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.post(
    "/blocks",
    status_code=status.HTTP_201_CREATED,
    response_model=BlockRead,
    summary="Block a brand or a creator",
    description=(
        "A creator blocks a brand (`brand_id`, from any of its campaigns); a brand "
        "blocks a creator (`creator_id`, from search or matches). From then on, "
        "in both directions, no invitation, repeat or application can start, and "
        "neither appears in the other's search, suggestions or campaign "
        "discovery. Deals already agreed carry on: a block cannot undo a "
        "contract. **The other side is never told**, and anything they try reads "
        "as not found. Blocking twice is one block."
    ),
    responses={
        **_COMMON,
        404: problem_doc("Nobody with that id you could block"),
        422: problem_doc("Give brand_id or creator_id, exactly one"),
    },
)
@rate_limit(WRITE_LIMIT)
def block(
    request: Request,
    response: Response,
    body: BlockCreate,
    account: CurrentAccount,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> BlockRead:
    view = service.block(db, account, body.brand_id or body.creator_id, now)
    response.headers["Location"] = f"/api/v1/me/blocks/{view.id}"
    return BlockRead.model_validate(view, from_attributes=True)


@router.get(
    "/blocks",
    response_model=Page[BlockRead],
    summary="My blocks",
    description="Everyone you blocked, newest first. Never who blocked you.",
    responses={**_COMMON, 422: problem_doc("A query parameter or the cursor is invalid")},
)
@rate_limit(READ_LIMIT)
def list_blocks(
    request: Request,
    account: CurrentAccount,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> Page[BlockRead]:
    result = service.list_blocks(db, account, limit=limit, cursor=cursor)
    return Page[BlockRead](
        items=[BlockRead.model_validate(v, from_attributes=True) for v in result.rows],
        next_cursor=result.next_cursor,
    )


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock",
    description="Removes one of your blocks. The other side is not told.",
    responses={**_COMMON, 404: problem_doc("No such block, or it is not yours")},
)
@rate_limit(WRITE_LIMIT)
def unblock(
    request: Request,
    block_id: Annotated[uuid.UUID, Path(description="The block's id")],
    account: CurrentAccount,
    db: Session = Depends(get_db),
) -> Response:
    service.unblock(db, account, block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

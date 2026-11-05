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
from app.modules.auth.brand_access import BrandAccess
from app.modules.auth.brand_dependencies import AnyBrandAccess
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.safety import block_service as service
from app.modules.safety.schemas import BlockCreate, BlockRead

# A ceiling per day as well as per minute (trust-and-safety.md rule 2).
WRITE_LIMIT = "30 per minute;200 per day"
READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/me", tags=["blocking"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
# Someone on a brand's team blocks for the brand (D-148), as with every brand route.
_TEAM: ResponseDocs = {
    403: problem_doc(
        "`brand_role_not_allowed`: your role in the brand does not reach creators"
    ),
}


def _for_brand(access: BrandAccess | None) -> uuid.UUID | None:
    """The brand someone on a team blocks for; None for those who block as themselves."""
    return access.brand.id if access is not None else None


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
        "as not found. Blocking twice is one block. Someone on a brand's team "
        "blocks for the whole brand (owner, admin and campaign manager; send "
        "`Brand-Id` if you are in more than one)."
    ),
    responses={
        **_COMMON,
        **_TEAM,
        404: problem_doc(
            "Nobody with that id you could block, or `brand_not_found`: the "
            "Brand-Id header names a brand you are not in"
        ),
        422: problem_doc(
            "Give brand_id or creator_id, exactly one; or `brand_choice_needed`"
        ),
    },
)
@rate_limit(WRITE_LIMIT)
def block(
    request: Request,
    response: Response,
    body: BlockCreate,
    account: CurrentAccount,
    access: AnyBrandAccess,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> BlockRead:
    view = service.block(
        db, account, _for_brand(access), body.brand_id or body.creator_id, now
    )
    response.headers["Location"] = f"/api/v1/me/blocks/{view.id}"
    return BlockRead.model_validate(view, from_attributes=True)


@router.get(
    "/blocks",
    response_model=Page[BlockRead],
    summary="My blocks",
    description=(
        "Everyone you blocked, newest first; on a brand's team, everyone the "
        "brand blocked. Never who blocked you."
    ),
    responses={
        **_COMMON,
        404: problem_doc(
            "`brand_not_found`: the Brand-Id header names a brand you are not in"
        ),
        422: problem_doc(
            "A query parameter or the cursor is invalid; or `brand_choice_needed`"
        ),
    },
)
@rate_limit(READ_LIMIT)
def list_blocks(
    request: Request,
    account: CurrentAccount,
    access: AnyBrandAccess,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query()] = None,
    db: Session = Depends(get_db),
) -> Page[BlockRead]:
    result = service.list_blocks(
        db, account, _for_brand(access), limit=limit, cursor=cursor
    )
    return Page[BlockRead](
        items=[BlockRead.model_validate(v, from_attributes=True) for v in result.rows],
        next_cursor=result.next_cursor,
    )


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock",
    description=(
        "Removes one of your blocks, or, on a brand's team, one of the brand's. "
        "The other side is not told."
    ),
    responses={
        **_COMMON,
        **_TEAM,
        404: problem_doc("No such block, or it is not yours; or `brand_not_found`"),
        422: problem_doc("The block id is not a valid id; or `brand_choice_needed`"),
    },
)
@rate_limit(WRITE_LIMIT)
def unblock(
    request: Request,
    block_id: Annotated[uuid.UUID, Path(description="The block's id")],
    account: CurrentAccount,
    access: AnyBrandAccess,
    db: Session = Depends(get_db),
) -> Response:
    service.unblock(db, account, _for_brand(access), block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

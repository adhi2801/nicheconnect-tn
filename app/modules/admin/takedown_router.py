"""Withholding one item, and lifting it, for the admins (item 52). Rules in takedown_service.

Like every admin route, anyone who is not a signed-in, active admin gets 404.
"""

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
from app.modules.admin import takedown_clocks
from app.modules.admin import takedown_service as service
from app.modules.admin.schemas import AdminTakedownRead, LiftTakedownIn, TakedownCreate
from app.modules.auth.dependencies import CurrentAdmin, get_now
from app.modules.safety.takedown_models import Takedown

ADMIN_LIMIT = "60 per minute"

# route_class: an admin's repeated tap withholds or lifts once (D-040).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], route_class=IdempotentRoute)

_ERRORS: ResponseDocs = {
    404: problem_doc(
        "Not found, which is also the answer for anyone who is not an admin"
    ),
    422: problem_doc("A field is not valid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(takedown: Takedown) -> AdminTakedownRead:
    return AdminTakedownRead(
        id=takedown.id,
        subject_kind=takedown.subject_kind,
        subject_id=takedown.subject_id,
        owner_account_id=takedown.owner_account_id,
        basis=takedown.basis,
        issued_by=takedown.issued_by,
        order_reference=takedown.order_reference,
        legal_provision=takedown.legal_provision,
        reference_sealed=takedown.reference_sealed,
        report_id=takedown.report_id,
        received_at=takedown.received_at,
        due_at=takedown.due_at,
        withheld_at=takedown.withheld_at,
        late=takedown_clocks.is_late(takedown.due_at, takedown.withheld_at),
        withheld_by_account_id=takedown.withheld_by_account_id,
        lifted_at=takedown.lifted_at,
        lifted_by_account_id=takedown.lifted_by_account_id,
        preserved=takedown.preserved,
    )


@router.post(
    "/takedowns",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminTakedownRead,
    summary="Withhold one creator, brand or campaign",
    description=(
        "On a court order, or a government notice from an authorised officer, "
        "the IT Rules give us 3 hours from when it reached us (rule 3(1)(d)); "
        "or on a report, while an admin looks into it (the report keeps its "
        "own deadline). At once, everyone but the owner stops seeing the item: "
        "it leaves search, matches and discovery, and opening it answers 451. "
        "The owner keeps their account and sees it, deals already agreed carry "
        "on, and nothing new can start from it. The owner is told (unless the "
        "order is sealed, with its details). Its visible text is kept as it "
        "stands (`preserved`). `late` says it was withheld after `due_at`."
    ),
    responses={
        **_ERRORS,
        409: problem_doc("It is already withheld"),
    },
)
@rate_limit(ADMIN_LIMIT)
def withhold(
    request: Request,
    response: Response,
    body: TakedownCreate,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminTakedownRead:
    order = None
    if body.basis != "report":
        issued_by, order_reference, received_at = body.order_essentials()
        order = service.Order(
            basis=body.basis,
            issued_by=issued_by,
            order_reference=order_reference,
            legal_provision=body.legal_provision,
            reference_sealed=body.reference_sealed,
            received_at=received_at,
        )
    takedown = service.withhold(
        db,
        admin,
        subject_kind=body.subject_kind,
        subject_id=body.subject_id,
        order=order,
        report_id=body.report_id,
        note=body.note,
        now=now,
    )
    response.headers["Location"] = f"/api/v1/admin/takedowns/{takedown.id}"
    return _read(takedown)


@router.post(
    "/takedowns/{takedown_id}/lift",
    response_model=AdminTakedownRead,
    summary="Lift a takedown",
    description=(
        "Makes the item visible again, with a note for the admin log: the order "
        "withdrawn or set aside, or the report dismissed. The owner is told. "
        "The record and its preserved text stay."
    ),
    responses={**_ERRORS, 409: problem_doc("Already lifted")},
)
@rate_limit(ADMIN_LIMIT)
def lift(
    request: Request,
    takedown_id: Annotated[uuid.UUID, Path(description="The takedown's id")],
    body: LiftTakedownIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminTakedownRead:
    return _read(service.lift(db, admin, takedown_id, note=body.note, now=now))


@router.get(
    "/takedowns",
    response_model=Page[AdminTakedownRead],
    summary="Takedowns",
    description=(
        "Newest first. `active=true` keeps those still withheld; `active=false` "
        "those lifted; leave it out for both."
    ),
    responses=_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def list_takedowns(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[AdminTakedownRead]:
    page = service.list_takedowns(db, active=active, limit=limit, cursor=cursor)
    return Page(items=[_read(t) for t in page.rows], next_cursor=page.next_cursor)

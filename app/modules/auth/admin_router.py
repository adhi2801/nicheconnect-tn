"""The admin API (D-061). Rules and the log live in admin_service.

Anyone who is not a signed-in, active admin gets 404 on every route here,
exactly as for a path that does not exist, so the admin API cannot be found
by probing it. That includes a missing or expired token, a brand, a creator,
and a suspended admin.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.errors import DomainError, ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import admin_service as service
from app.modules.auth.dependencies import bearer_scheme, get_current_account, get_now
from app.modules.auth.exceptions import AdminNotFound, InvalidSearch
from app.modules.auth.models.account import Account
from app.modules.auth.schemas import (
    AdminAccountRead,
    AdminActionRead,
    AdminProfileRead,
    AdminReportRead,
    IndianMobile,
    ResolveReportIn,
    RestoreIn,
    SuspendIn,
)

ADMIN_LIMIT = "60 per minute"

# route_class: an admin's repeated tap suspends or resolves once (D-040).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], route_class=IdempotentRoute)

_ERRORS: ResponseDocs = {
    404: problem_doc(
        "Not found, which is also the answer for anyone who is not an admin"
    ),
    422: problem_doc("A field is not valid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def get_admin(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Account:
    """The signed-in admin, or 404 for anyone else."""
    try:
        account = get_current_account(request, credentials, db, now)
    except DomainError:
        raise AdminNotFound() from None
    if account.role != "admin":
        raise AdminNotFound()
    return account


CurrentAdmin = Annotated[Account, Depends(get_admin)]
AccountId = Annotated[uuid.UUID, Path(description="The account's id")]
Reason = Annotated[
    str,
    Query(
        min_length=3,
        max_length=200,
        description="Why you are looking. Written to the admin log with your name",
    ),
]


def _account_read(detail: service.AccountDetail) -> AdminAccountRead:
    account = detail.account
    profile = None
    if detail.brand is not None:
        profile = AdminProfileRead(
            kind="brand", id=detail.brand.id, name=detail.brand.name, handle=None
        )
    elif detail.creator is not None:
        profile = AdminProfileRead(
            kind="creator",
            id=detail.creator.id,
            name=detail.creator.display_name,
            handle=detail.creator.handle,
        )
    return AdminAccountRead(
        id=account.id,
        role=account.role,
        phone=account.phone,
        created_at=account.created_at,
        suspended_at=account.suspended_at,
        suspension_reason=account.suspension_reason,
        profile=profile,
        deals=detail.deals,
        reports_about_open=detail.reports_about_open,
        reports_about_total=detail.reports_about_total,
        reports_made=detail.reports_made,
    )


@router.get(
    "/accounts",
    response_model=list[AdminAccountRead],
    summary="Find an account by phone or creator handle",
    description=(
        "Give exactly one of `phone` or `handle`, and a `reason`. Every "
        "account returned is written to the admin log as viewed, with the reason."
    ),
    responses=_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def find_accounts(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    reason: Reason,
    phone: IndianMobile | None = None,
    handle: Annotated[str | None, Query(min_length=3, max_length=31)] = None,
) -> list[AdminAccountRead]:
    if (phone is None) == (handle is None):
        raise InvalidSearch("Give exactly one of phone or handle.")
    found = service.find_accounts(
        db, admin, phone=phone, handle=handle, reason=reason, now=now
    )
    return [_account_read(d) for d in found]


@router.get(
    "/accounts/{account_id}",
    response_model=AdminAccountRead,
    summary="Read one account",
    description="Written to the admin log as viewed, with the reason.",
    responses=_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def read_account(
    request: Request,
    account_id: AccountId,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    reason: Reason,
) -> AdminAccountRead:
    return _account_read(
        service.account_detail(db, admin, account_id, reason=reason, now=now)
    )


@router.post(
    "/accounts/{account_id}/suspend",
    response_model=AdminAccountRead,
    summary="Suspend an account",
    description=(
        "Stops the account at once and ends its sessions. Its existing deals "
        "stay usable by the other party. The person is told the reason's "
        "category, never the note. Admins cannot be suspended here."
    ),
    responses={**_ERRORS, 409: problem_doc("Already suspended, or an admin")},
)
@rate_limit(ADMIN_LIMIT)
def suspend_account(
    request: Request,
    account_id: AccountId,
    body: SuspendIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminAccountRead:
    service.suspend(db, admin, account_id, reason=body.reason, note=body.note, now=now)
    return _account_read(service.describe(db, db.get_one(Account, account_id)))


@router.post(
    "/accounts/{account_id}/restore",
    response_model=AdminAccountRead,
    summary="Lift a suspension",
    description=(
        "Clears the suspension so the account works again at once. The note "
        "goes to the admin log. Admins are restored by a founder, not here."
    ),
    responses={**_ERRORS, 409: problem_doc("Not suspended, or an admin")},
)
@rate_limit(ADMIN_LIMIT)
def restore_account(
    request: Request,
    account_id: AccountId,
    body: RestoreIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminAccountRead:
    service.restore(db, admin, account_id, note=body.note, now=now)
    return _account_read(service.describe(db, db.get_one(Account, account_id)))


@router.get(
    "/reports",
    response_model=Page[AdminReportRead],
    summary="The report queue",
    description="Oldest first, so the report waiting longest is handled first.",
    responses=_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def list_reports(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str, Query(pattern="^(open|actioned|dismissed)$")] = "open",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[AdminReportRead]:
    page = service.list_reports(db, status=status, limit=limit, cursor=cursor)
    return Page(
        items=[AdminReportRead.model_validate(r) for r in page.rows],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/reports/{report_id}/resolve",
    response_model=AdminReportRead,
    summary="Resolve a report",
    description=(
        "Marks an open report `actioned` or `dismissed`, with a note for the "
        "admin log. The reporter sees the outcome, never who decided it."
    ),
    responses={**_ERRORS, 409: problem_doc("Already resolved")},
)
@rate_limit(ADMIN_LIMIT)
def resolve_report(
    request: Request,
    report_id: Annotated[uuid.UUID, Path(description="The report's id")],
    body: ResolveReportIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminReportRead:
    report = service.resolve_report(
        db, admin, report_id, outcome=body.outcome, note=body.note, now=now
    )
    return AdminReportRead.model_validate(report)


@router.get(
    "/actions",
    response_model=Page[AdminActionRead],
    summary="The admin log",
    description=(
        "Newest first. With `account_id`, only entries about that account or "
        'by it: how to answer "who looked at my number, and why?".'
    ),
    responses=_ERRORS,
)
@rate_limit(ADMIN_LIMIT)
def list_actions(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    account_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[AdminActionRead]:
    page = service.list_actions(
        db, subject_account_id=account_id, limit=limit, cursor=cursor
    )
    return Page(
        items=[AdminActionRead.model_validate(a) for a in page.rows],
        next_cursor=page.next_cursor,
    )

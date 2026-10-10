"""My invite code, who joined with it (as counts), and sign-ups by source (D-080).

The first two are the signed-in person's own, with no id in the path, so
nobody can reach anyone else's. The third is for admins, counts only.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import attribution_service as attribution
from app.modules.auth.admin_router import CurrentAdmin
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.schemas import InviteCodeRead, InviteCountsRead, SignupCountRead

READ_LIMIT = "60 per minute"
ADMIN_LIMIT = "30 per minute"

router = APIRouter(prefix="/api/v1", tags=["invitations"])

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only brand and creator accounts invite people"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _inviter(account: CurrentAccount) -> None:
    if account.role not in ("brand", "creator"):
        raise RoleNotAllowed()


@router.get(
    "/me/invite-code",
    response_model=InviteCodeRead,
    summary="My invite code",
    description=(
        "The code to share with people you invite, made the first time it is "
        "asked for and the same ever after."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def my_invite_code(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> InviteCodeRead:
    _inviter(account)
    code = attribution.invite_code_for(db, account, now)
    return InviteCodeRead(code=code.code, created_at=code.created_at)


@router.get(
    "/me/invites",
    response_model=InviteCountsRead,
    summary="How many joined with my code",
    description="Counts of brands and creators only, never who they are.",
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def my_invites(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> InviteCountsRead:
    _inviter(account)
    counts = attribution.invites_by(db, account)
    return InviteCountsRead(brands=counts.brands, creators=counts.creators)


@router.get(
    "/admin/signups",
    response_model=list[SignupCountRead],
    summary="Sign-ups by source and week",
    description=(
        "New accounts per week (from Monday, Tamil Nadu time), per source and "
        "role, newest week first. Counts only: no account is named, so nothing "
        "is written to the admin log."
    ),
    responses={
        404: problem_doc(
            "Not found, which is also the answer for anyone who is not an admin"
        ),
        422: problem_doc("weeks is out of range"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(ADMIN_LIMIT)
def signups(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    weeks: Annotated[int, Query(ge=1, le=52, description="How many weeks back")] = 12,
) -> list[SignupCountRead]:
    return [
        SignupCountRead(
            week_starting=row.week_starting,
            source=row.source,
            role=row.role,
            accounts=row.accounts,
        )
        for row in attribution.signups_by_source(db, now, weeks=weeks)
    ]

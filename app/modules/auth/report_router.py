"""Users reporting a creator, a brand or a campaign (D-061). Rules in report_service."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import per_account, rate_limit
from app.db.session import get_db
from app.modules.auth import report_service
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.exceptions import RoleNotAllowed
from app.modules.auth.schemas import ReportCreate, ReportRead

# Per account, not per address: reporting must not become a way to flood the
# queue, and an office sharing one address is not one person.
REPORT_LIMIT = "10 per hour"

# route_class: a tap repeated on a bad connection files one report (D-040).
router = APIRouter(
    prefix="/api/v1/reports", tags=["reports"], route_class=IdempotentRoute
)

_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Admins do not file reports"),
    404: problem_doc("There is nothing with that id to report"),
    422: problem_doc("A field is not valid, or you reported yourself"),
    429: problem_doc("Too many reports; see the Retry-After header"),
}


@router.post(
    "",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    summary="Report a creator, a brand or a campaign",
    description=(
        "Flags it for an admin to look at. Reporting the same thing again "
        "while your first report is still open changes nothing and answers "
        "200 with that report, rather than 201. You cannot report yourself. "
        "At most 10 reports an hour."
    ),
    responses={
        **_ERRORS,
        200: {
            "description": "You had already reported this; unchanged",
            "model": ReportRead,
        },
    },
)
@rate_limit(REPORT_LIMIT, key=per_account)
def file_report(
    request: Request,
    response: Response,
    body: ReportCreate,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> ReportRead:
    if account.role == "admin":
        raise RoleNotAllowed()
    filed = report_service.file_report(
        db,
        account,
        subject_kind=body.subject_kind,
        subject_id=body.subject_id,
        category=body.category,
        note=body.note,
        now=now,
    )
    if filed.already_open:
        response.status_code = status.HTTP_200_OK
    return ReportRead.model_validate(filed.report)

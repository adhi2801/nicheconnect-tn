"""The report queue against its legal clocks, for the admins (item 51). Rules in report_clock_service.

Like every admin route, anyone who is not a signed-in, active admin gets 404.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.admin import report_clock_service as service
from app.modules.admin.schemas import ReportClockRead, ReportClocksRead
from app.modules.auth.dependencies import CurrentAdmin, get_now

READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_ERRORS: ResponseDocs = {
    404: problem_doc(
        "Not found, which is also the answer for anyone who is not an admin"
    ),
    422: problem_doc("A query parameter is not valid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/reports/clocks",
    response_model=ReportClocksRead,
    summary="The report queue against its legal clocks",
    description=(
        "How many reports are open, how many are past their deadline now, the "
        "next deadline, and how many of those answered in the last `days` days "
        "were answered in time. The IT Rules give each category its clock "
        "(item 51): listed in `clocks`. Totals only."
    ),
    responses=_ERRORS,
)
@rate_limit(READ_LIMIT)
def read_clocks(
    request: Request,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    days: Annotated[int, Query(ge=1, le=service.MAX_DAYS)] = 30,
) -> ReportClocksRead:
    figures = service.figures(db, now=now, days=days)
    return ReportClocksRead(
        as_of=figures.as_of,
        open=figures.open,
        open_late=figures.open_late,
        next_due_at=figures.next_due_at,
        days=figures.days,
        answered=figures.answered,
        answered_in_time=figures.answered_in_time,
        answered_in_time_share=figures.answered_in_time_share,
        clocks=[
            ReportClockRead.model_validate(
                {"category": category, "answer_within_hours": hours}
            )
            for category, hours in figures.clocks
        ],
    )

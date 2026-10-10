"""The founders' weekly numbers over HTTP (item 63). The rules: numbers_service."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.clock import india_date
from app.core.errors import ResponseDocs, problem_doc
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth import numbers_service as service
from app.modules.auth.admin_router import CurrentAdmin
from app.modules.auth.dependencies import get_now
from app.modules.auth.schemas import FounderNumbersRead

# Each answer is several aggregate queries over the whole platform, run
# twice, so fewer than the admin's other reads.
NUMBERS_LIMIT = "20 per minute"

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_ERRORS: ResponseDocs = {
    404: problem_doc(
        "Not found, which is also the answer for anyone who is not an admin"
    ),
    422: problem_doc("A query parameter is not valid"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


@router.get(
    "/numbers",
    response_model=FounderNumbersRead,
    summary="The founders' weekly numbers",
    description=(
        "How dense the market is and whether the business is alive, for a period "
        "of 1 to 90 Tamil Nadu days ending on `ending_on` (today by default), "
        "beside the same length before it. Campaign fill rate, time to a first "
        "application, application success, repeat deals, payments on time, and "
        "active brands and creators. **Every rate is null below five examples**, "
        "and a campaign counts towards the fill rate only once it is 14 days old. "
        "Optionally for one city. Totals only. Admins only; anyone else gets 404."
    ),
    responses=_ERRORS,
)
@rate_limit(NUMBERS_LIMIT)
def founder_numbers(
    request: Request,
    admin: CurrentAdmin,
    now: Annotated[datetime, Depends(get_now)],
    db: Annotated[Session, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=service.MAX_DAYS)] = 7,
    ending_on: Annotated[
        date | None, Query(description="Last day of the period; today if left out")
    ] = None,
    city: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
) -> FounderNumbersRead:
    numbers = service.founder_numbers(
        db, ending_on=ending_on or india_date(now), days=days, city=city
    )
    return FounderNumbersRead.model_validate(numbers, from_attributes=True)

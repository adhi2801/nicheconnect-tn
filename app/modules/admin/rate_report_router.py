"""Publishing the quarterly city rate report, for the admins (HTTP; item 84, D-200).

Rules: `insights.rate_report_service`; the admin log: `admin.rate_report_service`.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.admin import rate_report_service as service
from app.modules.auth.dependencies import CurrentAdmin, get_now
from app.modules.insights.rate_report_models import QUARTER_PATTERN, CityRateReport
from app.modules.insights.rate_report_schemas import (
    AdminRateReportRead,
    WithdrawRateReportIn,
)

ADMIN_WRITE_LIMIT = "30 per minute"

# route_class: an admin's repeated tap publishes or withdraws once (D-040).
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], route_class=IdempotentRoute)

Quarter = Annotated[
    str,
    Path(
        pattern=QUARTER_PATTERN,
        description="A quarter of the Tamil Nadu calendar, `YYYY-Qn`",
        examples=["2026-Q4"],
    ),
]


def _errors(conflicts: str) -> ResponseDocs:
    return {
        404: problem_doc(
            "`rate_report_not_built`; also the answer for anyone who is not an admin"
        ),
        409: problem_doc(conflicts),
        422: problem_doc("That is not a quarter, or the reason is missing or too short"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    }


def _read(report: CityRateReport) -> AdminRateReportRead:
    return AdminRateReportRead(
        quarter=report.quarter,
        method_version=report.method_version,
        built_at=report.built_at,
        published_at=report.published_at,
        withdrawn_at=report.withdrawn_at,
        withdrawn_reason=report.withdrawn_reason,
        body_sha256=report.body_sha256,
    )


@router.post(
    "/rate-reports/{quarter}/publish",
    response_model=AdminRateReportRead,
    summary="Publish a quarter's city rate report",
    description=(
        "Makes a built report public, after an admin has read it. From then on "
        "nothing it says can change: the database refuses it. Written to the "
        "admin log. Limit: 30 requests per minute."
    ),
    responses=_errors("`rate_report_already_published`"),
)
@rate_limit(ADMIN_WRITE_LIMIT)
def publish_rate_report(
    request: Request,
    quarter: Quarter,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminRateReportRead:
    return _read(service.publish(db, admin, quarter, now))


@router.post(
    "/rate-reports/{quarter}/withdraw",
    response_model=AdminRateReportRead,
    summary="Withdraw a published city rate report",
    description=(
        "For a report found wrong after publishing: readers then get 410 with "
        "the reason, and the archive lists it as withdrawn. Its figures stay "
        "as they were, never rewritten; a corrected report comes as a new "
        "method version. Once only. Written to the admin log with the reason. "
        "Limit: 30 requests per minute."
    ),
    responses=_errors("`rate_report_not_published` or `rate_report_already_withdrawn`"),
)
@rate_limit(ADMIN_WRITE_LIMIT)
def withdraw_rate_report(
    request: Request,
    quarter: Quarter,
    body: WithdrawRateReportIn,
    admin: CurrentAdmin,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> AdminRateReportRead:
    return _read(service.withdraw(db, admin, quarter, body.reason, now))

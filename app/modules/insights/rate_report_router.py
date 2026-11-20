"""The quarterly city rate report, readable without logging in (HTTP; item 84, D-200).

Public by design, like city figures: hand-built responses, nothing that
depends on who is asking, a cache header and an ETag. A published report
never changes (the database refuses it), so it is cached for a day. The
rules are `rate_report_service`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.http_cache import etag_for, holds_current
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.insights import rate_report_service as service
from app.modules.insights.rate_report_models import QUARTER_PATTERN, CityRateReport
from app.modules.insights.rate_report_schemas import (
    RateReportBody,
    RateReportRead,
    RateReportSummaryRead,
)

# A published report never changes, so a day is safe; the list changes only
# when a report is published or withdrawn, so a day there too is at worst a
# day late (backend.md section 6). Invalidation: the ETag hashes the answer.
CACHE_SECONDS = 86_400
PUBLIC_READ_LIMIT = "60 per minute"

router = APIRouter(prefix="/api/v1/rate-reports", tags=["public"])

Quarter = Annotated[
    str,
    Path(
        pattern=QUARTER_PATTERN,
        description="A quarter of the Tamil Nadu calendar, `YYYY-Qn`",
        examples=["2026-Q4"],
    ),
]

_ERRORS: ResponseDocs = {
    429: problem_doc("Too many requests; see the Retry-After header")
}


def _cached(
    body: BaseModel, response: Response, if_none_match: str | None
) -> Response | None:
    """Set the cache headers; a 304 when the reader already has this answer."""
    etag = etag_for(body.model_dump_json().encode())
    headers = {"Cache-Control": f"public, max-age={CACHE_SECONDS}", "ETag": etag}
    if holds_current(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return None


def _summary(report: CityRateReport) -> RateReportSummaryRead:
    published_at = report.published_at
    if published_at is None:  # the service lists published reports only
        raise ValueError("an unpublished report reached the public list")
    return RateReportSummaryRead(
        quarter=report.quarter,
        method_version=report.method_version,
        published_at=published_at,
        withdrawn_at=report.withdrawn_at,
        body_sha256=report.body_sha256,
    )


@router.get(
    "",
    response_model=Page[RateReportSummaryRead],
    summary="Published quarterly rate reports",
    description=(
        "Every published quarterly city rate report, newest first, withdrawn "
        "ones included with when they were withdrawn. Paged with `cursor`. "
        "Cached for a day, with an ETag. Limit: 60 requests per minute."
    ),
    responses={**_ERRORS, 422: problem_doc("A limit out of range, or a bad cursor")},
)
@rate_limit(PUBLIC_READ_LIMIT)
def list_rate_reports(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    if_none_match: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Response | Page[RateReportSummaryRead]:
    """Anyone may call this."""
    found = service.published(db, limit=limit, cursor=cursor)
    body = Page[RateReportSummaryRead](
        items=[_summary(report) for report in found.rows], next_cursor=found.next_cursor
    )
    return _cached(body, response, if_none_match) or body


@router.get(
    "/{quarter}",
    response_model=RateReportRead,
    summary="One quarter's city rate report",
    description=(
        "What creators ask by city, platform and format, and statewide by "
        "audience band, for one closed quarter, from anonymous figures: each "
        "creator counted once, every figure rounded to the nearest ₹100, and "
        "`null` wherever too few are behind it, meaning **not enough to say**, "
        "never zero. Agreed fees appear only in a report built with them "
        "(`agreed_fees_included`). A published report never changes; "
        "`body_sha256` lets any copy be checked. A withdrawn report answers "
        "410 with why. Cached for a day, with an ETag. Limit: 60 requests per "
        "minute."
    ),
    responses={
        **_ERRORS,
        404: problem_doc("No report is published for that quarter"),
        410: problem_doc("`rate_report_withdrawn`: the detail says why"),
        422: problem_doc("That is not a quarter (`YYYY-Qn`)"),
    },
)
@rate_limit(PUBLIC_READ_LIMIT)
def read_rate_report(
    request: Request,
    response: Response,
    quarter: Quarter,
    if_none_match: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> Response | RateReportRead:
    """Anyone may call this. Nothing here depends on who is asking."""
    report = service.read_published(db, quarter)
    if report.published_at is None:  # read_published returns published reports only
        raise ValueError("an unpublished report reached a public read")
    body = RateReportRead(
        quarter=report.quarter,
        method_version=report.method_version,
        method_url=service.METHOD_URL,
        built_at=report.built_at,
        published_at=report.published_at,
        body_sha256=report.body_sha256,
        body=RateReportBody.model_validate(report.body),
    )
    return _cached(body, response, if_none_match) or body

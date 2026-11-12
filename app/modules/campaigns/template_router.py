"""Festival campaign templates, over HTTP (item 14, piece 1, D-161, D-165)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import TypeAdapter

from app.core.clock import end_of_india_day, india_date
from app.core.errors import problem_doc
from app.core.http_cache import etag_for, holds_current
from app.core.rate_limit import rate_limit
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import festival_templates
from app.modules.campaigns.template_schemas import CampaignTemplateRead, to_template_read

PUBLIC_READ_LIMIT = "60 per minute"
# Cached until midnight in Tamil Nadu, when the order can change (backend.md section 6).
# TTL: to that midnight, never less than a minute. Invalidation: the ETag hashes the
# answer itself, so a deploy that changes a template is a new ETag at once for a reader
# who asks again, and a 304 otherwise.
MIN_CACHE_SECONDS = 60

router = APIRouter(prefix="/api/v1/campaign-templates", tags=["public"])
_BODY = TypeAdapter(list[CampaignTemplateRead])


def seconds_to_india_midnight(now: datetime) -> int:
    midnight = end_of_india_day(india_date(now))
    return max(MIN_CACHE_SECONDS, int((midnight - now).total_seconds()))


@router.get(
    "",
    response_model=list[CampaignTemplateRead],
    summary="Festival campaign templates",
    description=(
        "Campaigns already worded for Tamil Nadu's festivals and seasons, of every faith "
        "and none, each with its next dates. Ordered only by date: the one to publish "
        "soonest first (`publish_by`), so one already under way leads. Each is a starting "
        "point: add the brand's cities and, for a paid campaign, a budget, then create it "
        "with `POST /api/v1/campaigns`. `dates_confirmed` is false for dates that are "
        "expected rather than notified, and `depends_on_moon` marks a day set by the moon "
        "being sighted. No login. Cached until midnight in Tamil Nadu, with an ETag. "
        "Limit: 60 a minute."
    ),
    responses={
        304: {"description": "The reader's copy, named by `If-None-Match`, is current"},
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@rate_limit(PUBLIC_READ_LIMIT)
def campaign_templates(
    request: Request,
    response: Response,
    if_none_match: Annotated[str | None, Header()] = None,
    now: datetime = Depends(get_now),
) -> Response | list[CampaignTemplateRead]:
    body = [
        to_template_read(t, o) for t, o in festival_templates.upcoming(india_date(now))
    ]
    etag = etag_for(_BODY.dump_json(body))
    headers = {
        "Cache-Control": f"public, max-age={seconds_to_india_midnight(now)}",
        "ETag": etag,
    }
    if holds_current(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return body

"""Festival campaign templates, over HTTP (item 14, piece 1, D-161)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response

from app.core.clock import india_date
from app.core.errors import problem_doc
from app.core.rate_limit import rate_limit
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import festival_templates
from app.modules.campaigns.template_schemas import CampaignTemplateRead, to_template_read

PUBLIC_READ_LIMIT = "60 per minute"
# A day: the order only changes when the month does.
CACHE_SECONDS = 86_400

router = APIRouter(prefix="/api/v1/campaign-templates", tags=["public"])


@router.get(
    "",
    response_model=list[CampaignTemplateRead],
    summary="Festival campaign templates",
    description=(
        "Campaigns already worded for Tamil Nadu's festivals and seasons, the "
        "soonest first from today in Tamil Nadu. Each is a starting point: add the "
        "brand's cities and, for a paid campaign, a budget, then create it with "
        "`POST /api/v1/campaigns`. A festival that follows the moon lists no months "
        "and comes last. A fixed list of 11; no login. Cached for a day. Limit: 60 a minute."
    ),
    responses={429: problem_doc("Too many requests; see the Retry-After header")},
)
@rate_limit(PUBLIC_READ_LIMIT)
def campaign_templates(
    request: Request, response: Response, now: datetime = Depends(get_now)
) -> list[CampaignTemplateRead]:
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return [to_template_read(t) for t in festival_templates.upcoming(india_date(now))]

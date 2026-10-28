"""A creator's campaign alerts (HTTP, item 43, D-130). The rules: alert_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentCreator, get_now
from app.modules.campaigns import alert_service as service
from app.modules.campaigns.alert_models import CampaignAlert
from app.modules.campaigns.schemas import CampaignAlertIn, CampaignAlertRead
from app.modules.campaigns.service import get_creator_for_account

READ_LIMIT = "60 per minute"
WRITE_LIMIT = "30 per minute"

URL = "/api/v1/me/campaign-alerts"

# route_class: a retry with the same Idempotency-Key gets the first answer.
router = APIRouter(prefix=URL, tags=["campaigns"], route_class=IdempotentRoute)

AlertId = Annotated[uuid.UUID, Path(description="The alert's id")]

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("Only creators keep campaign alerts"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(alert: CampaignAlert) -> CampaignAlertRead:
    return CampaignAlertRead(
        id=alert.id,
        city=alert.city,
        niche=alert.niche,
        campaign_type=alert.campaign_type,
        min_budget_paise=alert.min_budget_paise,
        currency="INR",
        created_at=alert.created_at,
    )


@router.get(
    "",
    response_model=list[CampaignAlertRead],
    summary="My campaign alerts",
    description=(
        "Every alert you saved, newest first. Whole, not paged: at most 5. When a "
        "campaign is published that fits one, you are told within a few minutes "
        "(`campaign_alert`, which you can mute), at most 20 a day."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def list_my_alerts(
    request: Request, account: CurrentCreator, db: Session = Depends(get_db)
) -> list[CampaignAlertRead]:
    creator = get_creator_for_account(db, account.id)
    return [_read(alert) for alert in service.alerts_of(db, creator)]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CampaignAlertRead,
    summary="Save a campaign alert",
    description=(
        "Any mix of a city (in any case), a niche, a campaign type and a least "
        "budget; each one named must fit, and one left out fits anything. Name at "
        "least one. Campaigns already open are not alerted; browse them instead."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`campaign_alerts_full`: you have 5; `campaign_alert_exists`: you have "
            "one with these terms"
        ),
        422: problem_doc("No term named, a term out of range, or a budget on barter"),
    },
)
@rate_limit(WRITE_LIMIT)
def save_an_alert(
    request: Request,
    response: Response,
    body: CampaignAlertIn,
    account: CurrentCreator,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CampaignAlertRead:
    alert = service.create(
        db,
        get_creator_for_account(db, account.id),
        city=body.city,
        niche=body.niche,
        campaign_type=body.campaign_type,
        min_budget_paise=body.min_budget_paise,
        now=now,
    )
    response.headers["Location"] = URL
    return _read(alert)


@router.delete(
    "/{alert_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a campaign alert",
    description="Notices it already sent stay in your notifications.",
    responses={**_COMMON, 404: problem_doc("No such alert of yours")},
)
@rate_limit(WRITE_LIMIT)
def remove_an_alert(
    request: Request,
    alert_id: AlertId,
    account: CurrentCreator,
    db: Session = Depends(get_db),
) -> Response:
    service.remove(db, get_creator_for_account(db, account.id), alert_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

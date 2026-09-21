"""HTTP endpoints for campaigns (D-016). HTTP only: rules live in service.py."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, Slice
from app.core.rate_limit import limiter
from app.core.taxonomy import Niche
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentAccount, get_now
from app.modules.auth.models.brand import Brand
from app.modules.campaigns import service
from app.modules.campaigns.dependencies import CurrentBrandProfile, OwnedCampaign
from app.modules.campaigns.exceptions import CampaignNotFound
from app.modules.campaigns.models import Campaign
from app.modules.campaigns.schemas import (
    CampaignCreate,
    CampaignRead,
    CampaignStatus,
    CampaignType,
    CampaignUpdate,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

router = APIRouter(
    prefix="/api/v1/campaigns", tags=["campaigns"], route_class=IdempotentRoute
)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]


def _page(result: Slice[Campaign]) -> Page[CampaignRead]:
    return Page[CampaignRead](
        items=[CampaignRead.model_validate(row) for row in result.rows],
        next_cursor=result.next_cursor,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CampaignRead,
    summary="Create a campaign (as a draft)",
    description=(
        "Creates a campaign owned by the signed-in brand. It starts as a draft "
        "and is not visible to creators until it is published."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc("Only brand accounts can post campaigns"),
        409: problem_doc("The brand profile has not been created yet"),
        422: problem_doc("A field is missing or invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(WRITE_LIMIT)
def create_campaign(
    request: Request,
    response: Response,
    body: CampaignCreate,
    brand: CurrentBrandProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CampaignRead:
    campaign = service.create_campaign(db, brand, body.model_dump(), now)
    response.headers["Location"] = f"/api/v1/campaigns/{campaign.id}"
    return CampaignRead.model_validate(campaign)


@router.get(
    "",
    response_model=Page[CampaignRead],
    summary="List my campaigns",
    description="Every campaign owned by the signed-in brand, newest first.",
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc("Only brand accounts have campaigns of their own"),
        409: problem_doc("The brand profile has not been created yet"),
        422: problem_doc("A query parameter or the cursor is invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(READ_LIMIT)
def list_my_campaigns(
    request: Request,
    brand: CurrentBrandProfile,
    campaign_status: Annotated[CampaignStatus | None, Query(alias="status")] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[CampaignRead]:
    return _page(
        service.list_brand_campaigns(
            db, brand, limit=limit, cursor=cursor, status=campaign_status
        )
    )


@router.get(
    "/discover",
    response_model=Page[CampaignRead],
    summary="Browse open campaigns",
    description=(
        "Open campaigns, newest first, for any signed-in account. Filters are "
        "optional and combine: city, niche, type and a minimum budget in paise."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        422: problem_doc("A query parameter or the cursor is invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(READ_LIMIT)
def discover_campaigns(
    request: Request,
    account: CurrentAccount,
    city: Annotated[str | None, Query(min_length=2, max_length=60)] = None,
    niche: Niche | None = None,
    campaign_type: CampaignType | None = None,
    min_budget_paise: Annotated[int | None, Query(ge=1)] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[CampaignRead]:
    return _page(
        service.discover_campaigns(
            db,
            limit=limit,
            cursor=cursor,
            city=city,
            niche=niche,
            campaign_type=campaign_type,
            min_budget_paise=min_budget_paise,
        )
    )


@router.get(
    "/{campaign_id}",
    response_model=CampaignRead,
    summary="Read one campaign",
    description=(
        "The owning brand sees its campaign in any status. Everyone else sees "
        "it only while it is open; otherwise the answer is 404, so drafts stay private."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        404: problem_doc("No such campaign, or it is not visible to you"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(READ_LIMIT)
def read_campaign(
    request: Request,
    campaign_id: uuid.UUID,
    account: CurrentAccount,
    db: Session = Depends(get_db),
) -> CampaignRead:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise CampaignNotFound()
    # A campaign that is not open is visible to its owner only.
    if campaign.status != "open":
        owner_account_id = db.scalar(
            select(Brand.account_id).where(Brand.id == campaign.brand_id)
        )
        if owner_account_id != account.id:
            raise CampaignNotFound()
    return CampaignRead.model_validate(campaign)


@router.patch(
    "/{campaign_id}",
    response_model=CampaignRead,
    summary="Change a campaign",
    description=(
        "A draft can be changed completely. While a campaign is open, only the "
        "description, deliverables and closing date may change, so the offer "
        "creators applied to stays the same. Closed and cancelled campaigns cannot change."
    ),
    responses={
        401: problem_doc("No access token, or it is invalid or expired"),
        403: problem_doc("Only brand accounts can change campaigns"),
        404: problem_doc("No such campaign, or it is not yours"),
        409: problem_doc("The campaign, or that field, cannot be changed now"),
        422: problem_doc("A field is missing or invalid"),
        429: problem_doc("Too many requests; see the Retry-After header"),
    },
)
@limiter.limit(WRITE_LIMIT)
def update_campaign(
    request: Request,
    body: CampaignUpdate,
    campaign: OwnedCampaign,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> CampaignRead:
    changes = body.model_dump(exclude_unset=True)
    return CampaignRead.model_validate(
        service.update_campaign(db, campaign, changes, now)
    )


def _status_endpoint(
    action: str, new_status: str, summary: str, description: str
) -> Callable[..., Any]:
    @router.post(
        f"/{{campaign_id}}/{action}",
        response_model=CampaignRead,
        summary=summary,
        description=description,
        name=f"campaign_{action}",
        responses={
            401: problem_doc("No access token, or it is invalid or expired"),
            403: problem_doc("Only brand accounts can do this"),
            404: problem_doc("No such campaign, or it is not yours"),
            409: problem_doc("The campaign is not in a state where that is allowed"),
            429: problem_doc("Too many requests; see the Retry-After header"),
        },
    )
    @limiter.limit(WRITE_LIMIT)
    def endpoint(
        request: Request,
        campaign: OwnedCampaign,
        db: Session = Depends(get_db),
        now: datetime = Depends(get_now),
    ) -> CampaignRead:
        return CampaignRead.model_validate(
            service.change_status(db, campaign, new_status, now)
        )

    return endpoint


publish_campaign = _status_endpoint(
    "publish",
    "open",
    "Publish a campaign",
    "Moves a draft to open, so creators can see and apply to it.",
)
close_campaign = _status_endpoint(
    "close",
    "closed",
    "Close a campaign",
    "Stops new applications. A closed campaign cannot reopen; post a new one instead.",
)
cancel_campaign = _status_endpoint(
    "cancel",
    "cancelled",
    "Cancel a campaign",
    "Cancels a draft or open campaign. This cannot be undone.",
)

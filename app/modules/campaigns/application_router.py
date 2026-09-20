"""Application endpoints: creators apply, brands decide (D-016).

Kept apart from the campaign routes so each file has one job. Both live in
the campaigns module.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import service
from app.modules.campaigns.dependencies import (
    BrandApplication,
    CreatorApplication,
    CurrentCreatorProfile,
    OwnedCampaign,
    VisibleApplication,
)
from app.modules.campaigns.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationReject,
    ApplicationStatus,
)

WRITE_LIMIT = "30 per minute"
READ_LIMIT = "60 per minute"

# route_class: every POST here accepts an Idempotency-Key header, so a
# creator whose connection dropped can retry safely (backend.md section 2).
router = APIRouter(prefix="/api/v1", tags=["applications"], route_class=IdempotentRoute)

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Rows per page")]
Cursor = Annotated[str | None, Query(description="From a previous page's next_cursor")]
StatusFilter = Annotated[ApplicationStatus | None, Query(alias="status")]

_COMMON_ERRORS = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _page(result) -> Page[ApplicationRead]:
    return Page[ApplicationRead](
        items=[ApplicationRead.model_validate(row) for row in result.rows],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/campaigns/{campaign_id}/applications",
    status_code=status.HTTP_201_CREATED,
    response_model=ApplicationRead,
    summary="Apply to a campaign",
    description=(
        "Sends the signed-in creator's pitch to an open campaign. One "
        "application per creator per campaign."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such campaign"),
        409: problem_doc(
            "The creator profile is missing, the campaign is not open, the "
            "closing date has passed, or you already applied"
        ),
        422: problem_doc("A field is missing or invalid"),
    },
)
@limiter.limit(WRITE_LIMIT)
def apply_to_campaign(
    request: Request,
    response: Response,
    campaign_id: uuid.UUID,
    body: ApplicationCreate,
    creator: CurrentCreatorProfile,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    application = service.apply_to_campaign(
        db, campaign_id, creator, body.model_dump(), now
    )
    response.headers["Location"] = f"/api/v1/applications/{application.id}"
    return ApplicationRead.model_validate(application)


@router.get(
    "/campaigns/{campaign_id}/applications",
    response_model=Page[ApplicationRead],
    summary="List applications to my campaign",
    description="Applications to one of the signed-in brand's campaigns, newest first.",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such campaign, or it is not yours"),
        409: problem_doc("The brand profile has not been created yet"),
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@limiter.limit(READ_LIMIT)
def list_campaign_applications(
    request: Request,
    campaign: OwnedCampaign,
    application_status: StatusFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[ApplicationRead]:
    return _page(
        service.list_campaign_applications(
            db, campaign, limit=limit, cursor=cursor, status=application_status
        )
    )


@router.get(
    "/applications/me",
    response_model=Page[ApplicationRead],
    summary="List my applications",
    description="Everything the signed-in creator has applied to, newest first.",
    responses={
        **_COMMON_ERRORS,
        409: problem_doc("The creator profile has not been created yet"),
        422: problem_doc("A query parameter or the cursor is invalid"),
    },
)
@limiter.limit(READ_LIMIT)
def list_my_applications(
    request: Request,
    creator: CurrentCreatorProfile,
    application_status: StatusFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
    db: Session = Depends(get_db),
) -> Page[ApplicationRead]:
    return _page(
        service.list_creator_applications(
            db, creator, limit=limit, cursor=cursor, status=application_status
        )
    )


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationRead,
    summary="Read one application",
    description=(
        "Visible to the creator who sent it and to the brand whose campaign it "
        "is for. Anyone else gets 404."
    ),
    responses={**_COMMON_ERRORS, 404: problem_doc("No such application, or not yours")},
)
@limiter.limit(READ_LIMIT)
def read_application(
    request: Request, application: VisibleApplication
) -> ApplicationRead:
    return ApplicationRead.model_validate(application)


def _brand_decision(action: str, new_status: str, summary: str, description: str):
    """Shortlist and accept: the brand moves one of its applications on."""

    @router.post(
        f"/applications/{{application_id}}/{action}",
        response_model=ApplicationRead,
        summary=summary,
        description=description,
        name=f"application_{action}",
        responses={
            **_COMMON_ERRORS,
            404: problem_doc("No such application, or it is not for your campaign"),
            409: problem_doc("The application is not in a state where that is allowed"),
        },
    )
    @limiter.limit(WRITE_LIMIT)
    def endpoint(
        request: Request,
        application: BrandApplication,
        db: Session = Depends(get_db),
        now: datetime = Depends(get_now),
    ) -> ApplicationRead:
        return ApplicationRead.model_validate(
            service.change_application_status(db, application, new_status, now)
        )

    return endpoint


shortlist_application = _brand_decision(
    "shortlist",
    "shortlisted",
    "Shortlist an application",
    "Marks an application as one you are considering. The creator sees this.",
)
accept_application = _brand_decision(
    "accept",
    "accepted",
    "Accept an application",
    "Accepts a shortlisted application. This is final and leads to the deal memo.",
)


@router.post(
    "/applications/{application_id}/reject",
    response_model=ApplicationRead,
    summary="Reject an application",
    description=(
        "Says no, with a reason the creator can see. A reason is required: "
        "\"no campaigns and no idea why\" is the complaint this avoids."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such application, or it is not for your campaign"),
        409: problem_doc("The application is not in a state where that is allowed"),
        422: problem_doc("The reason is missing or not one of the allowed values"),
    },
)
@limiter.limit(WRITE_LIMIT)
def reject_application(
    request: Request,
    body: ApplicationReject,
    application: BrandApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    return ApplicationRead.model_validate(
        service.change_application_status(
            db,
            application,
            "rejected",
            now,
            rejection_reason=body.reason,
            rejection_note=body.note,
        )
    )


@router.post(
    "/applications/{application_id}/withdraw",
    response_model=ApplicationRead,
    summary="Withdraw my application",
    description="Takes back an application the signed-in creator sent. This is final.",
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such application, or it is not yours"),
        409: problem_doc("The application is not in a state where that is allowed"),
    },
)
@limiter.limit(WRITE_LIMIT)
def withdraw_application(
    request: Request,
    application: CreatorApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    return ApplicationRead.model_validate(
        service.change_application_status(db, application, "withdrawn", now)
    )

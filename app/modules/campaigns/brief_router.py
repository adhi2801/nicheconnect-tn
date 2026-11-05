"""Drafting a campaign brief from a brand's own words (HTTP; item 40, D-156). The rules: brief_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core import rollout
from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import CurrentBrand, get_now
from app.modules.campaigns import brief_service as service
from app.modules.campaigns.brief_drafter import get_drafter
from app.modules.campaigns.brief_models import CampaignBriefDraft
from app.modules.campaigns.brief_schemas import (
    BriefDraftCreate,
    BriefDraftRead,
    BriefFieldsRead,
)
from app.modules.campaigns.dependencies import CurrentBrandAccess
from app.modules.campaigns.exceptions import BriefDraftingOff

# Each one is sent to a paid API: a ceiling per day as well as per minute.
ASK_LIMIT = "5 per minute;30 per day"
READ_LIMIT = "60 per minute"

router = APIRouter(
    prefix="/api/v1/brief-drafts", tags=["campaigns"], route_class=IdempotentRoute
)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc(
        "`role_not_allowed`: not a brand account; or `brand_role_not_allowed`: your role does not run campaigns"
    ),
    404: problem_doc(
        "`brand_not_found`: the Brand-Id header names a brand you are not in"
    ),
    409: problem_doc("`brand_profile_required`: you have no brand yet"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}


def _read(found: CampaignBriefDraft) -> BriefDraftRead:
    return BriefDraftRead(
        id=found.id,
        status=found.status,
        idea=found.idea,
        draft=BriefFieldsRead.model_validate(found.draft)
        if found.draft is not None
        else None,
        failure=found.failure,
        created_at=found.created_at,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BriefDraftRead,
    summary="Ask for a campaign brief drafted from your own words",
    description=(
        "A few sentences in; a draft of the campaign's title, description, deliverables, "
        "type, niches, cities and budget back, usually within a minute, at the `Location` "
        "given. Only what your words support is filled in: nothing is invented. The draft "
        "creates nothing; prefill the new-campaign form with it, edit, and create the "
        "campaign as usual. Owners, admins and campaign managers. Switched off until "
        "`GET /api/v1/features` says `brief_drafting` is on. Limits: 5 a minute, 30 a day."
    ),
    responses={
        **_COMMON,
        409: problem_doc(
            "`brief_drafts_waiting`: three of your brand's drafts are still being written; "
            "or `brand_profile_required`"
        ),
        422: problem_doc(
            "The idea is under 20 or over 1,500 characters; or `brand_choice_needed`"
        ),
        503: problem_doc("`brief_drafting_unavailable`: drafting is not switched on yet"),
    },
)
@rate_limit(ASK_LIMIT)
def ask(
    request: Request,
    response: Response,
    body: BriefDraftCreate,
    access: CurrentBrandAccess,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BriefDraftRead:
    # Off, or on for a share of brands not yet including this one (D-160).
    if get_drafter() is None or not rollout.includes(
        "brief_drafting", access.brand.account_id
    ):
        raise BriefDraftingOff()
    found = service.ask(db, access, account, body.idea, now)
    response.headers["Location"] = f"/api/v1/brief-drafts/{found.id}"
    return _read(found)


@router.get(
    "/{brief_draft_id}",
    response_model=BriefDraftRead,
    summary="Read a drafted brief",
    description=(
        "`waiting` until the draft is written, then `ready` with its fields, or `failed`. "
        "Anyone on the brand's team may read it. Kept a week. Limit: 60 a minute."
    ),
    responses={
        **_COMMON,
        404: problem_doc("`brief_draft_not_found`, or `brand_not_found`"),
    },
)
@rate_limit(READ_LIMIT)
def read(
    request: Request,
    brief_draft_id: Annotated[uuid.UUID, Path(description="The draft's id")],
    access: CurrentBrandAccess,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> BriefDraftRead:
    return _read(service.get(db, access, brief_draft_id, now))

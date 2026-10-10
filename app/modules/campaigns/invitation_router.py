"""Invitation endpoints: a brand invites, the creator answers (D-084).

Kept apart from the application routes so each file has one job. An
invitation is read and listed like any application: `GET
/applications/{id}`, `GET /applications/me?status=invited`, and the brand's
`GET /campaigns/{id}/applications`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.dependencies import get_now
from app.modules.campaigns import invitation_service as invitations
from app.modules.campaigns.dependencies import (
    BrandApplication,
    CreatorApplication,
    OwnedCampaign,
)
from app.modules.campaigns.schemas import (
    ApplicationRead,
    InvitationCreate,
    InvitationDecline,
)

WRITE_LIMIT = "30 per minute"
# A ceiling per day as well as per minute (trust-and-safety.md rule 2, item 58):
# a per-minute limit stops a script, not a person spamming by hand all day.
INVITE_LIMIT = "30 per minute;100 per day"

# route_class: every POST here accepts an Idempotency-Key header, so a retry
# after a dropped connection never invites twice (backend.md section 2).
router = APIRouter(prefix="/api/v1", tags=["invitations"], route_class=IdempotentRoute)

_COMMON_ERRORS: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    403: problem_doc("This account type cannot use this endpoint"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_ANSWER_ERRORS: ResponseDocs = {
    **_COMMON_ERRORS,
    404: problem_doc("No such invitation, or it is not yours"),
    409: problem_doc(
        "It is not an invitation waiting for an answer, or the campaign is no longer open"
    ),
}


@router.post(
    "/campaigns/{campaign_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=ApplicationRead,
    summary="Invite a creator to my campaign",
    description=(
        "Invites one creator, found in search or in a campaign's matches, to "
        "one of the signed-in brand's open campaigns. The creator is told at "
        "once and answers in one tap; accepting makes the invitation "
        "`accepted`, ready for the deal memo. A campaign may have at most "
        "25 invitations waiting for an answer at once. An invitation lasts "
        "while the campaign is open."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such campaign or creator, or the campaign is not yours"),
        409: problem_doc(
            "The brand profile is missing, the campaign is not open, the creator "
            "already applied or was invited, or the campaign has 25 invitations "
            "waiting"
        ),
        422: problem_doc("A field is missing or invalid"),
    },
)
@rate_limit(INVITE_LIMIT)
def invite_creator(
    request: Request,
    response: Response,
    body: InvitationCreate,
    campaign: OwnedCampaign,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    invitation = invitations.invite_creator(db, campaign, body.creator_id, body.note, now)
    response.headers["Location"] = f"/api/v1/applications/{invitation.id}"
    return ApplicationRead.model_validate(invitation)


@router.post(
    "/applications/{application_id}/accept-invitation",
    response_model=ApplicationRead,
    summary="Accept an invitation",
    description=(
        "The signed-in creator says yes. The invitation becomes `accepted`, "
        "and the brand is told. For a repeat of an earlier deal, the deal memo "
        "is drafted from that deal's terms for the brand to date and send."
    ),
    responses=_ANSWER_ERRORS,
)
@rate_limit(WRITE_LIMIT)
def accept_invitation(
    request: Request,
    invitation: CreatorApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    return ApplicationRead.model_validate(
        invitations.accept_invitation(db, invitation, now)
    )


@router.post(
    "/applications/{application_id}/decline-invitation",
    response_model=ApplicationRead,
    summary="Decline an invitation",
    description=(
        "The signed-in creator says no, with a reason the brand sees, as a "
        "creator sees the brand's reason for a rejection. This is final."
    ),
    responses={
        **_ANSWER_ERRORS,
        422: problem_doc("The reason is missing or not one of the allowed values"),
    },
)
@rate_limit(WRITE_LIMIT)
def decline_invitation(
    request: Request,
    body: InvitationDecline,
    invitation: CreatorApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    return ApplicationRead.model_validate(
        invitations.decline_invitation(db, invitation, body.reason, now)
    )


@router.post(
    "/applications/{application_id}/withdraw-invitation",
    response_model=ApplicationRead,
    summary="Withdraw an invitation",
    description=(
        "The signed-in brand takes back an invitation the creator has not "
        "answered yet. The creator is told. This is final."
    ),
    responses={
        **_COMMON_ERRORS,
        404: problem_doc("No such invitation, or it is not for your campaign"),
        409: problem_doc("It is not an invitation waiting for an answer"),
    },
)
@rate_limit(WRITE_LIMIT)
def withdraw_invitation(
    request: Request,
    invitation: BrandApplication,
    db: Session = Depends(get_db),
    now: datetime = Depends(get_now),
) -> ApplicationRead:
    return ApplicationRead.model_validate(
        invitations.withdraw_invitation(db, invitation, now)
    )

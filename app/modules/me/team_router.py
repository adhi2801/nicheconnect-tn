"""Team seats for brands (HTTP; item 13, D-148). The rules: team_service."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status
from sqlalchemy.orm import Session

from app.core.errors import ResponseDocs, problem_doc
from app.core.idempotent_route import IdempotentRoute
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.modules.auth.brand_access import BrandAccess
from app.modules.auth.dependencies import (
    CurrentAccount,
    CurrentBrand,
    StepUpCode,
    get_now,
)
from app.modules.campaigns.dependencies import CurrentBrandAccess
from app.modules.me import team_service as service
from app.modules.me.team_schemas import (
    MyTeamInviteRead,
    TeamInviteAccept,
    TeamInviteCreate,
    TeamInviteRead,
    TeamMemberRead,
    TeamRead,
    TeamRoleChange,
)

READ_LIMIT = "60 per minute"
# An invite can lead to a notice to someone else's account: a daily ceiling
# per account, as everything that reaches another person has (trust-and-safety
# rule 2).
INVITE_LIMIT = "10 per minute;20 per day"
CHANGE_LIMIT = "30 per minute"

router = APIRouter(tags=["team"], route_class=IdempotentRoute)

_COMMON: ResponseDocs = {
    401: problem_doc("No access token, or it is invalid or expired"),
    429: problem_doc("Too many requests; see the Retry-After header"),
}
_BRAND: ResponseDocs = {
    **_COMMON,
    403: problem_doc(
        "`role_not_allowed`: not a brand account; `brand_role_not_allowed`: your "
        "role does not include the team; or `team_change_not_allowed`: only the "
        "owner makes or changes an admin, and an admin never removes one"
    ),
    404: problem_doc(
        "`brand_not_found`: the Brand-Id header names a brand you are not in"
    ),
    409: problem_doc("`brand_profile_required`: you have no brand yet"),
    422: problem_doc("`brand_choice_needed`, or the body is not usable"),
}
InviteId = Annotated[uuid.UUID, Path(description="The invite's id")]
MemberId = Annotated[uuid.UUID, Path(description="The team member's id")]


def _team(access: BrandAccess, db: Session, now: datetime) -> TeamRead:
    found = service.team(db, access, now)
    return TeamRead(
        brand_id=found.brand.id,
        brand_name=found.brand.name,
        your_role=access.role,
        members=[TeamMemberRead.model_validate(m) for m in found.members],
        invites=[TeamInviteRead.model_validate(i) for i in found.invites],
    )


@router.get(
    "/api/v1/brands/me/team",
    response_model=TeamRead,
    summary="My brand's team",
    description=(
        "Who acts for the brand, in which role, and the invites still open: first "
        "names and roles, never a phone number. Everyone in the brand may read it. "
        "Limit: 60 a minute."
    ),
    responses=_BRAND,
)
@rate_limit(READ_LIMIT)
def read_team(
    request: Request,
    access: CurrentBrandAccess,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> TeamRead:
    return _team(access, db, now)


@router.post(
    "/api/v1/brands/me/team/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=TeamInviteRead,
    summary="Invite someone to the team",
    description=(
        "Invites a phone number to act for the brand in a role, for 7 days. We send "
        "no message to the number: tell the person, and the invite appears when "
        "that number signs in as a brand. We keep only a keyed hash of the number. "
        "An `admin` invite is the owner's alone and needs **a code**: ask at "
        "`POST /api/v1/me/step-up` with `change_team` and the value "
        "`invite:<phone>:admin`, then send it in `Step-Up-Code`. Owners and admins "
        "only. Limits: 10 a minute, 20 a day."
    ),
    responses={
        **_BRAND,
        400: problem_doc("The code is wrong, expired, used, or for another change"),
        409: problem_doc(
            "`team_invite_exists`, `already_on_team`, or `brand_profile_required`"
        ),
    },
)
@rate_limit(INVITE_LIMIT)
def invite(
    request: Request,
    body: TeamInviteCreate,
    access: CurrentBrandAccess,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> TeamInviteRead:
    made = service.invite(
        db, access, account, body.phone, body.role, body.first_name, step_up_code, now
    )
    return TeamInviteRead.model_validate(made)


@router.delete(
    "/api/v1/brands/me/team/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Take back an invite",
    description="Ends an open invite at once. Owners and admins only. Limit: 30 a minute.",
    responses={
        **_BRAND,
        404: problem_doc("`team_invite_not_found`, or `brand_not_found`"),
    },
)
@rate_limit(CHANGE_LIMIT)
def revoke_invite(
    request: Request,
    invite_id: InviteId,
    access: CurrentBrandAccess,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    service.revoke_invite(db, access, invite_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/api/v1/brands/me/team/members/{member_id}",
    response_model=TeamMemberRead,
    summary="Change a member's role",
    description=(
        "Gives a member another role; they are told in the app. Making someone an "
        "admin, or changing an admin, is the owner's alone and needs **a code** "
        "for `change_team` with the value `role:<member_id>:<role>`. Owners and "
        "admins only. Limit: 30 a minute."
    ),
    responses={
        **_BRAND,
        400: problem_doc("The code is wrong, expired, used, or for another change"),
        404: problem_doc("`team_member_not_found`, or `brand_not_found`"),
    },
)
@rate_limit(CHANGE_LIMIT)
def change_role(
    request: Request,
    member_id: MemberId,
    body: TeamRoleChange,
    access: CurrentBrandAccess,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> TeamMemberRead:
    member = service.change_role(
        db, access, account, member_id, body.role, step_up_code, now
    )
    return TeamMemberRead.model_validate(member)


@router.delete(
    "/api/v1/brands/me/team/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove someone from the team",
    description=(
        "They can no longer act for the brand, from their next request; they are "
        "told in the app. Needs **a code** for `change_team` with the value "
        "`remove:<member_id>`. An admin never removes an admin. Owners and admins "
        "only. Limit: 30 a minute."
    ),
    responses={
        **_BRAND,
        400: problem_doc("The code is wrong, expired, used, or for another change"),
        401: problem_doc(
            "No access token, or it is invalid or expired; or `step_up_required`"
        ),
        404: problem_doc("`team_member_not_found`, or `brand_not_found`"),
    },
)
@rate_limit(CHANGE_LIMIT)
def remove_member(
    request: Request,
    member_id: MemberId,
    access: CurrentBrandAccess,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
    step_up_code: StepUpCode = None,
) -> Response:
    service.remove(db, access, account, member_id, step_up_code, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/api/v1/me/team-invites",
    response_model=list[MyTeamInviteRead],
    summary="Invites to my number",
    description=(
        "Open invites to the signed-in brand account's own number, oldest first; "
        "a short list, since each lapses in 7 days. Limit: 60 a minute."
    ),
    responses=_COMMON,
)
@rate_limit(READ_LIMIT)
def my_invites(
    request: Request,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> list[MyTeamInviteRead]:
    return [
        MyTeamInviteRead(
            id=i.id,
            brand_id=b.id,
            brand_name=b.name,
            role=i.role,
            first_name=i.first_name,
            expires_at=i.expires_at,
        )
        for i, b in service.invites_for(db, account, now)
    ]


@router.post(
    "/api/v1/me/team-invites/{invite_id}/accept",
    status_code=status.HTTP_201_CREATED,
    response_model=TeamMemberRead,
    summary="Join a brand's team",
    description=(
        "Accepts an invite to your own number: you act for that brand in its role. "
        "Optionally give the first name creators will see. The owner and admins are "
        "told. Limit: 30 a minute."
    ),
    responses={
        **_COMMON,
        404: problem_doc("`team_invite_not_found`"),
        409: problem_doc("`already_on_team`, or `team_full` (20 besides the owner)"),
        422: problem_doc("The first name is not usable"),
    },
)
@rate_limit(CHANGE_LIMIT)
def accept_invite(
    request: Request,
    invite_id: InviteId,
    body: TeamInviteAccept,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> TeamMemberRead:
    member = service.accept(db, account, invite_id, body.first_name, now)
    return TeamMemberRead.model_validate(member)


@router.post(
    "/api/v1/me/team-invites/{invite_id}/decline",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Say no to an invite",
    description="Ends an invite to your own number. Limit: 30 a minute.",
    responses={**_COMMON, 404: problem_doc("`team_invite_not_found`")},
)
@rate_limit(CHANGE_LIMIT)
def decline_invite(
    request: Request,
    invite_id: InviteId,
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    service.decline(db, account, invite_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/api/v1/me/teams/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave a brand's team",
    description=(
        "Stop acting for a brand you belong to, at once, with no code. The brand's "
        "owner cannot leave their own brand this way. Limit: 30 a minute."
    ),
    responses={**_COMMON, 404: problem_doc("`team_member_not_found`")},
)
@rate_limit(CHANGE_LIMIT)
def leave_team(
    request: Request,
    brand_id: Annotated[uuid.UUID, Path(description="The brand's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
    now: Annotated[datetime, Depends(get_now)],
) -> Response:
    service.leave(db, account, brand_id, now)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

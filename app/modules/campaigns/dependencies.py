"""FastAPI dependencies for campaigns: who is asking, and do they own it."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import brand_access, brand_acts
from app.modules.auth.dependencies import CurrentAccount, CurrentBrand, CurrentCreator
from app.modules.auth.exceptions import BrandRoleNotAllowed
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.exceptions import (
    ApplicationNotFound,
    BrandProfileRequired,
    CampaignNotFound,
)
from app.modules.campaigns.models import Application, Campaign
from app.modules.campaigns.service import get_creator_for_account


def get_current_brand_access(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    brand_id: Annotated[
        str | None,
        Header(
            alias=brand_access.BRAND_HEADER,
            description=(
                "The brand to act for, for someone in more than one (D-148). "
                "Leave it out to act for your own brand, or your only one."
            ),
        ),
    ] = None,
) -> brand_access.BrandAccess:
    """The brand the signed-in account acts for and its role there, allowed this route.

    409 if it has no brand at all; 404 for a brand named but not theirs; 403
    when their role does not hold this route's act (`auth.brand_acts`).
    """
    access = brand_access.resolve(db, account, brand_access.parse_brand_header(brand_id))
    if access is None:
        raise BrandProfileRequired()
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    if not brand_acts.may(access.role, request.method, path):
        raise BrandRoleNotAllowed()
    # Who is acting, for the deal record to name (D-148): the request's own
    # session carries it, so an entry sealed in this request names this person.
    db.info[brand_access.ACTING_ACCOUNT] = account.id
    return access


CurrentBrandAccess = Annotated[
    brand_access.BrandAccess, Depends(get_current_brand_access)
]


def get_current_brand_profile(
    request: Request,
    account: CurrentBrand,
    db: Annotated[Session, Depends(get_db)],
    brand_id: Annotated[
        str | None,
        Header(
            alias=brand_access.BRAND_HEADER,
            description=(
                "The brand to act for, for someone in more than one (D-148). "
                "Leave it out to act for your own brand, or your only one."
            ),
        ),
    ] = None,
) -> Brand:
    """The brand the signed-in account acts for, in a role allowed this route.

    409 if it has no brand at all; 404 for a brand named but not theirs; 403
    when their role does not hold this route's act (`auth.brand_acts`). The
    owner of a brand passes every check, as before teams existed.
    """
    return get_current_brand_access(request, account, db, brand_id).brand


CurrentBrandProfile = Annotated[Brand, Depends(get_current_brand_profile)]


def get_owned_campaign(
    campaign_id: Annotated[uuid.UUID, Path(description="The campaign's id")],
    brand: CurrentBrandProfile,
    db: Annotated[Session, Depends(get_db)],
) -> Campaign:
    """A campaign owned by the signed-in brand.

    Another brand's campaign gives 404, never 403: saying "forbidden" would
    confirm that the campaign exists (security.md section 2).
    """
    campaign = db.scalars(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.brand_id == brand.id)
    ).first()
    if campaign is None:
        raise CampaignNotFound()
    return campaign


OwnedCampaign = Annotated[Campaign, Depends(get_owned_campaign)]


def get_current_creator_profile(
    account: CurrentCreator, db: Annotated[Session, Depends(get_db)]
) -> Creator:
    """The signed-in creator's profile, or 409 if they have not created one."""
    return get_creator_for_account(db, account.id)


CurrentCreatorProfile = Annotated[Creator, Depends(get_current_creator_profile)]


def get_visible_application(
    application_id: Annotated[uuid.UUID, Path(description="The application's id")],
    account: CurrentAccount,
    db: Annotated[Session, Depends(get_db)],
) -> Application:
    """An application the signed-in account may see.

    Visible to the creator who sent it and to the brand that owns the
    campaign. Anyone else gets 404, never 403, so its existence stays private.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise ApplicationNotFound()

    if account.role == "creator":
        creator = db.scalars(
            select(Creator).where(Creator.account_id == account.id)
        ).first()
        if creator is not None and application.creator_id == creator.id:
            return application
    else:
        owner_account_id = db.scalar(
            select(Brand.account_id)
            .join(Campaign, Campaign.brand_id == Brand.id)
            .where(Campaign.id == application.campaign_id)
        )
        if owner_account_id == account.id:
            return application
    raise ApplicationNotFound()


VisibleApplication = Annotated[Application, Depends(get_visible_application)]


def get_owned_application(
    application_id: Annotated[uuid.UUID, Path(description="The application's id")],
    brand: CurrentBrandProfile,
    db: Annotated[Session, Depends(get_db)],
) -> Application:
    """An application to one of the signed-in brand's campaigns (else 404)."""
    application = db.scalars(
        select(Application)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(Application.id == application_id, Campaign.brand_id == brand.id)
    ).first()
    if application is None:
        raise ApplicationNotFound()
    return application


BrandApplication = Annotated[Application, Depends(get_owned_application)]


def get_own_application(
    application_id: Annotated[uuid.UUID, Path(description="The application's id")],
    creator: CurrentCreatorProfile,
    db: Annotated[Session, Depends(get_db)],
) -> Application:
    """An application the signed-in creator sent (else 404)."""
    application = db.scalars(
        select(Application).where(
            Application.id == application_id, Application.creator_id == creator.id
        )
    ).first()
    if application is None:
        raise ApplicationNotFound()
    return application


CreatorApplication = Annotated[Application, Depends(get_own_application)]

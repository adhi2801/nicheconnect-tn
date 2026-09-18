"""FastAPI dependencies for campaigns: who is asking, and do they own it."""

import uuid
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import CurrentBrand
from app.modules.auth.models.brand import Brand
from app.modules.campaigns.exceptions import CampaignNotFound
from app.modules.campaigns.models import Campaign
from app.modules.campaigns.service import get_brand_for_account


def get_current_brand_profile(
    account: CurrentBrand, db: Annotated[Session, Depends(get_db)]
) -> Brand:
    """The signed-in brand's profile, or 409 if they have not created one."""
    return get_brand_for_account(db, account.id)


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
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.brand_id == brand.id
        )
    ).first()
    if campaign is None:
        raise CampaignNotFound()
    return campaign


OwnedCampaign = Annotated[Campaign, Depends(get_owned_campaign)]

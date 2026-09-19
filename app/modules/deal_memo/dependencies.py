"""Who may see or move a deal memo."""

import uuid
from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.dependencies import CurrentBrandProfile, CurrentCreatorProfile
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.exceptions import MemoNotFound
from app.modules.deal_memo.models import DealMemo

MemoId = Annotated[uuid.UUID, Path(description="The memo's id")]


def get_brand_memo(
    memo_id: MemoId,
    brand: CurrentBrandProfile,
    db: Annotated[Session, Depends(get_db)],
) -> DealMemo:
    """A memo on one of the signed-in brand's campaigns, else 404."""
    memo = db.scalars(
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(DealMemo.id == memo_id, Campaign.brand_id == brand.id)
    ).first()
    if memo is None:
        raise MemoNotFound()
    return memo


BrandMemo = Annotated[DealMemo, Depends(get_brand_memo)]


def get_creator_memo(
    memo_id: MemoId,
    creator: CurrentCreatorProfile,
    db: Annotated[Session, Depends(get_db)],
) -> DealMemo:
    """A memo sent to the signed-in creator, else 404.

    A draft is not theirs to see: to them it does not exist yet.
    """
    memo = db.scalars(
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .where(
            DealMemo.id == memo_id,
            Application.creator_id == creator.id,
            DealMemo.status != "draft",
        )
    ).first()
    if memo is None:
        raise MemoNotFound()
    return memo


CreatorMemo = Annotated[DealMemo, Depends(get_creator_memo)]


def visible_memo_for_account(
    db: Session, memo_id: uuid.UUID, account_id: uuid.UUID, role: str
) -> DealMemo:
    """The same memo from either side, for reading.

    The owning brand sees it in any status; the creator sees it once sent.
    """
    query = (
        select(DealMemo)
        .join(Application, Application.id == DealMemo.application_id)
        .where(DealMemo.id == memo_id)
    )
    if role == "brand":
        memo = db.scalars(
            query.join(Campaign, Campaign.id == Application.campaign_id)
            .join(Brand, Brand.id == Campaign.brand_id)
            .where(Brand.account_id == account_id)
        ).first()
    else:
        memo = db.scalars(
            query.join(Creator, Creator.id == Application.creator_id).where(
                Creator.account_id == account_id, DealMemo.status != "draft"
            )
        ).first()
    if memo is None:
        raise MemoNotFound()
    return memo
